from __future__ import annotations
import base64
import json
import os
import subprocess
import tempfile
from pathlib import Path
from .config import Config
from .audioutil import trim_silence as _do_trim


# ---------- remoto (Whisper GPU, API OpenAI-compat) ----------

def _default_curl(cmd: list[str]) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"curl falhou: {proc.stderr[:300]}")
    return proc.stdout


def _transcribe_remote(audio_path: Path, cfg: Config, curl=None) -> str:
    run = curl or _default_curl
    url = cfg.whisper_endpoint.rstrip("/") + "/v1/audio/transcriptions"
    lang = cfg.whisper_language or "pt"
    out = run([
        "curl", "-sS", "--fail", "--max-time", "600", url,
        "-F", f"file=@{audio_path}",
        "-F", f"language={lang}",
        "-F", "response_format=json",
    ])
    return str(json.loads(out)["text"]).strip()


# ---------- local (whisper CLI) ----------

def _default_runner(cmd: list[str], out_dir: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"whisper falhou: {proc.stderr[:300]}")


def _build_cmd(audio_path: Path, cfg: Config, out_dir: str) -> list[str]:
    cmd = ["whisper", str(audio_path), "--model", cfg.whisper_model,
           "--output_format", "txt", "--output_dir", out_dir]
    if cfg.whisper_language:
        cmd += ["--language", cfg.whisper_language]
    return cmd


def _transcribe_local(audio_path: Path, cfg: Config, runner=None) -> str:
    run = runner or _default_runner
    with tempfile.TemporaryDirectory() as out_dir:
        cmd = _build_cmd(audio_path, cfg, out_dir)
        run(cmd, out_dir)
        txt_path = Path(out_dir) / (audio_path.stem + ".txt")
        return txt_path.read_text(encoding="utf-8").strip()


# ---------- entrada ----------

# ---------- fallback nuvem (OpenRouter Whisper) — NÃO roda whisper local (fritava o Mac) ----------

def _transcribe_openrouter(audio_path: Path, cfg: Config, curl=None) -> str:
    from .summarize import _openrouter_key   # mesma chave do fallback de resumo
    key = _openrouter_key()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY ausente")
    fmt = (audio_path.suffix.lstrip(".").lower() or "m4a")
    body = json.dumps({
        "input_audio": {"data": base64.b64encode(audio_path.read_bytes()).decode(), "format": fmt},
        "model": cfg.openrouter_transcribe_model,
        "language": cfg.whisper_language or "pt",
    })
    run = curl or _default_curl
    # body grande (base64) → via arquivo (-d @file), senão estoura ARG_MAX
    with tempfile.NamedTemporaryFile("w", suffix=".json") as tf:
        tf.write(body); tf.flush()
        out = run([
            "curl", "-sS", "--fail", "--max-time", "600",
            cfg.openrouter_base_url.rstrip("/") + "/audio/transcriptions",
            "-H", f"Authorization: Bearer {key}",
            "-H", "Content-Type: application/json",
            "-d", "@" + tf.name,
        ])
    return str(json.loads(out)["text"]).strip()


def transcribe(audio_path: Path, cfg: Config, runner=None, curl=None) -> str:
    # 1) avell :5050 (Whisper-GPU via tailscale) → 2) OpenRouter (nuvem) → sem local.
    if cfg.whisper_endpoint:
        try:
            return _transcribe_remote(audio_path, cfg, curl=curl)
        except Exception:
            pass
        try:
            return _transcribe_openrouter(audio_path, cfg, curl=curl)
        except Exception:
            pass
        return ""   # sem whisper local (pesado/CPU); nota sai sem transcrição → reprocessa depois
    return _transcribe_local(audio_path, cfg, runner=runner)


def transcribe_diarized(audio_path: Path, cfg: Config, curl=None) -> str:
    """Envia o áudio ao serviço de diarização (:5051) e devolve a transcrição
    já rotulada por falante ('Eu' / 'Falante 2'...). Levanta em caso de falha —
    o chamador faz fallback para a transcrição normal."""
    run = curl or _default_curl
    url = cfg.voice_diarize_endpoint.rstrip("/") + "/v1/audio/diarize"
    out = run([
        "curl", "-sS", "--fail", "--max-time", "7200", url,   # diarização na CPU é lenta p/ reunião longa
        "-F", f"file=@{audio_path}",
        "-F", "response_format=json",
    ])
    return str(json.loads(out)["text"]).strip()


