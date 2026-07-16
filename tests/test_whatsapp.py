import sqlite3
from datetime import datetime

from voxlog.config import load_config, Config
from voxlog.summarize import Summary
from voxlog.whatsapp import (
    ChatDay, WaMessage, read_chat_days, default_yesterday, process_whatsapp_day,
)


# ---------- config ----------

def test_config_secao_whatsapp(tmp_path):
    p = tmp_path / "voxlog.toml"
    p.write_text(
        'vault_path = "/tmp/v"\n\n[whatsapp]\n'
        'messages_db = "~/wa/messages.db"\n'
        'bridge_url = "http://localhost:9999/api"\n'
        'notes_dir = "WA"\n'
        'exclude_chats = ["123@g.us"]\n'
    )
    cfg = load_config(p)
    assert str(cfg.whatsapp_db).endswith("/wa/messages.db")   # ~ expandido
    assert cfg.whatsapp_bridge_url == "http://localhost:9999/api"
    assert cfg.whatsapp_notes_dir == "WA"
    assert cfg.whatsapp_exclude_chats == ["123@g.us"]


def test_config_whatsapp_defaults(tmp_path):
    cfg = load_config(tmp_path / "inexistente.toml")
    assert cfg.whatsapp_notes_dir == "🎙️ WhatsApp"
    assert cfg.whatsapp_exclude_chats == []


# ---------- leitura do SQLite do bridge ----------

def _mk_db() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE chats (jid TEXT, name TEXT)")
    con.execute("CREATE TABLE senders "
                "(jid TEXT, push_name TEXT, full_name TEXT, business_name TEXT)")
    con.execute("CREATE TABLE messages (id TEXT, chat_jid TEXT, sender TEXT, "
                "is_from_me INT, timestamp TEXT, content TEXT, media_type TEXT, "
                "filename TEXT)")
    con.execute("INSERT INTO chats VALUES ('c1@s.whatsapp.net', 'Fulano')")
    con.execute("INSERT INTO senders VALUES "
                "('s1@s.whatsapp.net', 'push', 'Fulano Silva', '')")
    rows = [
        # dentro do dia alvo
        ("m1", "c1@s.whatsapp.net", "s1@s.whatsapp.net", 0,
         "2026-07-13 09:05:00-03:00", "oi", "", ""),
        ("m2", "c1@s.whatsapp.net", "s1@s.whatsapp.net", 0,
         "2026-07-13 09:06:00-03:00", "", "audio", "a.ogg"),
        ("m3", "c1@s.whatsapp.net", "", 1,
         "2026-07-13 09:07:00-03:00", "beleza", "", ""),
        # dia seguinte — NÃO deve entrar (mesmo perto da meia-noite/offset)
        ("m4", "c1@s.whatsapp.net", "s1@s.whatsapp.net", 0,
         "2026-07-14 08:00:00-03:00", "amanhã", "", ""),
        # chat excluído (broadcast) — nunca entra
        ("m5", "status@broadcast", "s1@s.whatsapp.net", 0,
         "2026-07-13 10:00:00-03:00", "spam", "", ""),
    ]
    con.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return con


def test_read_chat_days_filtra_por_data_e_exclui():
    con = _mk_db()
    cfg = Config()
    days = read_chat_days(cfg, "2026-07-13", connect=lambda _p: con)
    assert len(days) == 1                      # só c1; broadcast excluído
    cd = days[0]
    assert cd.chat_name == "Fulano"
    assert len(cd.messages) == 3               # m4 (dia seguinte) fora
    assert len(cd.audios) == 1                 # m2
    assert cd.participants == ["Fulano Silva"]  # 'Eu' (is_from_me) não conta


def test_read_chat_days_respeita_exclude_chats():
    con = _mk_db()
    cfg = Config()
    cfg.whatsapp_exclude_chats = ["c1@s.whatsapp.net"]
    days = read_chat_days(cfg, "2026-07-13", connect=lambda _p: con)
    assert days == []


def test_default_yesterday():
    hoje = datetime(2026, 7, 15, 8, 0, 0)
    assert default_yesterday(hoje) == "2026-07-14"


# ---------- orquestração ponta-a-ponta (com dependências fakeadas) ----------

def _chatday(date_str: str) -> ChatDay:
    ts = datetime(2026, 7, 13, 9, 6, 0)
    return ChatDay(
        chat_jid="c1@s.whatsapp.net", chat_name="Fulano", date=date_str,
        messages=[
            WaMessage("m1", "c1@s.whatsapp.net", "Fulano", False, ts, "oi", "", ""),
            WaMessage("m2", "c1@s.whatsapp.net", "Fulano", False, ts, "", "audio", "a.ogg"),
        ])


def test_process_whatsapp_day_gera_notas_e_digest(tmp_path):
    cfg = Config()
    cfg.vault_path = tmp_path
    calls = {"summarize": 0, "transcribe": 0}

    def fake_summarize(_text, _cfg):
        calls["summarize"] += 1
        return Summary(assunto="Assunto X", resumo="um resumo",
                       acoes=["ligar pro Fulano"], resumido_por="fake",
                       tags=["trabalho"], participantes=["Fulano"])

    def fake_transcribe(_p, _cfg):
        calls["transcribe"] += 1
        return "conteúdo do áudio"

    kw = dict(
        _read=lambda _cfg, d: [_chatday(d)],
        _download=lambda _a, _cfg: tmp_path / "a.ogg",
        _transcribe=fake_transcribe,
        _summarize=fake_summarize,
    )
    out = process_whatsapp_day(cfg, "2026-07-13", **kw)

    # 1 nota de chat + 1 digest
    assert len(out) == 2
    assert all(p.exists() for p in out)
    nota = next(p for p in out if "Fulano" in p.name)
    texto = nota.read_text(encoding="utf-8")
    assert "tipo: whatsapp" in texto
    assert "Assunto X" in texto
    assert "conteúdo do áudio" in texto      # transcrição embutida
    digest = next(p for p in out if "Digest" in p.name)
    assert "Assunto X" in digest.read_text(encoding="utf-8")
    assert calls == {"summarize": 1, "transcribe": 1}

    # re-execução: reaproveita a nota completa, NÃO regasta codex/whisper
    process_whatsapp_day(cfg, "2026-07-13", **kw)
    assert calls == {"summarize": 1, "transcribe": 1}
