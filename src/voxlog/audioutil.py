from __future__ import annotations
import shutil
import subprocess
import tempfile
from pathlib import Path


def _default_runner(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou: {proc.stderr[:300]}")


def combine_segments(segs: list[Path], dest: Path, runner=None) -> Path:
    """Concatena os segmentos .m4a (em ordem) num único arquivo `dest` via
    ffmpeg concat demuxer. Se houver 1 segmento, copia direto."""
    segs = [Path(s) for s in segs]
    if len(segs) == 1:
        shutil.copyfile(segs[0], dest)
        return dest
    run = runner or _default_runner
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for s in segs:
            f.write(f"file '{s.resolve()}'\n")
        listfile = f.name
    try:
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile,
             "-c", "copy", str(dest)])
    finally:
        Path(listfile).unlink(missing_ok=True)
    return dest


def trim_silence(src: Path, dest: Path, *, threshold: str = "-35dB",
                 min_sec: float = 2.0, keep: float = 0.3, runner=None) -> Path:
    """Remove trechos de silêncio >= `min_sec` (mantém `keep`s de padding em cada
    corte) e reencoda para mp3 mono 16kHz 32kbps. Dead air é o que faz Whisper/Gemini
    LOOPAR e o ElevenLabs ALUCINAR — remover mata os dois problemas e ainda corta custo.
    Também comprime a linha do tempo: os timestamps do STT passam a ser 'tempo de fala'."""
    src, dest = Path(src), Path(dest)
    run = runner or _default_runner
    filt = (f"silenceremove=stop_periods=-1:stop_duration={min_sec}:"
            f"stop_threshold={threshold}:stop_silence={keep}")
    run(["ffmpeg", "-y", "-i", str(src), "-af", filt,
         "-ac", "1", "-ar", "16000", "-b:a", "32k", str(dest)])
    return dest
