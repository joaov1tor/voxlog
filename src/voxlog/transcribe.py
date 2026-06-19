from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path
from .config import Config


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


def transcribe(audio_path: Path, cfg: Config, runner=None) -> str:
    run = runner or _default_runner
    with tempfile.TemporaryDirectory() as out_dir:
        cmd = _build_cmd(audio_path, cfg, out_dir)
        run(cmd, out_dir)
        txt_path = Path(out_dir) / (audio_path.stem + ".txt")
        return txt_path.read_text(encoding="utf-8").strip()
