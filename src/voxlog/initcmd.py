"""`voxlog init` — cria o voxlog.toml do usuário na primeira execução."""
from __future__ import annotations

import sys
from pathlib import Path

from . import paths

_TEMPLATE = """\
# Gerado por `voxlog init`. Ajuste à vontade.

# Vault do Obsidian onde as notas serão criadas.
vault_path = "{vault}"
gravacoes_dir = "🎙️ Gravações"
audios_dir = "🎙️ Gravações/_audios"

# Segmentos temporários durante a gravação.
staging_dir = "{staging}"

# ===== Transcrição =====
# Local (grátis, roda na sua máquina): deixe whisper_endpoint vazio.
#   modelos: tiny < base < small < medium < large-v3
whisper_model = "{whisper_model}"
whisper_language = "{lang}"     # "" = autodetect
# Remoto (mais rápido, não carrega o Mac): serviço compatível com a API OpenAI
#   (/v1/audio/transcriptions). Ex.: "https://meu-servidor:5050"
whisper_endpoint = "{endpoint}"

# ===== Resumo =====
# "codex" (CLI da OpenAI) | "claude" (CLI da Anthropic) | "ollama" (local) | "deepseek"
summarizer = "{summarizer}"
summarizer_fallback = "{fallback}"
ollama_model = "llama3.1:8b"

min_duration_sec = 5.0
"""


def _ask(prompt: str, default: str) -> str:
    try:
        answer = input(f"{prompt} [{default}]: ").strip()
    except EOFError:
        return default
    return answer or default


def run(config_path: Path | None = None, force: bool = False) -> int:
    dest = Path(config_path) if config_path else paths.default_config_file()

    if dest.exists() and not force:
        print(f"voxlog: {dest} já existe. Use --force para sobrescrever.", file=sys.stderr)
        return 1

    print("voxlog init — responda ou aceite os padrões entre colchetes.\n")
    vault = _ask("Pasta do vault do Obsidian", str(paths.default_vault_path()))
    staging = _ask("Pasta de gravações temporárias", str(paths.default_staging_dir()))
    lang = _ask("Idioma do áudio (pt, en, '' p/ autodetect)", "pt")
    endpoint = _ask("Endpoint remoto de Whisper (vazio = transcrever local)", "")
    whisper_model = "medium" if not endpoint else ""
    summarizer = _ask("Resumidor (codex/claude/ollama/deepseek)", "codex")
    fallback = _ask("Resumidor de fallback", "ollama")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        _TEMPLATE.format(
            vault=vault, staging=staging, lang=lang, endpoint=endpoint,
            whisper_model=whisper_model or "medium",
            summarizer=summarizer, fallback=fallback,
        ),
        encoding="utf-8",
    )

    vault_dir = Path(vault).expanduser()
    if not vault_dir.is_dir():
        print(f"\naviso: {vault_dir} não existe ainda — crie o vault ou edite {dest}.")

    print(f"\nconfig criado em {dest}")
    print("teste com:  voxlog process /caminho/audio.m4a --tipo reuniao")
    return 0
