from __future__ import annotations
import json
import subprocess
from dataclasses import dataclass, field
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


def _default_runner(cmd: list[str], input_text: str) -> str:
    proc = subprocess.run(
        cmd, input=input_text, capture_output=True, text=True, timeout=180
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{cmd[0]} falhou: {proc.stderr[:200]}")
    return proc.stdout


def _codex_cmd(cfg: Config) -> list[str]:
    cmd = ["codex", "exec", "--skip-git-repo-check"]
    if cfg.codex_model:
        cmd += ["-m", cfg.codex_model]
    cmd.append("-")
    return cmd


def _ollama_cmd(cfg: Config) -> list[str]:
    return ["ollama", "run", cfg.ollama_model]


def summarize(transcript: str, cfg: Config, force_local: bool = False, runner=None) -> Summary:
    run = runner or _default_runner
    prompt = build_prompt(transcript)

    backends: list[tuple[str, list[str]]] = []
    if force_local or cfg.summarizer == "ollama":
        backends.append(("ollama", _ollama_cmd(cfg)))
    else:
        backends.append(("codex", _codex_cmd(cfg)))
        backends.append(("ollama", _ollama_cmd(cfg)))

    for name, cmd in backends:
        try:
            raw = run(cmd, prompt)
            return parse_summary_json(raw, name)
        except Exception:
            continue
    return Summary(resumido_por="nenhum")
