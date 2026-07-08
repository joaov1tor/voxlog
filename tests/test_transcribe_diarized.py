from pathlib import Path
from voxlog.config import Config
from voxlog.transcribe import transcribe_diarized


def test_transcribe_diarized_monta_url_e_extrai_text(tmp_path):
    audio = tmp_path / "reuniao.m4a"; audio.write_bytes(b"X")
    cfg = Config(voice_diarize_endpoint="http://localhost:5051")
    captured = {}
    def fake_curl(cmd):
        captured["cmd"] = cmd
        return '{"language":"pt","speakers":["Eu","Falante 2"],"text":"**Eu** [00:03]: oi\\n**Falante 2** [00:11]: ola","segments":[]}'
    out = transcribe_diarized(audio, cfg, curl=fake_curl)
    assert out == "**Eu** [00:03]: oi\n**Falante 2** [00:11]: ola"
    assert "http://localhost:5051/v1/audio/diarize" in captured["cmd"]
    assert f"file=@{audio}" in captured["cmd"]
