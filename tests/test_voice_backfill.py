from pathlib import Path
from voxlog.config import Config
from voxlog.voice_backfill import (find_meeting_notes, note_audio_path,
                                   replace_transcript, is_diarized, backfill)

NOTE = """---
tipo: reuniao
data: 2026-06-20
audio: "[[2026-06-20 1400 reuniao.m4a]]"
---

## 📌 Resumo

resumo aqui

## 📝 Transcrição completa

> [!quote]- Transcrição
> tudo misturado sem rótulo
"""


def _setup(tmp_path):
    cfg = Config(vault_path=tmp_path / "v", gravacoes_dir="G", audios_dir="G/_audios")
    folder = cfg.vault_path / "G" / "2026" / "06-Junho"
    folder.mkdir(parents=True)
    note = folder / "2026-06-20 1400 — Reunião — X.md"
    note.write_text(NOTE, encoding="utf-8")
    audios = cfg.vault_path / "G/_audios"; audios.mkdir(parents=True)
    (audios / "2026-06-20 1400 reuniao.m4a").write_bytes(b"A")
    return cfg, note


def test_find_e_audio(tmp_path):
    cfg, note = _setup(tmp_path)
    notes = find_meeting_notes(cfg)
    assert note in notes
    assert note_audio_path(cfg, note).name == "2026-06-20 1400 reuniao.m4a"


def test_replace_transcript_e_marca(tmp_path):
    novo = replace_transcript(NOTE, "**Eu** [00:01]: oi")
    assert "diarizado: true" in novo
    assert "Transcrição (diarizada)" in novo
    assert "**Eu** [00:01]: oi" in novo
    assert "tudo misturado sem rótulo" not in novo
    assert is_diarized(novo) is True


def test_backfill_diariza_e_idempotente(tmp_path):
    cfg, note = _setup(tmp_path)
    chamadas = []
    def fake_diarize(audio, cfg, **kw):
        chamadas.append(Path(audio).name)
        return "**Eu** [00:01]: oi\n**Falante 2** [00:05]: ola"
    out = backfill(cfg, _diarize=fake_diarize)
    assert out == [note]
    assert "**Eu** [00:01]: oi" in note.read_text(encoding="utf-8")
    # 2ª passada: já diarizada -> não chama de novo
    out2 = backfill(cfg, _diarize=fake_diarize)
    assert out2 == []
    assert len(chamadas) == 1


def test_cli_voice_backfill(tmp_path, monkeypatch, capsys):
    import voxlog.cli as cli
    cfg_file = tmp_path / "voxlog.toml"
    cfg_file.write_text(f'vault_path = "{tmp_path}/v"\n[voice]\nenabled = true\n')
    chamado = {}
    def fake_backfill(cfg, **kw):
        chamado["ok"] = True
        return [tmp_path / "n1.md", tmp_path / "n2.md"]
    monkeypatch.setattr("voxlog.voice_backfill.backfill", fake_backfill)
    rc = cli.main(["voice-backfill", "--config", str(cfg_file)])
    assert rc == 0 and chamado["ok"]
    assert "2" in capsys.readouterr().out
