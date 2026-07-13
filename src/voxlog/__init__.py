from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("voxlog")
except PackageNotFoundError:      # rodando do source, sem instalar
    __version__ = "0.0.0+dev"

__all__ = ["__version__"]
