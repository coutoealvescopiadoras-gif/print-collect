"""Envio de dados coletados para a API central (Supabase via backend)."""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

from print_collect.snmp import PrinterData

logger = logging.getLogger("print-collect-agent")


class ApiSender:
    def __init__(self, server_url: str, agent_token: str, timeout: int = 60, retries: int = 5):
        self.server_url = server_url.rstrip("/")
        self.agent_token = agent_token
        self.timeout = timeout
        self.retries = retries
        self._headers = {"X-Agent-Token": agent_token, "Content-Type": "application/json"}

    def _post(self, path: str, payload: dict | None = None, headers: Optional[dict] = None) -> dict:
        url = f"{self.server_url}{path}"
        last_error: Exception | None = None
        merged_headers = {**self._headers, **(headers or {})}

        for attempt in range(1, self.retries + 1):
            try:
                response = requests.post(
                    url,
                    json=payload or {},
                    headers=merged_headers,
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
            # Usa timeout e retries padroes do proprio sender para consistencia:
            last_exc: Exception | None = None
            for attempt in range(1, self.retries + 1):
                try:
                    response = requests.get(f"{self.server_url}/health", timeout=self.timeout)
                    response.raise_for_status()
                    logger.info("Servidor acessível: %s", response.json())
                    self.heartbeat()
                    return True
                except requests.RequestException as exc:
                    last_exc = exc
                    logger.warning("test_connection tentativa %d/%d falhou: %s", attempt, self.retries, exc)
                    if attempt < self.retries:
                        time.sleep(2 ** attempt)
            logger.error("Servidor inacessível (apos %d tentativas): %s", self.retries, last_exc)
            return False
        except Exception as exc_global:
            logger.error("Servidor inacessível: %s", exc_global)
            return False


class PairingClient:
    """Cliente para os endpoints PUBLICOS de pareamento (por código curto ou código do cliente)."""

    def __init__(self, server_url: str, timeout: int = 20):
        self.server_url = server_url.rstrip("/")
        self.timeout = timeout

    def exchange(self, code: str, hostname: Optional[str] = None, version: Optional[str] = None) -> dict:
        url = f"{self.server_url}/api/agents/pairing/exchange"
        payload = {
            "pairing_code": code.strip().upper(),
        }
        if hostname:
            payload["hostname"] = hostname
        if version:
            payload["version"] = version
        response = requests.post(
            url, json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        if 400 <= response.status_code < 500:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise RuntimeError(f"Falha no pareamento ({response.status_code}): {detail}")
        response.raise_for_status()
        return response.json()

    def exchange_client_code(self, client_code: str, hostname: Optional[str] = None, version: Optional[str] = None) -> dict:
        """Tenta o endpoint novo de CÓDIGO DO CLIENTE (fixo, não expira).
        Retorna dicionario com agent_token, client_id, client_name, etc."""
        url = f"{self.server_url}/api/agents/client-code/exchange"
        payload = {
            "client_code": client_code.strip().upper(),
        }
        if hostname:
            payload["hostname"] = hostname
        if version:
            payload["version"] = version
        response = requests.post(
            url, json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        if 400 <= response.status_code < 500:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise RuntimeError(f"Falha no codigo do cliente ({response.status_code}): {detail}")
        response.raise_for_status()
        return response.json()

    def exchange_smart(self, code: str, hostname: Optional[str] = None, version: Optional[str] = None) -> tuple[str, dict]:
        """Tenta PRIMEIRO o endpoint novo de Código do Cliente.
        Se falhar com 404, cai no endpoint antigo de pareamento (TTL).
        Retorna: (nome_rota_usada, payload_resultado)."""
        cleaned = (code or "").strip().upper()
        if not cleaned:
            raise ValueError("Código não informado")
        # 1) Tenta CÓDIGO DO CLIENTE (novo)
        try:
            return ("client_code", self.exchange_client_code(cleaned, hostname=hostname, version=version))
        except Exception as exc:
            msg = str(exc).lower()
            # Se der "codigo do cliente nao encontrado" (404) ou qualquer erro 4xx — tenta modo antigo
            if "nao encontrado" in msg or "not found" in msg or "404" in msg or "invalido" in msg:
                pass  # cai pra baixo
            else:
                # Erro 500 / rede / etc: relança direto
                raise
        # 2) Fallback: endpoint antigo de código de pareamento TTL
        return ("pairing", self.exchange(cleaned, hostname=hostname, version=version))

