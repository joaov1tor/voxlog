from voxlog import taxonomy
from voxlog.config import Config
from voxlog.summarize import build_prompt, parse_summary_json


def test_fix_transcript_corrige_nome_do_cliente():
    correcoes = {"CACI": "CASSI", "Proteus": "Protheus", "Gira": "Jira"}
    texto = "a CACI cobrou o pacote do Proteus e o ticket ficou no Gira"
    assert taxonomy.fix_transcript(texto, correcoes) == \
        "a CASSI cobrou o pacote do Protheus e o ticket ficou no Jira"


def test_fix_transcript_ignora_maiusculas_mas_respeita_palavra_inteira():
    correcoes = {"caci": "CASSI"}
    # "caciques" NÃO deve virar "CASSIques"
    assert taxonomy.fix_transcript("os caciques da caci", correcoes) == "os caciques da CASSI"


def test_fix_transcript_sem_glossario_nao_altera():
    assert taxonomy.fix_transcript("texto original", {}) == "texto original"


def test_taxonomy_block_vazio_quando_nao_configurado():
    assert taxonomy.taxonomy_block([], []) == ""


def test_taxonomy_block_lista_entidades_e_regra():
    bloco = taxonomy.taxonomy_block(["CASSI", "Lívio"], ["AgentOS"])
    assert "CASSI" in bloco and "Lívio" in bloco and "AgentOS" in bloco
    assert "ferramenta é o MEIO" in bloco


def test_valid_natureza_rejeita_valor_inventado():
    assert taxonomy.valid_natureza("cliente") == "cliente"
    assert taxonomy.valid_natureza("CLIENTE") == "cliente"
    assert taxonomy.valid_natureza("inovação") == ""     # fora do enum → vazio


def test_build_prompt_injeta_vocabulario_do_config():
    cfg = Config()
    cfg.clientes = ["CASSI"]
    cfg.produtos = ["Agente de Pagamento"]
    prompt = build_prompt("transcrição qualquer", cfg)
    assert "CASSI" in prompt
    assert "Agente de Pagamento" in prompt
    assert '"natureza"' in prompt


def test_build_prompt_sem_config_nao_quebra():
    assert "transcrição qualquer" in build_prompt("transcrição qualquer")


def test_parse_summary_json_le_campos_novos():
    raw = """{"resumo": "r", "assunto": "a", "natureza": "cliente",
              "entidade": "CASSI", "ferramentas": ["jira"], "tags": [],
              "participantes": [], "decisoes": ["decidiu X"], "acoes": []}"""
    s = parse_summary_json(raw, "teste")
    assert s.natureza == "cliente"
    assert s.entidade == "CASSI"
    assert s.ferramentas == ["jira"]
    assert s.decisoes == ["decidiu X"]


def test_parse_summary_json_natureza_invalida_vira_vazio():
    raw = '{"resumo": "r", "assunto": "a", "natureza": "inovacao"}'
    assert parse_summary_json(raw, "teste").natureza == ""


def test_parse_summary_json_compativel_com_resposta_antiga():
    # modelo que não devolve os campos novos não pode quebrar o pipeline
    raw = '{"resumo": "r", "assunto": "a", "tags": [], "participantes": [], "acoes": []}'
    s = parse_summary_json(raw, "teste")
    assert s.natureza == "" and s.entidade == "" and s.decisoes == []
