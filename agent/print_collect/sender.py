"""Envio de dados coletados para a API central (Supabase via backend)."""

from __future__ import annotations

import logging
import time

import requests

from print_collect.snmp import PrinterData

logger = logging.getLogger("print-collect-agent")


class ApiSender:
    def __init__(self, server_url: str, agent_token: str, timeout: int = 30, retries: int = 3):
        self.server_url = server_url.rstrip("/")
        self.agent_token = agent_token
        self.timeout = timeout
        self.retries = retries
        self._headers = {"X-Agent-Token": agent_token, "Content-Type": "application/json"}

    def _post(self, path: str, payload: dict | None = None) -> dict:
        url = f"{self.server_url}{path}"
        last_error: Exception | None = None

        for attempt in range(1, self.retries + 1):
            try:
                response = requests.post(
                    url,
                    json=payload or {},
                    headers=self._headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Tentativa %d/%d falhou (%s): %s", attempt, self.retries, path, exc)
                if attempt < self.retries:
                    time.sleep(2 ** attempt)

        raise RuntimeError(f"Falha ao comunicar com {url}: {last_error}")

    def heartbeat(self) -> None:
        result = self._post("/api/agent/heartbeat")
        logger.debug("Heartbeat OK: %s", result)

    def send_readings(self, readings: list[PrinterData], agent_version: str) -> dict:
        payload = {
            "agent_version": agent_version,
            "readings": [
                {
                    "ip_address": r.ip_address,
                    "mac_address": r.mac_address,
                    "serial_number": r.serial_number,
                    "model": r.model,
                    "manufacturer": r.manufacturer,
                    "status": r.status,
                    "pages_total": r.pages_total,
                    "pages_bw": r.pages_bw,
                    "pages_color": r.pages_color,
                    "toner_black": r.toner_black,
                    "toner_cyan": r.toner_cyan,
                    "toner_magenta": r.toner_magenta,
                    "toner_yellow": r.toner_yellow,
                    "alerts": r.alerts,
                }
                for r in readings
            ],
        }

        result = self._post("/api/agent/report", payload)
        logger.info("Enviadas %d leituras — resposta: %s", len(readings), result)
        return result

    def test_connection(self) -> bool:
        try:
            response = requests.get(f"{self.server_url}/health", timeout=10)
            response.raise_for_status()
            logger.info("Servidor acessível: %s", response.json())
            self.heartbeat()
            return True
        except requests.RequestException as exc:
            logger.error("Servidor inacessível: %s", exc)
            return False
