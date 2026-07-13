from voxlog import taxonomy
from voxlog.config import Config
from voxlog.summarize import build_prompt

PISTAS = {
    "Lívio": ["check-in", "APK", "fazenda"],
    "Agente de Pagamento": ["SISPAG", "CNAB"],
}


def test_pista_encontrada_mesmo_sem_o_nome_da_entidade():
    # a reunião do cliente fala de check-in e APK, mas nunca diz "Lívio"
    texto = "o registro de check-in vai no grupo 01 e o Thiago manda o APK pra testar"
    achadas = taxonomy.pistas_presentes(texto, PISTAS)
    assert "Lívio" in achadas
    assert set(achadas["Lívio"]) == {"check-in", "APK"}
    assert "Agente de Pagamento" not in achadas


def test_pista_ignora_acento_e_caixa():
    assert "Lívio" in taxonomy.pistas_presentes("mapeamento de CHECK-IN na Fazenda", PISTAS)


def test_sem_pista_nao_inventa():
    assert taxonomy.pistas_presentes("conversa sobre férias", PISTAS) == {}


def test_prompt_inclui_a_pista_encontrada():
    cfg = Config()
    cfg.clientes = ["Lívio"]
    cfg.pistas = PISTAS
    prompt = build_prompt("vamos testar o APK do check-in", cfg)
    assert "PISTAS ENCONTRADAS" in prompt
    assert "entidade provável: Lívio" in prompt


def test_prompt_sem_pistas_nao_traz_a_secao():
    cfg = Config()
    cfg.clientes = ["Lívio"]
    cfg.pistas = PISTAS
    assert "PISTAS ENCONTRADAS" not in build_prompt("assunto totalmente distinto", cfg)


def test_entidade_por_pista_quando_inequivoca():
    # rede de segurança: o LLM deixou entidade vazia, mas a pista é de uma só entidade
    achadas = {"Lívio": ["check-in", "APK"]}
    assert taxonomy.entidade_por_pista(achadas) == "Lívio"


def test_entidade_por_pista_empate_devolve_vazio():
    # duas entidades com pista = ambíguo de verdade; não chutamos
    achadas = {"Lívio": ["check-in"], "Agente de Pagamento": ["CNAB"]}
    assert taxonomy.entidade_por_pista(achadas) == ""


def test_entidade_por_pista_sem_pista():
    assert taxonomy.entidade_por_pista({}) == ""
