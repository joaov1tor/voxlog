import json
import pytest
from voxlog.config import Config
from voxlog.summarize import Summary, parse_summary_json, summarize, build_prompt, summarize_segments


def test_summarize_fallback_codex_para_claude():
    # codex falha (ex.: cota) -> cai para o claude CLI
    cfg = Config(summarizer="codex", summarizer_fallback="claude")
    chamados = []

    def runner(cmd, prompt):
        chamados.append(cmd[0])
        if cmd[0] == "codex":
            raise RuntimeError("rate limit")
        assert cmd[0] == "claude"
        return '{"resumo":"r","assunto":"A","tags":[],"participantes":[],"acoes":[]}'

    s = summarize("transcricao", cfg, runner=runner)
    assert s.resumido_por == "claude"
    assert s.assunto == "A"
    assert chamados == ["codex", "claude"]

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


def test_summarize_codex_falha_cai_no_claude_nao_ollama():
    # codex falha -> tenta claude (fallback), nunca ollama; se ambos falham -> "nenhum"
    cfg = Config(summarizer="codex")   # summarizer_fallback="claude" por padrão
    used = []

    def runner(cmd, input_text):
        used.append(cmd[0])
        raise RuntimeError("offline")

    s = summarize("t", cfg, runner=runner)
    assert used == ["codex", "claude"]   # tenta claude, NÃO ollama
    assert s.resumido_por == "nenhum"    # ambos falharam


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


def test_openrouter_cmd_formato():
    from voxlog.summarize import _openrouter_cmd
    cmd = _openrouter_cmd(Config())
    assert cmd[0] == "openrouter"                          # sentinela p/ o runner HTTP
    assert cmd[1] == "deepseek/deepseek-v4-flash"
    assert cmd[2] == "https://openrouter.ai/api/v1"


def test_codex_falha_cai_no_deepseek():
    # cota do codex acaba -> DeepseekV4 Flash via OpenRouter
    cfg = Config(summarizer="codex", summarizer_fallback="deepseek")
    used = []

    def runner(cmd, input_text):
        used.append(cmd[0])
        if cmd[0] == "codex":
            raise RuntimeError("quota exceeded")
        assert cmd[0] == "openrouter"
        return json.dumps(PAYLOAD)

    s = summarize("t", cfg, runner=runner)
    assert used == ["codex", "openrouter"]   # NÃO tenta claude
    assert s.resumido_por == "deepseek"
    assert s.assunto == "Planejamento Sprint 12"


def test_openrouter_http_usa_chave_e_endpoint(monkeypatch, tmp_path):
    import voxlog.summarize as S
    monkeypatch.setenv("HOME", str(tmp_path))   # sem arquivo dedicado → usa a env
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-teste")
    cap = {}

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return json.dumps({"choices": [{"message": {"content": json.dumps(PAYLOAD)}}]}).encode()

    def fake_urlopen(req, timeout=180):
        cap["url"] = req.full_url
        cap["auth"] = req.headers.get("Authorization")
        return FakeResp()

    monkeypatch.setattr(S.urllib.request, "urlopen", fake_urlopen)
    out = S._openrouter_http("deepseek/deepseek-v4-flash", "https://openrouter.ai/api/v1", "prompt")
    assert json.loads(out)["assunto"] == "Planejamento Sprint 12"
    assert cap["url"].endswith("/chat/completions")
    assert cap["auth"] == "Bearer sk-or-teste"


def test_openrouter_http_sem_chave_levanta(monkeypatch, tmp_path):
    import voxlog.summarize as S
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))   # sem env e sem arquivo de chave
    with pytest.raises(RuntimeError):
        S._openrouter_http("m", "https://x/api/v1", "p")


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
    assert "RESUMOS PARCIAIS" in calls[2]   # 3a chamada = passe de combine
    assert s.assunto == "Reuniao Longa"
    assert s.resumido_por == "codex"
