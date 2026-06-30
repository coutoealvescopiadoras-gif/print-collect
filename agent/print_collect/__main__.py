from __future__ import annotations

import argparse
from pathlib import Path

from print_collect.collector import run_daemon, run_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Print Collect Agent")
    parser.add_argument(
        "-c",
        "--config",
        default="config.yaml",
        help="Caminho do arquivo config.yaml",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Testa a conexao e executa uma coleta unica",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Executa apenas uma coleta unica",
    )
    args = parser.parse_args()

    config_path = Path(args.config)

    if args.test or args.once:
        run_once(config_path)
        return

    run_daemon(config_path)


if __name__ == "__main__":
    main()
