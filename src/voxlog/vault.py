from __future__ import annotations
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from .config import Config
from .summarize import Summary

_MESES = ["", "01-Janeiro", "02-Fevereiro", "03-Março", "04-Abril", "05-Maio",
          "06-Junho", "07-Julho", "08-Agosto", "09-Setembro", "10-Outubro",
          "11-Novembro", "12-Dezembro"]
_TIPO_LABEL = {"reuniao": "Reunião", "nota": "Nota"}


@dataclass
class NoteMeta:
    tipo: str
    data: str            # YYYY-MM-DD
    hora_inicio: str     # HH:MM
    duracao_min: int
    origem: str
    audio_filename: str
    audio_hash: str


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[\s_]+", "-", s)


def _safe_assunto(assunto: str) -> str:
    # remove caracteres inválidos em nomes de arquivo, mantendo legibilidade
    cleaned = re.sub(r'[/\\:*?"<>|]', "-", assunto)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Sem assunto"


def note_filename(meta: NoteMeta, assunto: str) -> str:
    hhmm = meta.hora_inicio.replace(":", "")
    label = _TIPO_LABEL.get(meta.tipo, meta.tipo.capitalize())
    assunto = _safe_assunto(assunto)
    return f"{meta.data} {hhmm} — {label} — {assunto}.md"


def _link_assunto(assunto: str) -> str:
    # remove caracteres que quebram wikilink; mantém o texto p/ o nó do grafo
    s = re.sub(r"[\[\]|#^]", "", assunto).strip()
    return s or "Sem assunto"


def _yaml_list(items: list[str]) -> str:
    return "[" + ", ".join(f'"{i}"' for i in items) + "]"


def render_note(meta: NoteMeta, summary: Summary, transcript: str) -> str:
    tags = _yaml_list(summary.tags)
    parts = _yaml_list(summary.participantes)
    ferramentas = _yaml_list(summary.ferramentas)
    acoes = "\n".join(f"- [ ] {a}" for a in summary.acoes) or "- (nenhum)"
    decisoes = "\n".join(f"- {d}" for d in summary.decisoes) or "- (nenhuma registrada)"
    fm = (
        "---\n"
        f"tipo: {meta.tipo}\n"
        f"data: {meta.data}\n"
        f'hora_inicio: "{meta.hora_inicio}"\n'
        f"duracao_min: {meta.duracao_min}\n"
        f"origem: {meta.origem}\n"
        f'assunto: "{summary.assunto}"\n'
        f"natureza: {summary.natureza or '""'}\n"
        f'entidade: "{summary.entidade}"\n'
        f"ferramentas: {ferramentas}\n"
        f"tags: {tags}\n"
        f"participantes: {parts}\n"
        f"resumido_por: {summary.resumido_por}\n"
        f"audio_hash: {meta.audio_hash}\n"
        f'audio: "[[{meta.audio_filename}]]"\n'
        "---\n\n"
    )
    # a entidade vira link do grafo: é ela que agrupa "tudo do cliente X"
    entidade_link = f"Entidade: [[{_link_assunto(summary.entidade)}]]\n" if summary.entidade else ""
    body = (
        f"Assunto: [[{_link_assunto(summary.assunto)}]]\n"
        f"{entidade_link}\n"
        "## 📌 Resumo\n\n"
        f"{summary.resumo or '(sem resumo — reprocessar)'}\n\n"
        "## ✅ Itens de ação\n\n"
        f"{acoes}\n\n"
        "## 🗣️ Tópicos e decisões\n\n"
        f"{decisoes}\n\n"
        "## 📝 Transcrição completa\n\n"
        "> [!quote]- Transcrição\n"
        + "\n".join(f"> {line}" for line in transcript.splitlines() or [""])
        + "\n"
    )
    return fm + body


def _month_dir(cfg: Config, data: str) -> Path:
    year, month, _ = data.split("-")
    return cfg.vault_path / cfg.gravacoes_dir / year / _MESES[int(month)]


def _find_existing(cfg: Config, audio_hash: str) -> Path | None:
    base = cfg.vault_path / cfg.gravacoes_dir
    if not base.exists():
        return None
    for md in base.rglob("*.md"):
        if f"audio_hash: {audio_hash}\n" in md.read_text(encoding="utf-8"):
            return md
    return None


def write_note(cfg: Config, meta: NoteMeta, summary: Summary,
               transcript: str, audio_src: Path) -> Path:
    existing = _find_existing(cfg, meta.audio_hash)
    if existing is not None:
        return existing

    folder = _month_dir(cfg, meta.data)
    folder.mkdir(parents=True, exist_ok=True)
    note_path = folder / note_filename(meta, summary.assunto)
    note_path.write_text(render_note(meta, summary, transcript), encoding="utf-8")

    audios = cfg.vault_path / cfg.audios_dir
    audios.mkdir(parents=True, exist_ok=True)
    dest = audios / meta.audio_filename
    shutil.move(str(audio_src), str(dest))
    return note_path
