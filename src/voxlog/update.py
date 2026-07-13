"""Checagem de versão nova e auto-atualização.

O voxlog é distribuído direto do GitHub (uv tool / pipx), então a "última versão"
é a última release publicada no repositório — não há índice PyPI a consultar.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__

REPO = "joaov1tor/voxlog"
_LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
_GIT_URL = f"git+https://github.com/{REPO}"
_CACHE = Path(
    os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
) / "voxlog" / "update-check.json"
_CHECK_EVERY_SEC = 86_400      # uma vez por dia basta


def _parse(v: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Partes não numéricas viram 0 (ex.: '0.0.0+dev')."""
    core = v.lstrip("v").split("+")[0].split("-")[0]
    out = []
    for part in core.split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    return tuple(out)


def is_newer(remote: str, local: str) -> bool:
    return _parse(remote) > _parse(local)


def _fetch_latest_tag(timeout: float = 3.0) -> str | None:
    req = urllib.request.Request(
        _LATEST_URL, headers={"Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return str(json.load(resp).get("tag_name") or "") or None
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None      # sem rede, sem release, repo privado: silêncio


def _cache_read() -> dict:
    try:
        return json.loads(_CACHE.read_text())
    except (OSError, ValueError):
        return {}


def _cache_write(tag: str) -> None:
    try:
        _CACHE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE.write_text(json.dumps({"tag": tag, "checked_at": time.time()}))
    except OSError:
        pass      # cache é conveniência, nunca motivo de falha


def latest_version(force: bool = False) -> str | None:
    """Última release publicada. Usa cache de 24h para não bater na API a cada run."""
    cached = _cache_read()
    fresh = time.time() - cached.get("checked_at", 0) < _CHECK_EVERY_SEC
    if not force and fresh and cached.get("tag"):
        return str(cached["tag"])

    tag = _fetch_latest_tag()
    if tag:
        _cache_write(tag)
        return tag
    return str(cached.get("tag")) or None


def notify_if_outdated(stream=sys.stderr) -> None:
    """Aviso passivo, uma linha, em stderr — nunca interrompe o comando em curso.

    Silencioso quando VOXLOG_NO_UPDATE_CHECK está definido (útil em cron/launchd).
    """
    if os.environ.get("VOXLOG_NO_UPDATE_CHECK"):
        return
    tag = latest_version()
    if tag and is_newer(tag, __version__):
        print(
            f"voxlog: versão {tag} disponível (você tem {__version__}) "
            f"— atualize com: voxlog update",
            file=stream,
        )


def _installer() -> list[str] | None:
    """Como o voxlog foi instalado? Devolve o comando de upgrade correspondente."""
    if shutil.which("uv"):
        return ["uv", "tool", "upgrade", "voxlog"]
    if shutil.which("pipx"):
        return ["pipx", "upgrade", "voxlog"]
    return None


def self_update() -> int:
    """voxlog update — reinstala a partir do GitHub."""
    cmd = _installer()
    if cmd is None:
        print(
            "voxlog: nem 'uv' nem 'pipx' encontrados. Instale um deles, ou atualize à mão:\n"
            f"  pip install --upgrade {_GIT_URL}",
            file=sys.stderr,
        )
        return 1

    print(f"voxlog {__version__} → atualizando via {cmd[0]}…")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # 'upgrade' falha se o pacote foi instalado por outro caminho; tenta reinstalar.
        fallback = [cmd[0], "tool", "install", "--force", _GIT_URL] if cmd[0] == "uv" \
            else ["pipx", "install", "--force", _GIT_URL]
        proc = subprocess.run(fallback, capture_output=True, text=True)
        if proc.returncode != 0:
            print(f"voxlog: falha ao atualizar:\n{proc.stderr.strip()}", file=sys.stderr)
            return 1

    _cache_write("")      # invalida o cache: a próxima checagem é honesta
    print(proc.stdout.strip() or "atualizado.")
    return 0
