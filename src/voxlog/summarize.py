from __future__ import annotations
import json
import os
import subprocess
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from .config import Config

_PROMPT = """Você é um assistente que resume reuniões e notas de voz em português.
Analise a TRANSCRIÇÃO abaixo e responda APENAS com um objeto JSON válido, sem texto extra,
com exatamente estas chaves:
- "resumo": string (3-6 frases)
- "assunto": string curta (título do tema principal)
- "tags": array de strings curtas em minúsculas (kebab-case)
- "participantes": array de nomes citados (vazio se não houver)
- "acoes": array de itens de ação/próximos passos (vazio se não houver)

TRANSCRIÇÃO:
\"\"\"
{transcript}
\"\"\"
"""


@dataclass
class Summary:
    resumo: str = ""
    assunto: str = ""
    tags: list[str] = field(default_factory=list)
    participantes: list[str] = field(default_factory=list)
    acoes: list[str] = field(default_factory=list)
    resumido_por: str = "nenhum"


def build_prompt(transcript: str) -> str:
    return _PROMPT.format(transcript=transcript)


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


def parse_summary_json(raw: str, resumido_por: str) -> Summary:
    data = json.loads(_extract_first_json_object(raw))
    return Summary(
        resumo=str(data.get("resumo", "")),
        assunto=str(data.get("assunto", "")),
        tags=list(data.get("tags", [])),
        participantes=list(data.get("participantes", [])),
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
    prompt = build_prompt(transcript)
    backends = _backends(cfg, force_local)

    for name, cmd in backends:
        try:
            raw = run(cmd, prompt)
            return parse_summary_json(raw, name)
        except Exception:
            continue
    return Summary(resumido_por="nenhum")


_COMBINE_PROMPT = """Você recebe vários RESUMOS PARCIAIS de segmentos de uma mesma
reunião, em ordem. Combine tudo em UM resumo coeso. Responda APENAS com um objeto
JSON válido com as chaves: "resumo" (string), "assunto" (string curta), "tags"
(array), "participantes" (array), "acoes" (array consolidada).

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
    prompt = _COMBINE_PROMPT.format(parciais="\n\n".join(parciais))
    for name, cmd in backends:
        try:
            return parse_summary_json(run(cmd, prompt), name)
        except Exception:
            continue
    return Summary(resumido_por="nenhum")
