"""Coleta de dados de impressoras via SNMP na rede local do cliente."""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("print-collect-agent")

OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
OID_PRINTER_SERIAL = "1.3.6.1.2.1.43.5.1.1.17.1"
OID_PRINTER_MODEL = "1.3.6.1.2.1.25.3.2.1.3.1"
OID_PAGES_TOTAL = "1.3.6.1.2.1.43.10.2.1.4.1.1"
OID_TONER_LEVEL = "1.3.6.1.2.1.43.11.1.1.9.1.1"
OID_TONER_MAX = "1.3.6.1.2.1.43.11.1.1.8.1.1"


@dataclass
class PrinterData:
    ip_address: str
    mac_address: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    serial_number: Optional[str] = None
    status: str = "online"
    pages_total: int = 0
    pages_bw: int = 0
    pages_color: int = 0
    toner_black: Optional[float] = None
    toner_cyan: Optional[float] = None
    toner_magenta: Optional[float] = None
    toner_yellow: Optional[float] = None
    alerts: list[str] = field(default_factory=list)


def _snmp_get(ip: str, oid: str, community: str, timeout: int) -> Optional[str]:
    try:
        import asyncio

        from pysnmp.hlapi.v3arch.asyncio import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            get_cmd,
        )

        async def fetch():
            transport = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=1)
            error_indication, error_status, _, var_binds = await get_cmd(
                SnmpEngine(),
                CommunityData(community),
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
            if error_indication or error_status:
                return None
            for var_bind in var_binds:
                return str(var_bind[1])
            return None

        return asyncio.run(fetch())
    except Exception as exc:
        logger.debug("SNMP falhou %s %s: %s", ip, oid, exc)
        return None


def _parse_int(value: Optional[str]) -> int:
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        digits = "".join(c for c in value if c.isdigit())
        return int(digits) if digits else 0


def _toner_percent(level: Optional[str], maximum: Optional[str]) -> Optional[float]:
    lvl = _parse_int(level)
    mx = _parse_int(maximum)
    if mx <= 0:
        return None
    return round((lvl / mx) * 100, 1)


def _guess_manufacturer(sys_descr: Optional[str]) -> Optional[str]:
    text = (sys_descr or "").lower()
    for key, name in {
        "hp": "HP", "hewlett": "HP", "canon": "Canon", "epson": "Epson",
        "brother": "Brother", "xerox": "Xerox", "ricoh": "Ricoh",
        "kyocera": "Kyocera", "samsung": "Samsung", "lexmark": "Lexmark",
    }.items():
        if key in text:
            return name
    return None


def _looks_like_printer(sys_descr: str) -> bool:
    text = sys_descr.lower()
    keywords = ("printer", "laserjet", "impressora", "mfp", "copier", "brother", "canon", "epson", "xerox", "ricoh")
    return any(k in text for k in keywords)


def collect_printer(ip: str, community: str = "public", timeout: int = 2) -> Optional[PrinterData]:
    sys_descr = _snmp_get(ip, OID_SYS_DESCR, community, timeout)
    if not sys_descr:
        return None

    if not _looks_like_printer(sys_descr):
        logger.debug("%s responde SNMP mas não parece impressora: %s", ip, sys_descr[:60])
        return None

    model = _snmp_get(ip, OID_PRINTER_MODEL, community, timeout) or sys_descr[:120]
    serial = _snmp_get(ip, OID_PRINTER_SERIAL, community, timeout)
    pages_total = _parse_int(_snmp_get(ip, OID_PAGES_TOTAL, community, timeout))
    toner_pct = _toner_percent(
        _snmp_get(ip, OID_TONER_LEVEL, community, timeout),
        _snmp_get(ip, OID_TONER_MAX, community, timeout),
    )

    data = PrinterData(
        ip_address=ip,
        model=model.strip() if model else None,
        manufacturer=_guess_manufacturer(sys_descr),
        serial_number=serial.strip() if serial else None,
        status="online",
        pages_total=pages_total,
        pages_bw=pages_total,
        toner_black=toner_pct,
    )

    if toner_pct is not None:
        if toner_pct <= 5:
            data.alerts.append(f"Toner preto crítico: {toner_pct}%")
        elif toner_pct <= 15:
            data.alerts.append(f"Toner preto baixo: {toner_pct}%")

    return data


def scan_subnet(subnet: str, community: str = "public", timeout: int = 2) -> list[PrinterData]:
    results: list[PrinterData] = []
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        logger.error("Sub-rede inválida: %s", subnet)
        return results

    hosts = list(network.hosts())
    logger.info("Varredura SNMP: %s (%d hosts)", subnet, len(hosts))

    for host in hosts:
        ip = str(host)
        data = collect_printer(ip, community, timeout)
        if data:
            logger.info("  ✓ %s — %s (%s)", ip, data.model, data.manufacturer or "?")
            results.append(data)

    return results


def collect_targets(ips: list[str], community: str = "public", timeout: int = 2) -> list[PrinterData]:
    results: list[PrinterData] = []
    for ip in ips:
        ip = ip.strip()
        if not ip:
            continue
        data = collect_printer(ip, community, timeout)
        if data:
            logger.info("  ✓ %s — %s", ip, data.model)
            results.append(data)
        else:
            logger.warning("  ✗ %s — sem resposta SNMP", ip)
    return results


def collect_all(subnets: list[str], ips: list[str], community: str, timeout: int) -> list[PrinterData]:
    readings: list[PrinterData] = []

    for subnet in subnets:
        readings.extend(scan_subnet(subnet, community, timeout))

    if ips:
        logger.info("Coleta em IPs fixos...")
        readings.extend(collect_targets(ips, community, timeout))

    seen: set[str] = set()
    unique: list[PrinterData] = []
    for r in readings:
        if r.ip_address not in seen:
            seen.add(r.ip_address)
            unique.append(r)

    return unique
