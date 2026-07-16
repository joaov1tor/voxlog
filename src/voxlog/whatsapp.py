from __future__ import annotations
import json
import sqlite3
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from .config import Config
from .transcribe import transcribe as _do_transcribe
from .summarize import summarize as _do_summarize

_EXCLUDE_SUFFIXES = ("@broadcast", "@newsletter")


@dataclass
class WaMessage:
    msg_id: str
    chat_jid: str
    sender_name: str
    is_from_me: bool
    timestamp: datetime
    content: str
    media_type: str
    filename: str


@dataclass
class ChatDay:
    chat_jid: str
    chat_name: str
    date: str
    messages: list[WaMessage] = field(default_factory=list)

    @property
    def audios(self) -> list[WaMessage]:
        return [m for m in self.messages if m.media_type == "audio"]

    @property
    def participants(self) -> list[str]:
        seen: list[str] = []
        for m in self.messages:
            if not m.is_from_me and m.sender_name and m.sender_name not in seen:
                seen.append(m.sender_name)
        return seen


def _ro_connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    con.execute("PRAGMA busy_timeout=30000")
    return con


def _short_jid(jid: str) -> str:
    return jid.split("@", 1)[0]


def _excluded(jid: str, blocklist: list[str]) -> bool:
    return jid.endswith(_EXCLUDE_SUFFIXES) or jid in blocklist


def _parse_ts(raw: str) -> datetime:
    # timestamps vêm como "2026-06-20 09:05:00-03:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.fromisoformat(raw[:19])


def read_chat_days(cfg: Config, date_str: str, *, connect=None) -> list[ChatDay]:
    con = (connect or _ro_connect)(str(cfg.whatsapp_db))
    try:
        chat_names = {jid: (name or jid) for jid, name in
                      con.execute("SELECT jid, name FROM chats")}
        sender_names = {}
        for jid, push, full, biz in con.execute(
                "SELECT jid, push_name, full_name, business_name FROM senders"):
            sender_names[jid] = full or push or biz or _short_jid(jid)
        # NÃO usar date(timestamp): o SQLite converte o timestamp (que vem com
        # offset local, ex. "...-03:00") para UTC antes de extrair a data, o que
        # joga as mensagens da noite para o dia seguinte. Os 10 primeiros chars do
        # texto são a data LOCAL como gravada — é isso que queremos.
        cur = con.execute(
            "SELECT id, chat_jid, sender, is_from_me, timestamp, content, "
            "media_type, filename FROM messages WHERE substr(timestamp,1,10)=? "
            "ORDER BY timestamp", (date_str,))
        groups: dict[str, ChatDay] = {}
        for mid, cjid, sender, isme, ts, content, mtype, fname in cur:
            if _excluded(cjid, cfg.whatsapp_exclude_chats):
                continue
            cd = groups.get(cjid)
            if cd is None:
                cd = ChatDay(chat_jid=cjid, chat_name=chat_names.get(cjid, cjid),
                             date=date_str)
                groups[cjid] = cd
            cd.messages.append(WaMessage(
                msg_id=mid, chat_jid=cjid,
                sender_name=("Eu" if isme else sender_names.get(sender, _short_jid(sender or ""))),
                is_from_me=bool(isme), timestamp=_parse_ts(ts),
                content=content or "", media_type=mtype or "", filename=fname or ""))
        return list(groups.values())
    finally:
        con.close()


def default_yesterday(today: datetime | None = None) -> str:
    base = today or datetime.now()
    return (base - timedelta(days=1)).strftime("%Y-%m-%d")


def _default_poster(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_audio(msg: WaMessage, cfg: Config, *, poster=None) -> Path | None:
    poster = poster or _default_poster
    url = cfg.whatsapp_bridge_url.rstrip("/") + "/download"
    try:
        result = poster(url, {"message_id": msg.msg_id, "chat_jid": msg.chat_jid})
    except Exception:
        return None
    if result.get("success") and result.get("path"):
        return Path(result["path"])
    return None


def _summary_input(chatday: ChatDay, audio_transcripts: list[tuple[str, str]]) -> str:
    linhas = []
    for m in chatday.messages:
        quem = m.sender_name
        if m.media_type == "audio":
            corpo = "[áudio]"
        elif m.media_type:
            corpo = f"[{m.media_type}]"
        else:
            corpo = m.content
        linhas.append(f"{m.timestamp.strftime('%H:%M')} {quem}: {corpo}")
    bloco_audios = ""
    if audio_transcripts:
        bloco_audios = "\n\nTranscrições dos áudios:\n" + "\n".join(
            f"[{hora}] {txt}" for hora, txt in audio_transcripts)
    return f"Conversa de WhatsApp com {chatday.chat_name}:\n" + "\n".join(linhas) + bloco_audios


def process_whatsapp_day(cfg: Config, date_str: str, *, _read=None, _download=None,
                         _transcribe=None, _summarize=None) -> list[Path]:
    from .whatsapp_note import (write_chat_note, write_digest, WaNoteResult,
                                chat_note_path, result_from_note, note_is_complete)
    read = _read or read_chat_days
    download = _download or download_audio
    transcribe = _transcribe or _do_transcribe
    summarize = _summarize or _do_summarize

    days = read(cfg, date_str)
    results: list[WaNoteResult] = []
    out_paths: list[Path] = []
    for cd in days:
        # já processado num run anterior (catch-up do timer Persistent):
        # reaproveita a nota e NÃO gasta codex/whisper de novo.
        existing = chat_note_path(cfg, cd.date, cd.chat_name)
        if existing.exists():
            if note_is_complete(existing):
                results.append(result_from_note(existing, cd.chat_name))
                out_paths.append(existing)
                continue
            existing.unlink()  # nota sem resumo (codex+claude falharam) -> refaz
        audio_transcripts: list[tuple[str, str]] = []
        for a in cd.audios:
            hora = a.timestamp.strftime("%H:%M")
            path = download(a, cfg)
            if path is None:
                audio_transcripts.append((hora, "[áudio não transcrito]"))
                continue
            try:
                txt = transcribe(Path(path), cfg)
            except Exception:
                txt = "[áudio não transcrito]"
            audio_transcripts.append((hora, txt or "[áudio não transcrito]"))
        summary = summarize(_summary_input(cd, audio_transcripts), cfg)
        note_path = write_chat_note(cfg, cd, summary, audio_transcripts)
        out_paths.append(note_path)
        results.append(WaNoteResult(path=note_path, chat_name=cd.chat_name,
                                    assunto=summary.assunto, acoes=summary.acoes,
                                    qtd_audios=len(audio_transcripts)))
    digest = write_digest(cfg, date_str, results)
    out_paths.append(digest)
    return out_paths
