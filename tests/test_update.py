from voxlog import update


def test_is_newer_compara_semver():
    assert update.is_newer("v0.3.0", "0.2.0")
    assert update.is_newer("0.2.1", "0.2.0")
    assert not update.is_newer("v0.2.0", "0.2.0")
    assert not update.is_newer("v0.1.9", "0.2.0")


def test_is_newer_tolera_versao_de_source():
    # rodando do source, __version__ é "0.0.0+dev" — qualquer release é mais nova
    assert update.is_newer("v0.1.0", "0.0.0+dev")


def test_parse_ignora_sufixos():
    assert update._parse("v1.2.3") == (1, 2, 3)
    assert update._parse("1.2.3-rc1") == (1, 2, 3)
    assert update._parse("0.0.0+dev") == (0, 0, 0)


def test_notify_silencioso_com_env(monkeypatch, capsys):
    monkeypatch.setenv("VOXLOG_NO_UPDATE_CHECK", "1")
    update.notify_if_outdated()
    assert capsys.readouterr().err == ""
