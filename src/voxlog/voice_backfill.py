from __future__ import annotations
import re
from pathlib import Path
from .config import Config
from .transcribe import diarize as _do_diarize


def find_meeting_notes(cfg: Config) -> list[Path]:
    base = cfg.vault_path / cfg.gravacoes_dir
    out = []
    if not base.exists():
        return out
    for md in base.rglob("*.md"):
        head = md.read_text(encoding="utf-8")[:400]
        if re.search(r"^tipo:\s*reuniao\s*$", head, re.MULTILINE):
            out.append(md)
    return sorted(out)


def note_audio_path(cfg: Config, note_path: Path) -> Path | None:
    md = note_path.read_text(encoding="utf-8")
    m = re.search(r'^audio:\s*"\[\[(.+?)\]\]"', md, re.MULTILINE)
    if not m:
        return None
    p = cfg.vault_path / cfg.audios_dir / m.group(1)
    return p if p.exists() else None


def is_diarized(md: str) -> bool:
    return re.search(r"^diarizado:\s*true\s*$", md, re.MULTILINE) is not None


def replace_transcript(md: str, diarized: str) -> str:
    bloco = ("## 📝 Transcrição completa\n\n"
             "> [!quote]- Transcrição (diarizada)\n"
             + "\n".join(f"> {ln}" for ln in diarized.splitlines() or [""]) + "\n")
    # troca tudo a partir do header de transcrição até o fim
    md = re.sub(r"## 📝 Transcrição completa.*\Z", bloco, md, flags=re.DOTALL)
    # marca diarizado: true no frontmatter (após a linha tipo:)
    if not is_diarized(md):
        md = re.sub(r"(^tipo:\s*reuniao\s*$)", r"\1\ndiarizado: true",
                    md, count=1, flags=re.MULTILINE)
    return md


def backfill(cfg: Config, *, _diarize=None) -> list[Path]:
    diarize = _diarize or _do_diarize
    atualizadas = []
    for note in find_meeting_notes(cfg):
        md = note.read_text(encoding="utf-8")
        if is_diarized(md):
            continue
        audio = note_audio_path(cfg, note)
        if audio is None:
            continue
        try:
            diarized = diarize(audio, cfg)
        except Exception:
            continue
        note.write_text(replace_transcript(md, diarized), encoding="utf-8")
        atualizadas.append(note)
    return atualizadas
