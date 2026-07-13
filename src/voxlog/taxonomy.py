"""Classificação de notas e correção de vocabulário.

O modelo sozinho confunde a FERRAMENTA usada numa reunião com o ASSUNTO dela: uma
call sobre a fila de demandas de um cliente que menciona muito "review", "plugin" e
"Jira" acaba classificada como reunião de produto interno. A saída é dar a ele um
vocabulário fechado (as SUAS entidades) e uma regra explícita separando as duas coisas.

Nada aqui é hardcoded: clientes, produtos e correções vêm do voxlog.toml do usuário.
"""
from __future__ import annotations

import re

NATUREZAS = ("cliente", "produto-interno", "gestao", "comercial", "pessoal")


def fix_transcript(texto: str, correcoes: dict[str, str]) -> str:
    """Aplica o glossário ao texto bruto, antes de resumir.

    Determinístico de propósito: nome próprio da operação (cliente, produto, ferramenta)
    não deveria depender do humor do LLM. Casa palavra inteira, ignorando maiúsculas.
    """
    for errado, certo in (correcoes or {}).items():
        texto = re.sub(rf"\b{re.escape(errado)}\b", certo, texto, flags=re.IGNORECASE)
    return texto


def taxonomy_block(clientes: list[str], produtos: list[str]) -> str:
    """Trecho do prompt que ensina o vocabulário do usuário. Vazio se ele não configurou."""
    if not clientes and not produtos:
        return ""

    linhas = ["", 'VOCABULÁRIO DA OPERAÇÃO (use exatamente estes nomes em "entidade"):']
    if clientes:
        linhas.append(f"- Clientes: {', '.join(clientes)}")
    if produtos:
        linhas.append(f"- Produtos internos: {', '.join(produtos)}")
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
