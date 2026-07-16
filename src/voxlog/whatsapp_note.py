from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from .config import Config
from .summarize import Summary
from .whatsapp import ChatDay
from .vault import _MESES, _safe_assunto, _link_assunto


@dataclass
class WaNoteResult:
    path: Path
    chat_name: str
    assunto: str
    acoes: list[str] = field(default_factory=list)
    qtd_audios: int = 0


def wa_note_filename(date_str: str, chat_name: str) -> str:
    return f"{date_str} — WhatsApp — {_safe_assunto(chat_name)}.md"


def _wa_month_dir(cfg: Config, date_str: str) -> Path:
    year, month, _ = date_str.split("-")
    return cfg.vault_path / cfg.whatsapp_notes_dir / year / _MESES[int(month)]


def render_chat_note(chatday: ChatDay, summary: Summary,
                     audio_transcripts: list[tuple[str, str]]) -> str:
    tags = "[" + ", ".join(f'"{t}"' for t in [*summary.tags, "whatsapp"]) + "]"
    parts = "[" + ", ".join(f'"{p}"' for p in summary.participantes) + "]"
    acoes = "\n".join(f"- [ ] {a}" for a in summary.acoes) or "- (nenhum)"
    fm = (
        "---\n"
        "tipo: whatsapp\n"
        f"data: {chatday.date}\n"
        f'chat: "{_safe_assunto(chatday.chat_name)}"\n'
        f"chat_jid: {chatday.chat_jid}\n"
        "origem: whatsapp-corporativo\n"
        f'assunto: "{summary.assunto}"\n'
        f"tags: {tags}\n"
        f"participantes: {parts}\n"
        f"resumido_por: {summary.resumido_por}\n"
        f"qtd_mensagens: {len(chatday.messages)}\n"
        f"qtd_audios: {len(audio_transcripts)}\n"
        "---\n\n"
    )
    if audio_transcripts:
        audios_md = "\n\n".join(
            f"> [!quote]- Áudio {hora}\n" + "\n".join(f"> {ln}" for ln in (txt.splitlines() or [""]))
            for hora, txt in audio_transcripts)
    else:
        audios_md = "(nenhum áudio)"
    log_lines = []
    for m in chatday.messages:
        if m.media_type == "audio":
            corpo = "🎙️ (áudio)"
        elif m.media_type:
            corpo = f"({m.media_type})"
        else:
            corpo = m.content.replace("\n", " ")
        log_lines.append(f"> {m.timestamp.strftime('%H:%M')} — {m.sender_name}: {corpo}")
    body = (
        f"Assunto: [[{_link_assunto(summary.assunto)}]]\n\n"
        "## 📌 Resumo\n\n"
        f"{summary.resumo or '(sem resumo — reprocessar)'}\n\n"
        "## ✅ Pendências / Itens de ação\n\n"
        f"{acoes}\n\n"
        "## 🗣️ Áudios transcritos\n\n"
        f"{audios_md}\n\n"
        "## 📝 Log de mensagens\n\n"
        "> [!note]- Conversa completa\n"
        + "\n".join(log_lines) + "\n"
    )
    return fm + body


def chat_note_path(cfg: Config, date_str: str, chat_name: str) -> Path:
    return _wa_month_dir(cfg, date_str) / wa_note_filename(date_str, chat_name)


def note_is_complete(path: Path) -> bool:
    """False se a nota foi escrita sem resumo (codex E claude falharam) — assim
    uma re-execução refaz a nota em vez de pulá-la pelo short-circuit."""
    return "resumido_por: nenhum" not in path.read_text(encoding="utf-8")


def result_from_note(path: Path, chat_name: str) -> WaNoteResult:
    """Reconstrói um WaNoteResult a partir de uma nota já escrita — usado em
    re-execuções para regenerar o digest sem reprocessar (sem gastar codex)."""
    text = path.read_text(encoding="utf-8")
    assunto = ""
    qtd_audios = 0
    acoes: list[str] = []
    in_pend = False
    for line in text.splitlines():
        if line.startswith("assunto:"):
            assunto = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("qtd_audios:"):
            try:
                qtd_audios = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("## ✅"):
            in_pend = True
        elif in_pend and line.startswith("## "):
            in_pend = False
        elif in_pend and line.startswith("- [ ] "):
            item = line[6:].strip()
            if item and item != "(nenhum)":
                acoes.append(item)
    return WaNoteResult(path=path, chat_name=chat_name, assunto=assunto,
                        acoes=acoes, qtd_audios=qtd_audios)


def write_chat_note(cfg: Config, chatday: ChatDay, summary: Summary,
                    audio_transcripts: list[tuple[str, str]]) -> Path:
    folder = _wa_month_dir(cfg, chatday.date)
    folder.mkdir(parents=True, exist_ok=True)
    note_path = folder / wa_note_filename(chatday.date, chatday.chat_name)
    if note_path.exists():
        return note_path
    note_path.write_text(render_chat_note(chatday, summary, audio_transcripts),
                         encoding="utf-8")
    return note_path


def _wikilink(path: Path) -> str:
    return path.stem


def render_digest(date_str: str, results: list[WaNoteResult]) -> str:
    fm = (
        "---\n"
        "tipo: whatsapp-digest\n"
        f"data: {date_str}\n"
        f"qtd_chats: {len(results)}\n"
        "---\n\n"
    )
    pend_lines = []
    for r in results:
        link = _wikilink(r.path)
        for a in r.acoes:
            pend_lines.append(f"- [ ] {a} (de [[{link}]])")
    pend = "\n".join(pend_lines) or "- (nenhuma pendência identificada)"
    conv_lines = []
    for r in results:
        link = _wikilink(r.path)
        sufixo = f" ({r.qtd_audios} áudios)" if r.qtd_audios else ""
        conv_lines.append(f"- [[{link}]] — {r.assunto}{sufixo}")
    conv = "\n".join(conv_lines) or "- (nenhuma conversa)"
    body = (
        f"# WhatsApp — {date_str}\n\n"
        "## ⚠️ Pendências do dia (consolidado)\n\n"
        f"{pend}\n\n"
        "## 💬 Conversas do dia\n\n"
        f"{conv}\n"
    )
    return fm + body


def write_digest(cfg: Config, date_str: str, results: list[WaNoteResult]) -> Path:
    folder = cfg.vault_path / cfg.whatsapp_notes_dir / "_digests"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{date_str} — WhatsApp Digest.md"
    path.write_text(render_digest(date_str, results), encoding="utf-8")
    return path
