from voxlog.config import Config
from voxlog.transcribe import (transcribe_elevenlabs_diarized, diarize,
                               _words_to_transcript)


def _fake_response():
    # 2 falantes, com 'spacing' entre palavras (formato real do Scribe)
    words = [
        {"type": "word", "text": "Oi", "start": 3.0, "end": 3.4, "speaker_id": "speaker_0"},
        {"type": "spacing", "text": " ", "start": 3.4, "end": 3.5, "speaker_id": "speaker_0"},
        {"type": "word", "text": "tudo", "start": 3.5, "end": 3.8, "speaker_id": "speaker_0"},
        {"type": "word", "text": "Ola", "start": 11.0, "end": 11.5, "speaker_id": "speaker_1"},
    ]
    return '{"language_code":"por","words":' + __import__("json").dumps(words) + '}'


def test_words_to_transcript_agrupa_por_falante():
    words = __import__("json").loads(_fake_response())["words"]
    out = _words_to_transcript(words)
    assert out == "**Falante 1** [00:03]: Oi tudo\n**Falante 2** [00:11]: Ola"


def test_transcribe_elevenlabs_trima_e_envia(tmp_path):
    audio = tmp_path / "reuniao.m4a"; audio.write_bytes(b"X" * 10)
    cfg = Config(elevenlabs_model="scribe_v1", whisper_language="pt")
    trimmed = {}

    def fake_runner(cmd):  # ffmpeg do trim_silence
        trimmed["cmd"] = cmd
        # cria o arquivo de saída que o ffmpeg produziria (penúltimo/último arg)
        out = cmd[-1]
        __import__("pathlib").Path(out).write_bytes(b"TRIMMED")

    captured = {}

    def fake_curl(cmd):
        captured["cmd"] = cmd
        return _fake_response()

    out = transcribe_elevenlabs_diarized(audio, cfg, curl=fake_curl, runner=fake_runner)
    assert out == "**Falante 1** [00:03]: Oi tudo\n**Falante 2** [00:11]: Ola"
    # trimou o silêncio antes de enviar
    assert "silenceremove" in " ".join(trimmed["cmd"])
    # enviou ao ElevenLabs com diarize e model corretos
    joined = " ".join(captured["cmd"])
    assert "diarize=true" in joined
    assert "model_id=scribe_v1" in joined
    assert "language_code=pt" in joined


def test_diarize_dispatcher_escolhe_provider(tmp_path):
    audio = tmp_path / "r.m4a"; audio.write_bytes(b"X")
    # whisperx -> bate no :5051
    cfg_wx = Config(voice_diarize_provider="whisperx",
                    voice_diarize_endpoint="http://localhost:5051")
    seen = {}

    def curl_wx(cmd):
        seen["url"] = [c for c in cmd if "5051" in c or "diarize" in c]
        return '{"text":"**Eu** [00:00]: oi"}'

    assert diarize(audio, cfg_wx, curl=curl_wx) == "**Eu** [00:00]: oi"
    assert any("5051" in u for u in seen["url"])
