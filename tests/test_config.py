from pathlib import Path
from voxlog.config import load_config, Config


def test_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "inexistente.toml")
    assert isinstance(cfg, Config)
    assert cfg.summarizer == "codex"
    assert cfg.whisper_model == "medium"
    assert cfg.min_duration_sec == 5.0
    assert cfg.whisper_language is None


def test_loads_and_overrides(tmp_path):
    p = tmp_path / "voxlog.toml"
    p.write_text(
        'vault_path = "~/V"\n'
        'summarizer = "ollama"\n'
        'whisper_language = "pt"\n'
        'min_duration_sec = 3\n'
        'ignored_apps = ["Banco"]\n'
    )
    cfg = load_config(p)
    assert cfg.summarizer == "ollama"
    assert cfg.whisper_language == "pt"
    assert cfg.min_duration_sec == 3.0
    assert cfg.ignored_apps == ["Banco"]
    assert str(cfg.vault_path).endswith("/V")  # ~ expandido
