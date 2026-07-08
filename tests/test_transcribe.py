import json
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


def test_transcribe_remoto_usa_endpoint(tmp_path):
    audio = tmp_path / "fala.m4a"; audio.write_bytes(b"X")
    cfg = Config(whisper_endpoint="https://gpu:5050", whisper_language="pt")
    captured = {}

    def fake_curl(cmd):
        captured["cmd"] = cmd
        return json.dumps({"text": "  transcrito pela GPU  "})

    txt = transcribe(audio, cfg, curl=fake_curl)
    assert txt == "transcrito pela GPU"
    assert any("https://gpu:5050/v1/audio/transcriptions" in c for c in captured["cmd"])
    assert any(c.startswith("file=@") for c in captured["cmd"])


def test_transcribe_remoto_falha_cai_no_openrouter(tmp_path, monkeypatch):
    # avell :5050 falha -> fallback NUVEM (OpenRouter), NÃO local
    audio = tmp_path / "fala.m4a"; audio.write_bytes(b"abc")
    cfg = Config(whisper_endpoint="https://gpu:5050")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")

    def fake_curl(cmd):
        if "openrouter" in " ".join(cmd):
            return '{"text": "transcrito na nuvem"}'
        raise RuntimeError("avell offline")

    assert transcribe(audio, cfg, curl=fake_curl) == "transcrito na nuvem"


def test_transcribe_nunca_roda_local_com_endpoint(tmp_path, monkeypatch):
    # endpoint configurado: remoto E openrouter falham -> "" (NUNCA whisper local CPU)
    audio = tmp_path / "fala.m4a"; audio.write_bytes(b"X")
    cfg = Config(whisper_endpoint="https://gpu:5050")
    monkeypatch.setenv("HOME", str(tmp_path)); monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    def fake_curl(cmd):
        raise RuntimeError("tudo offline")

    def fake_runner(cmd, out_dir):
        (Path(out_dir) / "fala.txt").write_text("LOCAL NÃO DEVE RODAR")

    assert transcribe(audio, cfg, runner=fake_runner, curl=fake_curl) == ""
