"""Loop principal do agente de coleta."""

from __future__ import annotations

import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from print_collect.config import AgentConfig, load_config
from print_collect.sender import ApiSender
from print_collect.snmp import collect_all
from print_collect.usb import collect_all_usb

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

    # ==============================================================
    # NOVO (Julio 06/09: IMPRESSORAS MANUAIS EM SUB-REDES DIFERENTES!)
    # Baixa IPs adicionais direto do servidor (endpoint novo
    # /api/agent/extra-targets, ja autenticado via X-Agent-Token).
    #
    # 🔒 SEGURANCA 100% ADITIVA (NAO QUEBRA NADA!):
    #   - Chama fetch_extra_targets() que internamente TEM try/except TOTAL.
    #   - Qualquer erro (servidor antigo sem endpoint, rede, timeout...)
    #       => retorna lista vazia, log warning apenas, NAO ABORTA CICLO!
    #   - Existe FEATURE FLAG de emergencia PRINTCOLLECT_DISABLE_EXTRA_TARGETS=1
    #       para DESATIVAR TUDO e voltar comportamento 100% original.
    # ==============================================================
    try:
        extra_ips = sender.fetch_extra_targets()
        if extra_ips:
            # Adiciona aos IPs fixos ja configurados, SEM duplicatas!
            existing_lower = {str(ip).strip().lower() for ip in (snmp.ips or [])}
            added_count = 0
            # Nao queremos alterar a lista original sem necessidade
            new_ips = list(snmp.ips or [])
            for extra in extra_ips:
                if extra.strip().lower() not in existing_lower:
                    new_ips.append(extra)
                    existing_lower.add(extra.strip().lower())
                    added_count += 1
            if added_count > 0:
                snmp.ips = new_ips
                logger.info(
                    "[extra-targets] Adicionados %d IP(s) do servidor na lista de alvos SNMP. Total IPs agora: %d.",
                    added_count,
                    len(snmp.ips),
                )
    except Exception as exc_top:
        # Ultima camada de protecao: NUNCA deixa erro escapar aqui!
        logger.warning(
            "[extra-targets] Erro ao integrar IPs extras (ignorado, coleta normal continua 100%% ok): %s",
            exc_top,
        )

    readings = collect_all(snmp.subnets, snmp.ips, snmp.community, snmp.timeout)

    # ==============================================================
    # COLETA USB (Windows spooler/WMI) - 100% ADITIVA, NUNCA QUEBRA NADA!
    #
    # 🔒 FEATURE FLAG (POR SEGURANCA, DESLIGADA POR PADRAO!):
    #    A coleta USB SÓ ira rodar se existir a VARIAVEL DE AMBIENTE:
    #         PRINTCOLLECT_ENABLE_USB = 1 (ou "true"/"yes"/"sim")
    #    Se a variavel NAO EXISTIR (padrao) ou for 0/off = PULA TUDO!
    #    Assim, 100% IGUAL ao que ja estava rodando certinho sem USB.
    #
    # Para ativar depois (na maquina do cliente):
    #   - Painel de Controle > Sistema > Variaveis de Ambiente > Sistema > Nova
    #   - Ou: CMD > setx PRINTCOLLECT_ENABLE_USB 1 /M (rebootar depois)
    # ==============================================================
    _usb_env = str(os.environ.get("PRINTCOLLECT_ENABLE_USB") or "").strip().lower()
    _usb_enabled = _usb_env in ("1", "true", "yes", "sim", "on", "s")
    if not _usb_enabled:
        logger.debug("Coleta USB: DESLIGADA (default, 100% modo SNMP original). Para ligar: variavel PRINTCOLLECT_ENABLE_USB=1.")
    else:
        logger.info("Coleta USB: LIGADA (PRINTCOLLECT_ENABLE_USB=%s). Rodando agora...", _usb_env)
        try:
            usb_list = collect_all_usb()
            if usb_list:
                seen_serial: set[str] = set()
                for r in readings:
                    sn = (r.serial_number or "").strip().lower()
                    if sn:
                        seen_serial.add(sn)
                for u in usb_list:
                    usn = (u.serial_number or "").strip().lower()
                    if usn and usn in seen_serial:
                        logger.info("USB: impressora serial=%s ja coletada via SNMP, ignorada.", usn)
                        continue
                    readings.append(u)
                    logger.info("USB OK: %s %s pag=%s", u.ip_address, u.model or "", u.pages_total)
            else:
                logger.info("Coleta USB: Nenhuma impressora USB fisica encontrada neste ciclo (normal).")
        except Exception as usb_err:
            logger.warning("Coleta USB falhou neste ciclo (ignorado, SNMP continua 100% ok): %s", usb_err)

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
