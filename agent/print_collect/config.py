from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SnmpConfig:
    community: str = "public"
    timeout: int = 2
    subnets: list[str] = field(default_factory=list)
    ips: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "community": self.community,
            "timeout": self.timeout,
            "subnets": list(self.subnets),
            "ips": list(self.ips),
        }


@dataclass
class AgentConfig:
    server_url: str
    agent_token: str
    agent_version: str = "0.3.0"
    interval_minutes: int = 15
    log_file: str | None = None
    snmp: SnmpConfig = field(default_factory=SnmpConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentConfig":
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
            raise ValueError("server_url e obrigatorio em config.yaml")
        if not agent_token:
            raise ValueError("agent_token e obrigatorio — crie um agente no painel web ou use o codigo de pareamento")

        return cls(
            server_url=server_url.rstrip("/"),
            agent_token=agent_token,
            agent_version=data.get("agent_version", "0.3.0"),
            interval_minutes=int(data.get("interval_minutes", 15)),
            log_file=data.get("log_file"),
            snmp=snmp,
        )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "server_url": self.server_url.rstrip("/"),
            "agent_token": self.agent_token,
            "agent_version": self.agent_version,
            "interval_minutes": int(self.interval_minutes),
            "snmp": self.snmp.to_dict(),
        }
        if self.log_file:
            data["log_file"] = self.log_file
        return data


def load_config(path: Path) -> AgentConfig:
    if not path.exists():
        raise FileNotFoundError(
            f"Configuracao nao encontrada: {path}\n"
            f"Copie config.example.yaml para config.yaml e preencha os valores, "
            f"ou use: python -m print_collect pair"
        )

    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return AgentConfig.from_dict(raw)


def save_config(path: Path, config: AgentConfig) -> Path:
    """Salva AgentConfig em arquivo YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            config.to_dict(),
            f,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )
    return path
