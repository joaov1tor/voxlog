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

    ps = sub.add_parser("process-session", help="processa os segmentos de uma sessão")
    ps.add_argument("session_id")
    ps.add_argument("--staging", default="/Volumes/SSD/Gravacoes/staging")
    ps.add_argument("--tipo", default="reuniao", choices=["nota", "reuniao"])
    ps.add_argument("--origem", default="manual")
    ps.add_argument("--local", action="store_true")
    ps.add_argument("--config", default=str(_DEFAULT_CFG))

    args = parser.parse_args(argv)
    cfg = load_config(Path(args.config))

    if args.cmd == "process":
        try:
            out = process_audio(Path(args.audio), args.tipo, args.origem, cfg,
                                force_local=args.local)
        except Exception as e:
            print(f"voxlog: erro ao processar '{args.audio}': {e}", file=sys.stderr)
            return 1
        if out is None:
            print("descartado (clipe curto)")
            return 0
        print(str(out))
        return 0

    if args.cmd == "process-session":
        from .session import process_session
        try:
            out = process_session(args.staging, args.session_id, args.tipo,
                                  args.origem, cfg, force_local=args.local)
        except Exception as e:
            print(f"voxlog: erro na sessão '{args.session_id}': {e}", file=sys.stderr)
            return 1
        if out is None:
            print("descartado (sessão curta/sem segmentos)")
            return 0
        print(str(out))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
