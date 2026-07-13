from voxlog import taxonomy
from voxlog.config import Config
from voxlog.summarize import parse_summary_json

CLIENTES = ["CASSI", "Ocampo", "Lívio"]
PRODUTOS = ["Agente de Pagamento", "AgentOS"]


def test_entidade_conhecida_passa():
    assert taxonomy.valid_entidade("CASSI", CLIENTES, PRODUTOS) == "CASSI"
    assert taxonomy.valid_entidade("AgentOS", CLIENTES, PRODUTOS) == "AgentOS"


def test_entidade_ignora_caixa_e_acento():
    assert taxonomy.valid_entidade("cassi", CLIENTES, PRODUTOS) == "CASSI"
    assert taxonomy.valid_entidade("livio", CLIENTES, PRODUTOS) == "Lívio"


def test_entidade_inventada_vira_vazio():
    # caso real: o modelo devolveu "TBC" (a própria empresa) como entidade
    assert taxonomy.valid_entidade("TBC", CLIENTES, PRODUTOS) == ""
    assert taxonomy.valid_entidade("Reunião interna", CLIENTES, PRODUTOS) == ""


def test_entidade_com_sufixo_casa_pelo_nome():
    # "CASSI - Interno" ainda é CASSI
    assert taxonomy.valid_entidade("CASSI - Interno", CLIENTES, PRODUTOS) == "CASSI"


def test_sem_vocabulario_aceita_o_que_vier():
    # usuário que não configurou taxonomia não deve perder o campo
    assert taxonomy.valid_entidade("Qualquer Coisa", [], []) == "Qualquer Coisa"


def test_parse_filtra_entidade_pelo_config():
    cfg = Config()
    cfg.clientes = CLIENTES
    cfg.produtos = PRODUTOS
    bom = '{"resumo": "r", "assunto": "a", "natureza": "cliente", "entidade": "CASSI"}'
    ruim = '{"resumo": "r", "assunto": "a", "natureza": "cliente", "entidade": "TBC"}'
    assert parse_summary_json(bom, "t", cfg).entidade == "CASSI"
    assert parse_summary_json(ruim, "t", cfg).entidade == ""


def test_parse_sem_cfg_mantem_compatibilidade():
    raw = '{"resumo": "r", "assunto": "a", "entidade": "Seja o que for"}'
    assert parse_summary_json(raw, "t").entidade == "Seja o que for"
