from __future__ import annotations
import argparse
import sys
from pathlib import Path
from . import __version__, paths, update as update_mod
from .config import load_config
from .process import process_audio

_DEFAULT_CFG = paths.default_config_file()

# comandos que não carregam config nem checam versão nova
_STANDALONE = {"init", "update"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voxlog")
    parser.add_argument("--version", action="version",
                        version=f"voxlog {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="cria o arquivo de configuração do usuário")
    pi.add_argument("--config", default=str(_DEFAULT_CFG))
    pi.add_argument("--force", action="store_true", help="sobrescreve config existente")

    sub.add_parser("update", help="atualiza o voxlog para a última versão")

    p = sub.add_parser("process", help="processa um áudio em nota do Obsidian")
    p.add_argument("audio")
    p.add_argument("--tipo", default="nota", choices=["nota", "reuniao"])
    p.add_argument("--origem", default="manual")
    p.add_argument("--local", action="store_true", help="força resumo local (ollama)")
    p.add_argument("--config", default=str(_DEFAULT_CFG))

    ps = sub.add_parser("process-session", help="processa os segmentos de uma sessão")
    ps.add_argument("session_id")
    ps.add_argument("--staging", default=None,
                    help="pasta de staging (padrão: a do config)")
    ps.add_argument("--tipo", default="reuniao", choices=["nota", "reuniao"])
    ps.add_argument("--origem", default="manual")
    ps.add_argument("--local", action="store_true")
    ps.add_argument("--config", default=str(_DEFAULT_CFG))

    pvb = sub.add_parser("voice-backfill", help="re-diariza reuniões passadas")
    pvb.add_argument("--config", default=str(_DEFAULT_CFG))
    pvs = sub.add_parser("voice-status", help="status do perfil de voz/diarização")
    pvs.add_argument("--config", default=str(_DEFAULT_CFG))

    args = parser.parse_args(argv)

    if args.cmd == "init":
        from . import initcmd
        return initcmd.run(Path(args.config), force=args.force)

    if args.cmd == "update":
        return update_mod.self_update()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(
            f"voxlog: configuração não encontrada em {cfg_path}.\n"
            f"        rode `voxlog init` para criá-la.",
            file=sys.stderr,
        )
        return 1
    cfg = load_config(cfg_path)

    try:
        return _dispatch(args, cfg)
    finally:
        if args.cmd not in _STANDALONE:
            update_mod.notify_if_outdated()


def _dispatch(args, cfg) -> int:
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
        staging = args.staging or str(cfg.staging_dir)
        try:
            out = process_session(staging, args.session_id, args.tipo,
                                  args.origem, cfg, force_local=args.local)
        except Exception as e:
            print(f"voxlog: erro na sessão '{args.session_id}': {e}", file=sys.stderr)
            return 1
        if out is None:
            print("descartado (sessão curta/sem segmentos)")
            return 0
        print(str(out))
        return 0

    if args.cmd == "voice-backfill":
        from . import voice_backfill
        notas = voice_backfill.backfill(cfg)
        print(f"{len(notas)} notas re-diarizadas")
        for n in notas:
            print(str(n))
        return 0

    if args.cmd == "voice-status":
        print(f"voice_enabled: {cfg.voice_enabled}")
        print(f"diarize_endpoint: {cfg.voice_diarize_endpoint}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
