from pathlib import Path
from voxlog.config import Config
from voxlog.transcribe import transcribe


def test_transcribe_le_txt_gerado(tmp_path):
    audio = tmp_path / "fala.m4a"
    audio.write_bytes(b"X")
    cfg = Config(whisper_model="tiny")

    def fake_runner(cmd, out_dir):
        # simula o whisper escrevendo <stem>.txt no out_dir
        (Path(out_dir) / "fala.txt").write_text("olá mundo transcrito")

    txt = transcribe(audio, cfg, runner=fake_runner)
    assert txt == "olá mundo transcrito"


def test_transcribe_monta_comando_com_modelo(tmp_path):
    audio = tmp_path / "a.m4a"; audio.write_bytes(b"X")
    cfg = Config(whisper_model="medium", whisper_language="pt")
    captured = {}

    def fake_runner(cmd, out_dir):
        captured["cmd"] = cmd
        (Path(out_dir) / "a.txt").write_text("ok")

    transcribe(audio, cfg, runner=fake_runner)
    assert "whisper" in captured["cmd"][0]
    assert "medium" in captured["cmd"]
    assert "pt" in captured["cmd"]
