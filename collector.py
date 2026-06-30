"""Loop principal do agente de coleta."""

from __future__ import annotations

import logging
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from print_collect.config import AgentConfig, load_config
from print_collect.sender import ApiSender
from print_collect.snmp import collect_all

logger = logging.getLogger("print-collect-agent")


def setup_logging(log_file: str | None = None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True,
    )


def run_cycle(config: AgentConfig, sender: ApiSender) -> int:
    snmp = config.snmp
    readings = collect_all(snmp.subnets, snmp.ips, snmp.community, snmp.timeout)

    if not readings:
        logger.warning("Nenhuma impressora encontrada neste ciclo.")
        sender.heartbeat()
        return 0

    sender.send_readings(readings, config.agent_version)
    return len(readings)


def run_once(config_path: Path) -> None:
    config = load_config(config_path)
    setup_logging(config.log_file)
    sender = ApiSender(config.server_url, config.agent_token)

    if not sender.test_connection():
        sys.exit(1)

    count = run_cycle(config, sender)
    logger.info("Coleta única concluída — %d impressora(s).", count)


def run_daemon(config_path: Path) -> None:
    config = load_config(config_path)
    setup_logging(config.log_file)
    sender = ApiSender(config.server_url, config.agent_token)

    if not sender.test_connection():
        sys.exit(1)

    interval = config.interval_minutes * 60
    logger.info(
        "Agente Print Collect v%s iniciado — intervalo: %d min",
        config.agent_version,
        config.interval_minutes,
    )

    while True:
        try:
            run_cycle(config, sender)
        except Exception:
            logger.exception("Erro no ciclo de coleta")
        time.sleep(interval)
