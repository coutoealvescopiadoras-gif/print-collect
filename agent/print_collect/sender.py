"""Envio de dados coletados para a API central (Supabase via backend)."""

from __future__ import annotations

import logging
import os
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

    # =========================================================================
    # NOVO (Julio 06/09: IMPRESSORAS MANUAIS EM SUB-REDES DIFERENTES!)
    # GET /api/agent/extra-targets
    #
    # 🔒 CAMADAS DE SEGURANCA ANTI-QUEBRA (NUNCA QUEBRA a coleta normal!):
    #   1. FEATURE FLAG: se PRINTCOLLECT_DISABLE_EXTRA_TARGETS = 1 (qualquer
    #      valor verdadeiro) => NAO CHAMA NADA, retorna lista vazia.
    #      (comando Windows p/ desativar urgente: setx PRINTCOLLECT_DISABLE_EXTRA_TARGETS 1 /M)
    #   2. Timeout CURTO 8s (nao atrasa a coleta)
    #   3. 1 tentativa so (nao fica retentando)
    #   4. QUALQUER erro: retorna lista vazia, log warning, NAO ABORTA CICLO
    #   5. Backwards compatibility: servidor antigo sem esse endpoint retorna
    #      404 => tratado como erro normal (retorna [], nao quebra nada!)
    # =========================================================================
    def fetch_extra_targets(self) -> list[str]:
        # Camada 1: Feature flag de emergencia (desativa tudo, volta original!)
        _env_disable = str(os.environ.get("PRINTCOLLECT_DISABLE_EXTRA_TARGETS") or "").strip().lower()
        if _env_disable in ("1", "true", "yes", "sim", "on", "s"):
            logger.info("[extra-targets] Desativado por variavel PRINTCOLLECT_DISABLE_EXTRA_TARGETS=%s (modo 100% original).", _env_disable)
            return []

        try:
            url = f"{self.server_url}/api/agent/extra-targets"
            headers = {"X-Agent-Token": self.agent_token}
            # Camada 2: timeout curto, 1 tentativa so
            response = requests.get(url, headers=headers, timeout=8)
            response.raise_for_status()
            data = response.json()

            targets_raw = data.get("extra_targets") or []
            if not isinstance(targets_raw, list):
                logger.warning("[extra-targets] Resposta inesperada (extra_targets nao eh lista). Ignorado.")
                return []

            # Sanitiza
            result = []
            seen = set()
            for t in targets_raw:
                if not isinstance(t, str):
                    continue
                ip = t.strip()
                if not ip:
                    continue
                if ip in seen:
                    continue
                seen.add(ip)
                result.append(ip)

            if result:
                logger.info("[extra-targets] Obtidos %d IPs adicionais do servidor: %s", len(result), result)
            else:
                logger.debug("[extra-targets] Nenhum IP adicional retornado pelo servidor (normal).")
            return result

        except Exception as exc:
            # Camada 3: QUALQUER erro (404 servidor antigo, rede, DNS, timeout...)
            # LOGA apenas WARNING e retorna lista vazia — NAO QUEBRA NADA!
            logger.warning(
                "[extra-targets] Nao foi possivel obter IPs extras (ignorado, coleta normal continua 100%% ok): %s",
                exc,
            )
            return []

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

