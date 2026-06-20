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
    staging_dir: Path = field(default_factory=lambda: Path("~/Gravacoes/staging").expanduser())
    whisper_model: str = "medium"
    whisper_language: str | None = None
    whisper_endpoint: str = ""   # URL base do Whisper-GPU remoto (vazio = local)
    summarizer: str = "codex"
    ollama_model: str = "llama3.1:8b"
    codex_model: str | None = None
    min_duration_sec: float = 5.0
    target_apps: list[str] = field(default_factory=list)
    ignored_apps: list[str] = field(default_factory=list)


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
                "summarizer", "ollama_model", "target_apps", "ignored_apps"):
        if key in data:
            setattr(cfg, key, data[key])
    if data.get("whisper_language"):
        cfg.whisper_language = data["whisper_language"]
    if data.get("codex_model"):
        cfg.codex_model = data["codex_model"]
    if "min_duration_sec" in data:
        cfg.min_duration_sec = float(data["min_duration_sec"])
    return cfg
