from pathlib import Path
from voxlog.config import Config
from voxlog.summarize import Summary
from voxlog.process import process_audio, file_sha1


def test_descarta_clipe_curto(tmp_path):
    audio = tmp_path / "curto.m4a"; audio.write_bytes(b"X")
    cfg = Config(vault_path=tmp_path / "v", min_duration_sec=5.0)
    out = process_audio(audio, "nota", "manual", cfg,
                        _transcribe=lambda *a, **k: "t",
                        _summarize=lambda *a, **k: Summary(),
                        _duration=lambda p, runner=None: 2.0)
    assert out is None
    assert not audio.exists()  # descartado


def test_processa_e_cria_nota(tmp_path):
    audio = tmp_path / "ok.m4a"; audio.write_bytes(b"AUDIO")
    cfg = Config(vault_path=tmp_path / "v", gravacoes_dir="G", audios_dir="G/_audios")
    summ = Summary(resumo="r", assunto="Tema", tags=["t"], resumido_por="codex")
    out = process_audio(audio, "reuniao", "Zoom", cfg,
                        _transcribe=lambda *a, **k: "transcricao",
                        _summarize=lambda *a, **k: summ,
                        _duration=lambda p, runner=None: 60.0)
    assert out is not None and out.exists()
    assert "Tema" in out.name
    assert "transcricao" in out.read_text(encoding="utf-8")


def test_sha1_estavel(tmp_path):
    p = tmp_path / "a"; p.write_bytes(b"abc")
    assert file_sha1(p) == "a9993e364706816aba3e25717850c26c9cd0d89d"
