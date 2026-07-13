"""Classificação de notas e correção de vocabulário.

O modelo sozinho confunde a FERRAMENTA usada numa reunião com o ASSUNTO dela: uma
call sobre a fila de demandas de um cliente que menciona muito "review", "plugin" e
"Jira" acaba classificada como reunião de produto interno. A saída é dar a ele um
vocabulário fechado (as SUAS entidades) e uma regra explícita separando as duas coisas.

Nada aqui é hardcoded: clientes, produtos e correções vêm do voxlog.toml do usuário.
"""
from __future__ import annotations

import re
import unicodedata

NATUREZAS = ("cliente", "produto-interno", "gestao", "comercial", "pessoal")


def fix_transcript(texto: str, correcoes: dict[str, str]) -> str:
    """Aplica o glossário ao texto bruto, antes de resumir.

    Determinístico de propósito: nome próprio da operação (cliente, produto, ferramenta)
    não deveria depender do humor do LLM. Casa palavra inteira, ignorando maiúsculas.
    """
    for errado, certo in (correcoes or {}).items():
        texto = re.sub(rf"\b{re.escape(errado)}\b", certo, texto, flags=re.IGNORECASE)
    return texto


def pistas_presentes(texto: str, pistas: dict[str, list[str]]) -> dict[str, list[str]]:
    """Quais entidades têm pista no texto, e quais pistas casaram.

    O dono de um cliente raramente é citado nas calls dele: a reunião fala de
    "check-in", "APK" e "fazenda", nunca o nome do cliente. Sem pista, o modelo não
    tem como saber de quem é a conversa — e chuta.
    """
    achadas: dict[str, list[str]] = {}
    alvo = _norm(texto)
    for entidade, termos in (pistas or {}).items():
        casaram = [t for t in termos if _norm(t) in alvo]
        if casaram:
            achadas[entidade] = casaram
    return achadas


def entidade_por_pista(pistas_achadas: dict[str, list[str]]) -> str:
    """Entidade deduzida das pistas, quando elas são inequívocas.

    O LLM é instável: no mesmo texto ele às vezes devolve a entidade e às vezes deixa
    vazio. Quando as pistas apontam para UMA entidade só, isso é determinístico e não
    precisa passar pelo modelo — usamos como rede de segurança.

    Empate (pistas de duas entidades) devolve "": aí é ambíguo de verdade, e o palpite
    do modelo vale mais que o nosso.
    """
    if len(pistas_achadas) == 1:
        return next(iter(pistas_achadas))
    return ""


def taxonomy_block(clientes: list[str], produtos: list[str],
                   pistas_achadas: dict[str, list[str]] | None = None) -> str:
    """Trecho do prompt que ensina o vocabulário do usuário. Vazio se ele não configurou."""
    if not clientes and not produtos:
        return ""

    linhas = ["", 'VOCABULÁRIO DA OPERAÇÃO (use exatamente estes nomes em "entidade"):']
    if clientes:
        linhas.append(f"- Clientes: {', '.join(clientes)}")
    if produtos:
        linhas.append(f"- Produtos internos: {', '.join(produtos)}")

    if pistas_achadas:
        linhas += ["", "PISTAS ENCONTRADAS NESTA TRANSCRIÇÃO (fortes indícios de entidade —",
                   "o nome da entidade pode nem ser dito em voz alta na reunião):"]
        for entidade, termos in pistas_achadas.items():
            linhas.append(f'- menciona {", ".join(repr(t) for t in termos)} → entidade provável: {entidade}')

    linhas += [
        "",
        "COMO DECIDIR A NATUREZA — siga nesta ordem e PARE no primeiro que se aplicar:",
        "",
        "1. A conversa trata do trabalho de um CLIENTE da lista acima — demandas, tickets,",
        '   fila, prazos, entrega, homologação, cobrança dele? Então natureza="cliente" e',
        "   entidade=o nome do cliente. PARE AQUI, mesmo que a maior parte do tempo tenha",
        "   sido gasta explicando ferramentas (plugin, review, IDE, Jira, IA).",
        "",
        "2. Senão: a conversa trata de um PRODUTO INTERNO da lista — o que vamos construir,",
        '   entregar, corrigir ou lançar NELE? Então natureza="produto-interno" e',
        "   entidade=o nome do produto.",
        "",
        '3. Senão: pessoas, metas, orçamento, processo → "gestao".',
        '   Proposta, preço, contrato, churn, venda → "comercial".',
        '   Assunto particular → "pessoal".',
        "",
        "DESEMPATE (o erro mais comum): uma reunião pode gastar 80% do tempo ensinando uma",
        "FERRAMENTA e ainda assim ser natureza=\"cliente\", se o motivo de existir dela é a",
        "entrega de um cliente. Pergunte-se: 'se essa ferramenta não existisse, a reunião",
        "ainda aconteceria?' Se sim, o assunto é o cliente, não a ferramenta.",
        'Toda ferramenta citada vai em "ferramentas" — nunca em "entidade".',
        "",
        'Se nenhuma entidade conhecida aparecer, deixe "entidade" como "".',
    ]
    return "\n".join(linhas)


def valid_natureza(valor: str) -> str:
    v = (valor or "").strip().lower()
    return v if v in NATUREZAS else ""


def _norm(s: str) -> str:
    """Normaliza p/ comparar: sem acento, sem caixa, sem espaço extra."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


def valid_entidade(valor: str, clientes: list[str], produtos: list[str]) -> str:
    """Casa a entidade devolvida pelo modelo com o vocabulário configurado.

    Sem isto o modelo inventa entidade — já apareceu "TBC" (a própria empresa) num
    resumo, num campo que só deveria conter cliente ou produto conhecido. Entidade
    fora do vocabulário vira "": melhor vazio que uma classificação fantasma.

    Sem vocabulário configurado, aceita o que vier (o usuário não opinou).
    """
    conhecidas = [*clientes, *produtos]
    if not conhecidas:
        return (valor or "").strip()

    alvo = _norm(valor)
    if not alvo:
        return ""

    for nome in conhecidas:                       # match exato (ignorando acento/caixa)
        if _norm(nome) == alvo:
            return nome

    for nome in conhecidas:                       # "Agente Pix" -> "Agente de Pagamento"? não.
        n = _norm(nome)                           # mas "CASSI - Interno" -> "CASSI", sim.
        if alvo in n.split() or n in alvo.split():
            return nome

    return ""
