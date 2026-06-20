from __future__ import annotations
import json
import subprocess
import tempfile
from pathlib import Path
from .config import Config


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

def transcribe(audio_path: Path, cfg: Config, runner=None, curl=None) -> str:
    # Whisper-GPU remoto tem prioridade quando configurado; cai p/ local se falhar.
    if cfg.whisper_endpoint:
        try:
            return _transcribe_remote(audio_path, cfg, curl=curl)
        except Exception:
            pass
    return _transcribe_local(audio_path, cfg, runner=runner)