# ---------- ElevenLabs Scribe (STT+diarização dedicado, robusto) ----------

def _elevenlabs_key() -> str:
    """Chave do ElevenLabs. Arquivo dedicado ~/.config/voxlog/elevenlabs.env tem
    prioridade sobre a env do shell. NUNCA hardcode/commit a chave."""
    p = Path.home() / ".config" / "voxlog" / "elevenlabs.env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line.startswith("ELEVENLABS_API_KEY="):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                if v:
                    return v
    return os.environ.get("ELEVENLABS_API_KEY", "")


def _words_to_transcript(words: list[dict]) -> str:
    """Agrupa palavras consecutivas do mesmo falante -> linhas '**Falante N** [mm:ss]: texto'.
    Mapeia speaker_0/1/... do ElevenLabs para 'Falante 1/2/...' (rótulos estáveis por chamada)."""
    spk_map: dict[str, str] = {}
    lines: list[str] = []
    cur: str | None = None
    buf: list[str] = []
    t0 = 0.0

    def flush():
        if buf:
            mm, ss = int(t0 // 60), int(t0 % 60)
            lines.append(f"**{cur}** [{mm:02d}:{ss:02d}]: " + "".join(buf).strip())

    for w in words:
        if w.get("type") == "spacing":
            if cur is not None:
                buf.append(w.get("text", " "))
            continue
        sid = w.get("speaker_id", "speaker_0")
        lab = spk_map.get(sid)
        if lab is None:
            lab = f"Falante {len(spk_map) + 1}"
            spk_map[sid] = lab
        if lab != cur:
            flush()
            cur, buf, t0 = lab, [], float(w.get("start", 0.0))
        buf.append(w.get("text", ""))
    flush()
    return "\n".join(lines).strip()


def _elevenlabs_stt(audio_path: Path, cfg: Config, curl=None) -> dict:
    key = _elevenlabs_key()
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY ausente (env ou ~/.config/voxlog/elevenlabs.env)")
    run = curl or _default_curl
    lang = cfg.whisper_language or "pt"
    out = run([
        "curl", "-sS", "--fail-with-body", "--max-time", "1200", cfg.elevenlabs_endpoint,
        "-H", f"xi-api-key: {key}",
        "-F", f"model_id={cfg.elevenlabs_model}",
        "-F", f"file=@{audio_path}",
        "-F", "diarize=true",
        "-F", "timestamps_granularity=word",
        "-F", f"language_code={lang}",
    ])
    return json.loads(out)


def transcribe_elevenlabs_diarized(audio_path: Path, cfg: Config, curl=None, runner=None) -> str:
    """Pré-trima o silêncio (mata alucinação em dead air + corta custo) e envia ao
    ElevenLabs Scribe, devolvendo a transcrição rotulada por falante. Levanta em falha —
    o chamador faz fallback."""
    with tempfile.TemporaryDirectory() as td:
        src = audio_path
        if cfg.voice_trim_silence:
            src = _do_trim(audio_path, Path(td) / "trim.mp3",
                           threshold=cfg.voice_silence_db,
                           min_sec=cfg.voice_silence_min_sec,
                           keep=cfg.voice_silence_keep, runner=runner)
        data = _elevenlabs_stt(src, cfg, curl=curl)
    return _words_to_transcript(data.get("words", []))


def diarize(audio_path: Path, cfg: Config, curl=None, runner=None) -> str:
    """Dispatcher de diarização por provider (config `voice.provider`).
    'elevenlabs' (padrão, STT dedicado robusto) | 'whisperx' (:5051)."""
    if cfg.voice_diarize_provider == "whisperx":
        return transcribe_diarized(audio_path, cfg, curl=curl)
    return transcribe_elevenlabs_diarized(audio_path, cfg, curl=curl, runner=runner)
