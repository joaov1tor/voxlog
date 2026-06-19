from __future__ import annotations
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from .config import Config
from .transcribe import transcribe as _do_transcribe
from .summarize import summarize as _do_summarize
from .vault import NoteMeta, write_note


def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def _ffprobe_runner(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def audio_duration_sec(path: Path, runner=None) -> float:
    run = runner or _ffprobe_runner
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)])
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def process_audio(audio_path: Path, tipo: str, origem: str, cfg: Config,
                  force_local: bool = False, *, _transcribe=None,
                  _summarize=None, _duration=None) -> Path | None:
    audio_path = Path(audio_path)
    duration = (_duration or audio_duration_sec)(audio_path)
    if duration < cfg.min_duration_sec:
        audio_path.unlink(missing_ok=True)
        return None

    transcript = (_transcribe or _do_transcribe)(audio_path, cfg)
    summary = (_summarize or _do_summarize)(transcript, cfg, force_local)

    mtime = datetime.fromtimestamp(audio_path.stat().st_mtime)
    hhmm = mtime.strftime("%H%M")
    audio_filename = f"{mtime.strftime('%Y-%m-%d')} {hhmm} {tipo}.m4a"
    meta = NoteMeta(
        tipo=tipo,
        data=mtime.strftime("%Y-%m-%d"),
        hora_inicio=mtime.strftime("%H:%M"),
        duracao_min=max(1, round(duration / 60)),
        origem=origem,
        audio_filename=audio_filename,
        audio_hash=file_sha1(audio_path),
    )
    return write_note(cfg, meta, summary, transcript, audio_path)
