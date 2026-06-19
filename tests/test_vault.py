from pathlib import Path
from voxlog.config import Config
from voxlog.summarize import Summary
from voxlog.vault import NoteMeta, slugify, note_filename, render_note, write_note


def _meta(**kw):
    base = dict(tipo="reuniao", data="2026-06-18", hora_inicio="14:30",
                duracao_min=40, origem="Zoom",
                audio_filename="2026-06-18 1430 reuniao.m4a", audio_hash="abc123")
    base.update(kw)
    return NoteMeta(**base)


def _summary():
    return Summary(resumo="Resumo X", assunto="Planejamento Sprint 12",
                   tags=["reuniao", "projeto-x"], participantes=["João"],
                   acoes=["Enviar ata"], resumido_por="codex")


def test_slugify():
    assert slugify("Planejamento Sprint 12!") == "planejamento-sprint-12"


def test_note_filename():
    fn = note_filename(_meta(), "Planejamento Sprint 12")
    assert fn == "2026-06-18 1430 — Reunião — Planejamento Sprint 12.md"


def test_render_note_tem_frontmatter_e_secoes():
    md = render_note(_meta(), _summary(), "transcricao completa aqui")
    assert md.startswith("---\n")
    assert "tipo: reuniao" in md
    assert 'assunto: "Planejamento Sprint 12"' in md
    assert "resumido_por: codex" in md
    assert "## 📌 Resumo" in md
    assert "- [ ] Enviar ata" in md
    assert "transcricao completa aqui" in md


def test_write_note_cria_arquivo_e_move_audio(tmp_path):
    vault = tmp_path / "vault"
    cfg = Config(vault_path=vault, gravacoes_dir="Gravações",
                 audios_dir="Gravações/_audios")
    audio = tmp_path / "src.m4a"
    audio.write_bytes(b"FAKEAUDIO")
    path = write_note(cfg, _meta(), _summary(), "txt", audio)
    assert path.exists()
    assert (vault / "Gravações" / "2026" / "06-Junho").is_dir()
    assert (vault / "Gravações" / "_audios" / "2026-06-18 1430 reuniao.m4a").exists()
    assert not audio.exists()  # movido


def test_write_note_idempotente_por_hash(tmp_path):
    vault = tmp_path / "vault"
    cfg = Config(vault_path=vault, gravacoes_dir="G", audios_dir="G/_audios")
    a1 = tmp_path / "a1.m4a"; a1.write_bytes(b"X")
    p1 = write_note(cfg, _meta(), _summary(), "t", a1)
    a2 = tmp_path / "a2.m4a"; a2.write_bytes(b"X")
    p2 = write_note(cfg, _meta(), _summary(), "t", a2)
    assert p1 == p2  # mesma nota, não duplica


def test_note_filename_sanitiza_assunto_inseguro():
    fn = note_filename(_meta(), "Sprint: Q2/2026")
    assert "/" not in fn
    assert ":" not in fn
    assert fn.endswith(".md")
