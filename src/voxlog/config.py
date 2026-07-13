from __future__ import annotations
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def _expand(p: str) -> Path:
    return Path(p).expanduser()


@dataclass
class Config:
    vault_path: Path = Path("/Volumes/SSD/Dropbox/obsidian/SecundBrain")
    gravacoes_dir: str = "🎙️ Gravações"
    audios_dir: str = "🎙️ Gravações/_audios"
    staging_dir: Path = field(default_factory=lambda: Path("/Volumes/SSD/Gravacoes/staging"))
    whisper_model: str = "medium"
    whisper_language: str | None = None
    whisper_endpoint: str = ""   # URL base do Whisper-GPU remoto (vazio = local)
    summarizer: str = "codex"
    summarizer_fallback: str = "claude"   # usado se o primário (codex) falhar (ex.: cota)
    ollama_model: str = "llama3.1:8b"
    codex_model: str | None = None
    claude_model: str = "claude-haiku-4-5"   # modelo do fallback via claude CLI
    openrouter_model: str = "deepseek/deepseek-v4-flash"   # fallback DeepSeek via OpenRouter
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_transcribe_model: str = "openai/gpt-4o-mini-transcribe"   # fallback transcrição (nuvem, bom+barato)
    min_duration_sec: float = 5.0
    target_apps: list[str] = field(default_factory=list)
    ignored_apps: list[str] = field(default_factory=list)
    # Vocabulário da SUA operação — sem isto o modelo classifica no chute.
    # [taxonomia] clientes = [...] / produtos = [...]
    clientes: list[str] = field(default_factory=list)
    produtos: list[str] = field(default_factory=list)
    # [glossario] "CACI" = "CASSI"  — corrige o que o transcritor ouve errado
    glossario: dict[str, str] = field(default_factory=dict)
    # [taxonomia.pistas] Lívio = ["check-in", "APK"] — termos que denunciam a entidade
    # quando o nome dela não é dito em voz alta na reunião
    pistas: dict[str, list[str]] = field(default_factory=dict)
    voice_enabled: bool = False
    voice_diarize_provider: str = "elevenlabs"   # "elevenlabs" (STT dedicado, robusto) | "whisperx" (:5051, OOM na GPU 6GB)
    voice_diarize_endpoint: str = "http://localhost:5051"
    voice_max_sec: float = 600.0   # acima disso, pula diarização (OOM na GPU 6GB)
    elevenlabs_endpoint: str = "https://api.elevenlabs.io/v1/speech-to-text"
    elevenlabs_model: str = "scribe_v1"
    # pré-trim de silêncio (obrigatório: dead air faz Whisper/Gemini loopar e ElevenLabs alucinar)
    voice_trim_silence: bool = True
    voice_silence_db: str = "-35dB"        # limiar do que conta como silêncio
    voice_silence_min_sec: float = 2.0     # só remove silêncios >= isto
    voice_silence_keep: float = 0.3        # padding mantido em cada corte (evita palavras coladas)


def load_config(path: Path | None = None) -> Config:
    cfg = Config()
    if path is None or not Path(path).exists():
        return cfg
    data = tomllib.loads(Path(path).read_text())
    if "vault_path" in data:
        cfg.vault_path = _expand(data["vault_path"])
    if "staging_dir" in data:
        cfg.staging_dir = _expand(data["staging_dir"])
    for key in ("gravacoes_dir", "audios_dir", "whisper_model", "whisper_endpoint",
                "summarizer", "summarizer_fallback", "claude_model",
                "openrouter_model", "openrouter_base_url", "openrouter_transcribe_model",
                "elevenlabs_endpoint", "elevenlabs_model",
                "ollama_model", "target_apps", "ignored_apps"):
        if key in data:
            setattr(cfg, key, data[key])
    if data.get("whisper_language"):
        cfg.whisper_language = data["whisper_language"]
    if data.get("codex_model"):
        cfg.codex_model = data["codex_model"]
    if "min_duration_sec" in data:
        cfg.min_duration_sec = float(data["min_duration_sec"])
    tax = data.get("taxonomia", {})
    if "clientes" in tax:
        cfg.clientes = [str(c) for c in tax["clientes"]]
    if "produtos" in tax:
        cfg.produtos = [str(p) for p in tax["produtos"]]
    if "pistas" in tax:
        cfg.pistas = {str(k): [str(v) for v in vs] for k, vs in tax["pistas"].items()}
    glossario = data.get("glossario", {})
    if glossario:
        cfg.glossario = {str(k): str(v) for k, v in glossario.items()}

    voice = data.get("voice", {})
    if "enabled" in voice:
        cfg.voice_enabled = bool(voice["enabled"])
    if "provider" in voice:
        cfg.voice_diarize_provider = voice["provider"]
    if "diarize_endpoint" in voice:
        cfg.voice_diarize_endpoint = voice["diarize_endpoint"]
    if "max_sec" in voice:
        cfg.voice_max_sec = float(voice["max_sec"])
    if "trim_silence" in voice:
        cfg.voice_trim_silence = bool(voice["trim_silence"])
    if "silence_db" in voice:
        cfg.voice_silence_db = str(voice["silence_db"])
    if "silence_min_sec" in voice:
        cfg.voice_silence_min_sec = float(voice["silence_min_sec"])
    if "silence_keep" in voice:
        cfg.voice_silence_keep = float(voice["silence_keep"])
    return cfg
