"""Caminhos padrão, neutros e portáveis.

Antes os defaults do Config apontavam para a máquina do autor
(/Volumes/SSD/Dropbox/... e /home/jv/...), o que quebrava qualquer instalação
de terceiro. Aqui eles passam a derivar do ambiente do usuário.
"""
from __future__ import annotations

import os
from pathlib import Path


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "voxlog"


def data_home() -> Path:
    return Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    ) / "voxlog"


def default_config_file() -> Path:
    return config_home() / "voxlog.toml"


def default_staging_dir() -> Path:
    """Segmentos temporários de gravação."""
    return data_home() / "staging"


def default_vault_path() -> Path:
    """Chute razoável para o vault do Obsidian — o usuário confirma no `voxlog init`."""
    for candidate in (
        Path.home() / "Obsidian",
        Path.home() / "Documents" / "Obsidian",
    ):
        if candidate.is_dir():
            return candidate
    return Path.home() / "Obsidian"
