from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SnmpConfig:
    community: str = "public"
    timeout: int = 2
    subnets: list[str] = field(default_factory=list)
    ips: list[str] = field(default_factory=list)


@dataclass
class AgentConfig:
    server_url: str
    agent_token: str
    agent_version: str = "0.2.0"
    interval_minutes: int = 15
    log_file: str | None = None
    snmp: SnmpConfig = field(default_factory=SnmpConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentConfig:
        snmp_raw = data.get("snmp") or {}
        snmp = SnmpConfig(
            community=snmp_raw.get("community", "public"),
            timeout=int(snmp_raw.get("timeout", 2)),
            subnets=list(snmp_raw.get("subnets") or []),
            ips=list(snmp_raw.get("ips") or []),
        )

        server_url = (data.get("server_url") or "").strip()
        agent_token = (data.get("agent_token") or "").strip()

        if not server_url:
            raise ValueError("server_url é obrigatório em config.yaml")
        if not agent_token:
            raise ValueError("agent_token é obrigatório — crie um agente no painel web")

        if not snmp.subnets and not snmp.ips:
            raise ValueError("Configure ao menos uma sub-rede (snmp.subnets) ou IP fixo (snmp.ips)")

        return cls(
            server_url=server_url.rstrip("/"),
            agent_token=agent_token,
            agent_version=data.get("agent_version", "0.2.0"),
            interval_minutes=int(data.get("interval_minutes", 15)),
            log_file=data.get("log_file"),
            snmp=snmp,
        )


def load_config(path: Path) -> AgentConfig:
    if not path.exists():
        raise FileNotFoundError(
            f"Configuração não encontrada: {path}\n"
            f"Copie config.example.yaml para config.yaml e preencha os valores."
        )

    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return AgentConfig.from_dict(raw)
