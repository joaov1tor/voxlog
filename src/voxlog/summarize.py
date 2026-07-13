from __future__ import annotations
import json
import os
import subprocess
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from . import taxonomy
from .config import Config

_PROMPT = """Você é um assistente que resume reuniões e notas de voz em português.
Analise a TRANSCRIÇÃO abaixo e responda APENAS com um objeto JSON válido, sem texto extra,
com exatamente estas chaves:
- "resumo": string (3-6 frases)
- "assunto": string curta (título do tema principal)
- "natureza": UMA de ["cliente", "produto-interno", "gestao", "comercial", "pessoal"]
- "entidade": o cliente OU o produto de que a reunião trata ("" se nenhum)
- "ferramentas": array de tecnologias/ferramentas citadas (kebab-case, vazio se não houver)
- "tags": array de strings curtas em minúsculas (kebab-case)
- "participantes": array de nomes citados (vazio se não houver)
- "decisoes": array de decisões explícitas tomadas (vazio se não houver)
- "acoes": array de itens de ação/próximos passos (vazio se não houver)
{taxonomia}
TRANSCRIÇÃO:
\"\"\"
{transcript}
\"\"\"
"""


@dataclass
class Summary:
    resumo: str = ""
    assunto: str = ""
    natureza: str = ""
    entidade: str = ""
    ferramentas: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    participantes: list[str] = field(default_factory=list)
    decisoes: list[str] = field(default_factory=list)
    acoes: list[str] = field(default_factory=list)
    resumido_por: str = "nenhum"


def build_prompt(transcript: str, cfg: Config | None = None) -> str:
    bloco = ""
    if cfg is not None:
        achadas = taxonomy.pistas_presentes(transcript, cfg.pistas)
        bloco = taxonomy.taxonomy_block(cfg.clientes, cfg.produtos, achadas)
    return _PROMPT.format(transcript=transcript, taxonomia=bloco)


def _extract_first_json_object(raw: str) -> str:
    start = raw.find("{")
    if start == -1:
        raise ValueError("nenhum JSON encontrado na saída")
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                return raw[start:i + 1]
    raise ValueError("JSON não balanceado na saída")


def parse_summary_json(raw: str, resumido_por: str, cfg: Config | None = None) -> Summary:
    data = json.loads(_extract_first_json_object(raw))
    clientes = cfg.clientes if cfg else []
    produtos = cfg.produtos if cfg else []
    return Summary(
        resumo=str(data.get("resumo", "")),
        assunto=str(data.get("assunto", "")),
        # natureza fora do enum vira "" — melhor vazio que uma classificação inventada
        natureza=taxonomy.valid_natureza(str(data.get("natureza", ""))),
        # idem para entidade: fora do vocabulário configurado, vira ""
        entidade=taxonomy.valid_entidade(str(data.get("entidade", "")), clientes, produtos),
        ferramentas=list(data.get("ferramentas", [])),
        tags=list(data.get("tags", [])),
        participantes=list(data.get("participantes", [])),
        decisoes=list(data.get("decisoes", [])),
        acoes=list(data.get("acoes", [])),
        resumido_por=resumido_por,
    )


def _openrouter_key() -> str:
    """Chave do OpenRouter. O arquivo dedicado ~/.config/voxlog/openrouter.env
    tem PRIORIDADE sobre a env do shell (que pode estar stale/inválida em outra
    máquina). Fallback p/ a env. NUNCA hardcode/commit a chave."""
    p = Path.home() / ".config" / "voxlog" / "openrouter.env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY="):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                if v:
                    return v
    return os.environ.get("OPENROUTER_API_KEY", "")


def _openrouter_http(model: str, base_url: str, prompt: str, timeout: int = 180) -> str:
    """Chama o OpenRouter (OpenAI-compat) — fallback DeepSeek quando o codex
    estoura cota."""
    key = _openrouter_key()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY ausente (env ou ~/.config/voxlog/openrouter.env)")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    return str(data["choices"][0]["message"]["content"])


def _default_runner(cmd: list[str], input_text: str) -> str:
    if cmd[0] == "openrouter":               # ["openrouter", model, base_url]
        return _openrouter_http(cmd[1], cmd[2], input_text)
    proc = subprocess.run(
        cmd, input=input_text, capture_output=True, text=True, timeout=180
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} falhou: {proc.stderr[:200]}")
    return proc.stdout


def _codex_cmd(cfg: Config) -> list[str]:
    # `-c otel.exporter=none`: desativa o exporter otel (config do usuário estava
    # quebrada — "missing field headers" — e travava o `codex exec`).
    cmd = ["codex", "exec", "--skip-git-repo-check", "-c", "otel.exporter=none"]
    if cfg.codex_model:
        cmd += ["-m", cfg.codex_model]
    cmd.append("-")
    return cmd


