from pathlib import Path
from voxlog.config import Config
from voxlog.summarize import Summary
from voxlog.session import process_session


def _segs(staging, sid, n):
    for i in range(1, n + 1):
        (staging / f"{sid}_{i}.m4a").write_bytes(b"A" * 1000)


def test_process_session_reuniao_voz_diariza(tmp_path):
    staging = tmp_path / "stg"; staging.mkdir()
    sid = "20260620-140000_reuniao"
    _segs(staging, sid, 2)
    cfg = Config(vault_path=tmp_path / "vault", voice_enabled=True,
                 gravacoes_dir="G", audios_dir="G/_audios")
    combinados = {}
    def fake_combine(segs, dest, runner=None):
        combinados["n"] = len(segs); dest.write_bytes(b"FULL"); return dest
    def fake_diarize(audio, cfg, **kw):
        return "**Eu** [00:03]: oi\n**Falante 2** [00:10]: ola"
    inputs = []
    def fake_summarize(text, cfg, *a, **k):
        inputs.append(text)
        return Summary(resumo="r", assunto="Reunião X", resumido_por="codex")
    note = process_session(str(staging), sid, "reuniao", "Discord", cfg,
                           _duration=lambda p: 120.0,
                           _combine=fake_combine, _diarize=fake_diarize,
                           _summarize=fake_summarize)
    assert combinados["n"] == 2                       # concatenou os 2 segmentos
    txt = note.read_text(encoding="utf-8")
    assert "**Eu** [00:03]: oi" in txt                # transcrição diarizada na nota
    assert any("Falante 2" in t for t in inputs)      # resumo recebeu o texto inteiro
