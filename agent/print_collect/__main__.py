"""Ponto de entrada: python -m print_collect"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from print_collect.collector import run_daemon, run_once


def resolve_config_path(config_value: str) -> Path:
    path = Path(config_value)
    if path.is_absolute():
        return path

    candidates = [Path.cwd() / path]

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / path)
    else:
        # Em desenvolvimento, o config.yaml costuma ficar na raiz de `agent/`.
        candidates.append(Path(__file__).resolve().parents[1] / path)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Print Collect — coletor local de impressoras (SNMP → Supabase via API)",
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Caminho do config.yaml (padrão: config.yaml)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Executa uma coleta e encerra (útil para testar)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Testa conexão com o servidor e encerra",
    )
    args = parser.parse_args()
    config_path = resolve_config_path(args.config)

    if args.test:
        from print_collect.config import load_config
        from print_collect.sender import ApiSender

        config = load_config(config_path)
        ok = ApiSender(config.server_url, config.agent_token).test_connection()
        sys.exit(0 if ok else 1)

    if args.once:
        run_once(config_path)
    else:
        run_daemon(config_path)


if __name__ == "__main__":
    main()