def _ollama_cmd(cfg: Config) -> list[str]:
    return ["ollama", "run", cfg.ollama_model]


def _claude_cmd(cfg: Config) -> list[str]:
    # fallback via claude CLI headless (usa a assinatura; sem ANTHROPIC_API_KEY).
    cmd = ["claude", "-p"]
    if cfg.claude_model:
        cmd += ["--model", cfg.claude_model]
    return cmd


def _openrouter_cmd(cfg: Config) -> list[str]:
    # "cmd" sentinela: o runner detecta cmd[0]=="openrouter" e faz HTTP (não subprocess).
    return ["openrouter", cfg.openrouter_model, cfg.openrouter_base_url]


def _backends(cfg: Config, force_local: bool) -> list[tuple[str, list[str]]]:
    """Primário + fallback. Se o codex falhar (ex.: cota estourada), tenta o
    fallback configurado. Sem fallback p/ ollama por padrão (o usuário não quer
    ollama no Mac). 'deepseek'/'openrouter' → DeepSeek V4 Flash via OpenRouter."""
    if force_local or cfg.summarizer == "ollama":
        return [("ollama", _ollama_cmd(cfg))]
    backends = [("codex", _codex_cmd(cfg))]
    fb = cfg.summarizer_fallback
    if fb in ("deepseek", "openrouter"):
        backends.append(("deepseek", _openrouter_cmd(cfg)))
    elif fb == "claude":
        backends.append(("claude", _claude_cmd(cfg)))
    elif fb == "ollama":
        backends.append(("ollama", _ollama_cmd(cfg)))
    return backends


def summarize(transcript: str, cfg: Config, force_local: bool = False, runner=None) -> Summary:
    run = runner or _default_runner
    # corrige o vocabulário ANTES de resumir: o resumo, o assunto e o nome do
    # arquivo derivam daqui, então errar o nome do cliente aqui contamina tudo.
    transcript = taxonomy.fix_transcript(transcript, cfg.glossario)
    prompt = build_prompt(transcript, cfg)
    backends = _backends(cfg, force_local)

    achadas = taxonomy.pistas_presentes(transcript, cfg.pistas)
    for name, cmd in backends:
        try:
            raw = run(cmd, prompt)
            s = parse_summary_json(raw, name, cfg)
            # o modelo é instável: no mesmo texto ele ora devolve a entidade, ora
            # deixa vazio. Se as pistas apontam para uma só, não precisamos dele.
            if not s.entidade:
                s.entidade = taxonomy.entidade_por_pista(achadas)
            return s
        except Exception:
            continue
    return Summary(resumido_por="nenhum")


_COMBINE_PROMPT = """Você recebe vários RESUMOS PARCIAIS de segmentos de uma mesma
reunião, em ordem. Combine tudo em UM resumo coeso. Responda APENAS com um objeto
JSON válido com as chaves: "resumo" (string), "assunto" (string curta), "natureza"
(uma de ["cliente", "produto-interno", "gestao", "comercial", "pessoal"]), "entidade"
(string), "ferramentas" (array), "tags" (array), "participantes" (array), "decisoes"
(array consolidada), "acoes" (array consolidada).
{taxonomia}
RESUMOS PARCIAIS:
\"\"\"
{parciais}
\"\"\"
"""


def summarize_segments(transcripts, cfg, force_local: bool = False, runner=None) -> Summary:
    transcripts = [t for t in transcripts if t and t.strip()]
    if not transcripts:
        return Summary(resumido_por="nenhum")
    if len(transcripts) == 1:
        return summarize(transcripts[0], cfg, force_local=force_local, runner=runner)
    # resume cada segmento, depois combina
    parciais = []
    for t in transcripts:
        s = summarize(t, cfg, force_local=force_local, runner=runner)
        parciais.append(s.resumo or t[:500])
    run = runner or _default_runner
    backends = _backends(cfg, force_local)
    juntos = "\n\n".join(parciais)
    prompt = _COMBINE_PROMPT.format(
        parciais=juntos,
        taxonomia=taxonomy.taxonomy_block(
            cfg.clientes, cfg.produtos, taxonomy.pistas_presentes(juntos, cfg.pistas)
        ),
    )
    achadas = taxonomy.pistas_presentes(juntos, cfg.pistas)
    for name, cmd in backends:
        try:
            s = parse_summary_json(run(cmd, prompt), name, cfg)
            if not s.entidade:
                s.entidade = taxonomy.entidade_por_pista(achadas)
            return s
        except Exception:
            continue
    return Summary(resumido_por="nenhum")
