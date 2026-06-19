from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .config import load_config
from .process import process_audio

_DEFAULT_CFG = Path("~/.config/voxlog/voxlog.toml").expanduser()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voxlog")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("process", help="processa um áudio em nota do Obsidian")
    p.add_argument("audio")
    p.add_argument("--tipo", default="nota", choices=["nota", "reuniao"])
    p.add_argument("--origem", default="manual")
    p.add_argument("--local", action="store_true", help="força resumo local (ollama)")
    p.add_argument("--config", default=str(_DEFAULT_CFG))

    args = parser.parse_args(argv)
    cfg = load_config(Path(args.config))
    out = process_audio(Path(args.audio), args.tipo, args.origem, cfg,
                        force_local=args.local)
    if out is None:
        print("descartado (clipe curto)")
        return 0
    print(str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
