from __future__ import annotations
import shutil
from datetime import datetime
from pathlib import Path
from .config import Config
from .transcribe import transcribe as _do_transcribe
from .summarize import summarize_segments as _do_summarize_segments
from .process import file_sha1, audio_duration_sec
from .vault import NoteMeta, write_note


def _session_start(session_id: str) -> datetime:
    # session_id = "YYYYMMDD-HHMMSS_tipo"
    stamp = session_id.split("_")[0]
    return datetime.strptime(stamp, "%Y%m%d-%H%M%S")


def process_session(staging_dir, session_id, tipo, origem, cfg: Config,
                    force_local: bool = False, *, _transcribe=None,
                    _summarize=None, _duration=None) -> Path | None:
    staging = Path(staging_dir)
    segs = sorted(staging.glob(f"{session_id}_*.m4a"))
    if not segs:
        return None
    dur = _duration or audio_duration_sec
    total = sum(dur(s) for s in segs)
    if total < cfg.min_duration_sec:
        for s in segs:
            s.unlink(missing_ok=True)
        return None

    tr = _transcribe or _do_transcribe
    transcripts = [tr(s, cfg) for s in segs]
    full = "\n".join(transcripts)
    summary = (_summarize or _do_summarize_segments)(transcripts, cfg, force_local)

    start = _session_start(session_id)
    audio_filename = f"{start.strftime('%Y-%m-%d %H%M')} {tipo}.m4a"
    meta = NoteMeta(
        tipo=tipo,
        data=start.strftime("%Y-%m-%d"),
        hora_inicio=start.strftime("%H:%M"),
        duracao_min=max(1, round(total / 60)),
        origem=origem,
        audio_filename=audio_filename,
        audio_hash=file_sha1(segs[0]),
    )
    note = write_note(cfg, meta, summary, full, segs[0])  # move segs[0] -> _audios
    # preserva as demais partes em _audios (não perde áudio do restante da reunião)
    audios = cfg.vault_path / cfg.audios_dir
    audios.mkdir(parents=True, exist_ok=True)
    for s in segs[1:]:
        if s.exists():
            shutil.move(str(s), str(audios / s.name))
    return note
