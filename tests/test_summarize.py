import json
import pytest
from voxlog.config import Config
from voxlog.summarize import Summary, parse_summary_json, summarize, build_prompt, summarize_segments

PAYLOAD = {
    "resumo": "Discutiu-se o sprint.",
    "assunto": "Planejamento Sprint 12",
    "tags": ["reuniao", "projeto-x"],
    "participantes": ["João", "Maria"],
    "acoes": ["Enviar ata"],
}


def test_build_prompt_inclui_transcricao_e_pede_json():
    p = build_prompt("ola mundo")
    assert "ola mundo" in p
    assert "JSON" in p


def test_parse_extrai_json_com_lixo_em_volta():
    raw = "Claro!\n```json\n" + json.dumps(PAYLOAD) + "\n```\nfim"
    s = parse_summary_json(raw, "codex")
    assert s.assunto == "Planejamento Sprint 12"
    assert s.tags == ["reuniao", "projeto-x"]
    assert s.resumido_por == "codex"


def test_summarize_usa_codex_por_padrao():
    cfg = Config(summarizer="codex")
    calls = []

    def runner(cmd, input_text):
        calls.append(cmd[0])
        return json.dumps(PAYLOAD)

    s = summarize("t", cfg, runner=runner)
    assert s.resumido_por == "codex"
    assert calls[0] == "codex"


def test_summarize_codex_falha_nao_cai_no_ollama():
    # usuário não quer ollama local (trava o Mac): codex falha -> "nenhum"
    cfg = Config(summarizer="codex")
    used = []

    def runner(cmd, input_text):
        used.append(cmd[0])
        raise RuntimeError("offline")

    s = summarize("t", cfg, runner=runner)
    assert used == ["codex"]            # NÃO tenta ollama
    assert s.resumido_por == "nenhum"


def test_force_local_pula_codex():
    cfg = Config(summarizer="codex")
    used = []

    def runner(cmd, input_text):
        used.append(cmd[0])
        return json.dumps(PAYLOAD)

    summarize("t", cfg, force_local=True, runner=runner)
    assert used == ["ollama"]


def test_tudo_falha_retorna_nenhum():
    cfg = Config(summarizer="codex")

    def runner(cmd, input_text):
        raise RuntimeError("boom")

    s = summarize("t", cfg, runner=runner)
    assert s.resumido_por == "nenhum"
    assert s.resumo == ""


def test_codex_cmd_inclui_modelo_na_ordem_correta():
    from voxlog.summarize import _codex_cmd
    cmd = _codex_cmd(Config(codex_model="gpt-x"))
    assert cmd[:3] == ["codex", "exec", "--skip-git-repo-check"]
    assert cmd[-1] == "-"
    assert "gpt-x" in cmd and cmd[cmd.index("-m") + 1] == "gpt-x"


def test_parse_pega_primeiro_objeto_balanceado():
    raw = 'lixo {"resumo": "a", "assunto": "b", "tags": [], "participantes": [], "acoes": []} e mais {"outro": 1}'
    s = parse_summary_json(raw, "codex")
    assert s.resumo == "a"
    assert s.assunto == "b"


def test_summarize_segments_um_so_delega():
    cfg = Config(summarizer="codex")
    def runner(cmd, input_text):
        return json.dumps(PAYLOAD)
    s = summarize_segments(["transcricao unica"], cfg, runner=runner)
    assert s.assunto == "Planejamento Sprint 12"
    assert s.resumido_por == "codex"


def test_summarize_segments_combina_varios():
    cfg = Config(summarizer="codex")
    calls = []
    final = {"resumo": "resumo final", "assunto": "Reuniao Longa",
             "tags": ["x"], "participantes": ["Ana"], "acoes": ["fazer y"]}
    def runner(cmd, input_text):
        calls.append(input_text)
        # 2 parciais + 1 final = 3 chamadas; a final recebe os parciais juntos
        return json.dumps(final)
    s = summarize_segments(["seg1", "seg2"], cfg, runner=runner)
    assert len(calls) == 3                      # 2 segmentos + combine
    assert s.assunto == "Reuniao Longa"
    assert s.resumido_por == "codex"
