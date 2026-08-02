from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import os
import platform
import sys
import tempfile

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


def default_writable_config_path() -> Path:
    """
    Retorna o PATH PADRAO do config.yaml onde o agente SEMPRE consegue ESCREVER
    (mesmo sem permissao de administrador).
    - Windows: %PROGRAMDATA%\PrintCollect\config.yaml
               (ex: C:\ProgramData\PrintCollect\config.yaml — fora de Program Files)
    - Linux/macOS: ~/.print_collect/config.yaml
    """
    system = platform.system().lower()
    if system == "windows":
        base = os.environ.get("PROGRAMDATA") or r"C:\ProgramData"
        folder = Path(base) / "PrintCollect"
    else:
        folder = Path.home() / ".print_collect"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "config.yaml"


def is_path_writable(path: Path) -> bool:
    """Testa se conseguimos ESCREVER em um path (usando arquivo temporario para nao corromper)."""
    test_file = path.parent / f".write-test-{os.getpid()}.tmp"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with test_file.open("w") as f:
            f.write("ok")
        test_file.unlink(missing_ok=True)
        return True
    except (OSError, PermissionError):
        try:
            test_file.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def load_config(path: Path) -> AgentConfig:
    if not path.exists():
        # Fallback amigavel: tenta buscar no PROGRAMDATA se nao achou no Program Files
        fallback = default_writable_config_path()
        if fallback.exists() and fallback.resolve() != path.resolve():
            return load_config(fallback)
        raise FileNotFoundError(
            f"Configuracao nao encontrada: {path}\n"
            f"Copie config.example.yaml para config.yaml e preencha os valores, "
            f"ou use: python -m print_collect pair"
        )

    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return AgentConfig.from_dict(raw)


def save_config(path: Path, config: AgentConfig) -> Path:
    """
    Salva AgentConfig em arquivo YAML.
    Se der PERMISSION DENIED (erro 13) no caminho original (por exemplo,
    dentro de C:\Program Files), salva automaticamente no caminho GRAVAVEL
    (ProgramData ou home) e retorna esse novo caminho.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                config.to_dict(),
                f,
                sort_keys=False,
                allow_unicode=True,
                width=120,
            )
        return path
    except PermissionError:
        # === FALLBACK: nao consegue escrever em Program Files ===
        writable = default_writable_config_path()
        print(f"[!] Permissao negada ao salvar em: {path}")
        print(f"[!] Salvando automaticamente no caminho gravavel: {writable}")
        writable.parent.mkdir(parents=True, exist_ok=True)
        with writable.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                config.to_dict(),
                f,
                sort_keys=False,
                allow_unicode=True,
                width=120,
            )
        # Tambem salva log_file (se existia) com caminho absoluto para nao perder referencia
        try:
            save_config._last_fallback_path = writable
        except Exception:
            pass
        return writable

