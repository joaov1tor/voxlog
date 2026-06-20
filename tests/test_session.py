from pathlib import Path
from voxlog.config import Config
from voxlog.summarize import Summary
from voxlog.session import process_session


def _seg(dirp, name):
    p = dirp / name; p.write_bytes(b"AUDIO"); return p


def test_process_session_uma_nota_de_varios_segmentos(tmp_path):
    staging = tmp_path / "staging"; staging.mkdir()
    _seg(staging, "20260620-101500_reuniao_000.m4a")
    _seg(staging, "20260620-101500_reuniao_001.m4a")
    cfg = Config(vault_path=tmp_path / "v", gravacoes_dir="G", audios_dir="G/_audios")
    summ = Summary(resumo="r", assunto="Reuniao Longa", tags=["t"], resumido_por="codex")
    out = process_session(
        staging, "20260620-101500_reuniao", "reuniao", "Zoom", cfg,
        _transcribe=lambda seg, c: f"texto {seg.name}",
        _summarize=lambda trs, c, fl: summ,
        _duration=lambda p, runner=None: 600.0,
    )
    assert out is not None and out.exists()
    body = out.read_text(encoding="utf-8")
    assert "Reuniao Longa" in out.name
    assert "texto 20260620-101500_reuniao_000.m4a" in body  # transcrição concatenada
    assert 'hora_inicio: "10:15"' in body                   # início vem do session id
    assert "duracao_min: 20" in body                        # 2x600s = 1200s = 20min


def test_process_session_descarta_curto(tmp_path):
    staging = tmp_path / "staging"; staging.mkdir()
    _seg(staging, "20260620-101500_nota_000.m4a")
    cfg = Config(vault_path=tmp_path / "v", min_duration_sec=5.0)
    out = process_session(
        staging, "20260620-101500_nota", "nota", "manual", cfg,
        _transcribe=lambda *a, **k: "t",
        _summarize=lambda *a, **k: Summary(),
        _duration=lambda p, runner=None: 2.0,
    )
    assert out is None
    assert not list(staging.glob("*.m4a"))   # segmentos descartados
