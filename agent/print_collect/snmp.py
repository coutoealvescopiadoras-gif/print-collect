"""Coleta de dados de impressoras via SNMP na rede local do cliente.

Varredura PARALELA com pre-triagem (ping ICMP + porta TCP 9100/161) para
evitar esperar 2 segundos por IP que nem sequer estah ligado.
Em uma rede /24 (254 IPs) tipicamente cai de ~8 min para < 20 segundos.
"""

from __future__ import annotations

import ipaddress
import logging
import platform
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("print-collect-agent")

OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"
OID_PRINTER_SERIAL = "1.3.6.1.2.1.43.5.1.1.17.1"
OID_PRINTER_MODEL = "1.3.6.1.2.1.25.3.2.1.3.1"
OID_PAGES_TOTAL = "1.3.6.1.2.1.43.10.2.1.4.1.1"
OID_PAGES_BW = "1.3.6.1.2.1.43.10.2.1.4.1.2"
OID_PAGES_COLOR = "1.3.6.1.2.1.43.10.2.1.4.1.3"
OID_TONER_LEVEL = "1.3.6.1.2.1.43.11.1.1.9.1.1"
OID_TONER_MAX = "1.3.6.1.2.1.43.11.1.1.8.1.1"
OID_TONER_CYAN_LEVEL = "1.3.6.1.2.1.43.11.1.1.9.1.2"
OID_TONER_CYAN_MAX = "1.3.6.1.2.1.43.11.1.1.8.1.2"
OID_TONER_MAGENTA_LEVEL = "1.3.6.1.2.1.43.11.1.1.9.1.3"
OID_TONER_MAGENTA_MAX = "1.3.6.1.2.1.43.11.1.1.8.1.3"
OID_TONER_YELLOW_LEVEL = "1.3.6.1.2.1.43.11.1.1.9.1.4"
OID_TONER_YELLOW_MAX = "1.3.6.1.2.1.43.11.1.1.8.1.4"

PRINTER_KEYWORDS = (
    "printer", "laserjet", "impressora", "mfp", "copier", "multifunction",
    "brother", "canon", "epson", "xerox", "ricoh", "hp ", "hewlett",
    "kyocera", "samsung", "lexmark", "oki", "sharp", "konica", "toshiba",
)


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


# ---------------------------------------------------------------------------
# SNMP get
# ---------------------------------------------------------------------------

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
            try:
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
            except Exception:
                return None
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
        # Alguns fabricantes retornam -1 para "infinito"
        if lvl >= 0 and lvl <= 100:
            return float(lvl)
        return None
    # Se o level vier em percentual diretamente (menor que mx e menor que 100)
    if mx == 100:
        return round(float(lvl), 1)
    pct = round((lvl / mx) * 100, 1)
    return pct if 0 <= pct <= 100 else None


def _guess_manufacturer(sys_descr: Optional[str]) -> Optional[str]:
    text = (sys_descr or "").lower()
    mapping = {
        "hp": "HP", "hewlett": "HP", "hp laserjet": "HP",
        "canon": "Canon",
        "epson": "Epson",
        "brother": "Brother",
        "xerox": "Xerox",
        "ricoh": "Ricoh",
        "kyocera": "Kyocera",
        "samsung": "Samsung",
        "lexmark": "Lexmark",
        "oki": "OKI",
        "sharp": "Sharp",
        "konica": "Konica Minolta",
        "toshiba": "Toshiba",
    }
    for key, name in mapping.items():
        if key in text:
            return name
    return None


def _looks_like_printer(sys_descr: str) -> bool:
    text = sys_descr.lower()
    return any(k in text for k in PRINTER_KEYWORDS)


# ---------------------------------------------------------------------------
# Pre-triagem: esta IP provavelmente eh uma impressora? (ping + portas TCP)
# ---------------------------------------------------------------------------

def _tcp_probe(ip: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ping_ip(ip: str, timeout_ms: int) -> bool:
    """Retorna True se o IP responder a ping."""
    system = platform.system().lower()
    try:
        if system == "windows":
            # -n 1  uma tentativa ; -w timeout_ms
            proc = subprocess.run(
                ["ping", "-n", "1", "-w", str(timeout_ms), ip],
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000 + 2,
            )
            return proc.returncode == 0 and (
                "TTL=" in proc.stdout or "TTL=" in proc.stderr
            )
        else:
            proc = subprocess.run(
                ["ping", "-c", "1", "-W", str(max(1, timeout_ms // 1000)), ip],
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000 + 2,
            )
            return proc.returncode == 0
    except Exception:
        return False


def pre_scan_one(ip: str, snmp_timeout: int = 2) -> bool:
    """Verificacao RAPIDA (ate ~1,5s). Porta 9100 => quase certamente impressora.
    Porta 161 SNMP aberta => vale tentar SNMP get. Ping OK => chance de existir."""
    if _tcp_probe(ip, 9100, timeout=min(1.0, snmp_timeout / 2)):
        return True
    if _tcp_probe(ip, 161, timeout=min(0.8, snmp_timeout / 2)):
        return True
    # Caso contrario, ping: se responder, tentamos SNMP de qualquer jeito
    return _ping_ip(ip, timeout_ms=max(600, snmp_timeout * 400))


# ---------------------------------------------------------------------------
# Descoberta de sub-redes locais (melhorado)
# ---------------------------------------------------------------------------

def discover_local_subnets() -> list[str]:
    """Retorna lista de sub-redes /24 onde a maquina possui interface IPv4 ativa.
    Tenta varias tecnicas para nao perder VPNs, adaptadores virtuais, etc."""
    discovered: set[str] = set()

    def add_ip(ip: str, prefix_len: int = 24) -> None:
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return
        if address.version != 4 or address.is_loopback or address.is_link_local:
            return
        network = ipaddress.ip_network(f"{address}/{prefix_len}", strict=False)
        discovered.add(str(network))

    # 1) Conectando a um IP da internet descobrimo IP de saida
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2)
            sock.connect(("8.8.8.8", 80))
            add_ip(sock.getsockname()[0])
    except OSError:
        pass

    # 2) hostname + DNS
    try:
        hostname = socket.gethostname()
        for family, _, _, _, sockaddr in socket.getaddrinfo(hostname, None, socket.AF_INET):
            if family == socket.AF_INET and sockaddr:
                add_ip(sockaddr[0])
    except OSError:
        pass

    # 3) Windows: via netsh ou socket.ioctl com SIO_GET_INTERFACE_LIST
    if platform.system() == "Windows":
        try:
            proc = subprocess.run(
                ["netsh", "interface", "ip", "show", "address"],
                capture_output=True, text=True, timeout=5,
            )
            import re
            for match in re.finditer(
                r"IP address:\s*(?P<ip>\d{1,3}(?:\.\d{1,3}){3}).*?Subnet Prefix:\s*[\d\.]*/(?P<prefix>\d+)",
                proc.stdout,
                re.DOTALL,
            ):
                prefix = int(match.group("prefix"))
                if prefix > 24:
                    prefix = 24  # nao vasculhamos sub-redes maiores que /24
                add_ip(match.group("ip"), prefix_len=prefix)
        except Exception:
            pass

    # 4) socket.ioctl (SIO_GET_INTERFACE_LIST) - Windows/Linux
    try:
        import array
        import struct
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        SIO_GET_INTERFACE_LIST = 0x74000000 + 21
        MAX_BYTES = 8192
        buf = array.array("B", b"\0" * MAX_BYTES)
        _, bytes_written = sock.ioctl(SIO_GET_INTERFACE_LIST, buf, True)
        num_ifaces = bytes_written // (8 * 4 + 16 + 16)
        offset = 0
        for _ in range(num_ifaces):
            _, _, _, _, _, _, _, _ = struct.unpack_from("<llllllll", buf, offset)
            offset += 32
            addr = buf[offset:offset + 16]
            offset += 16
            _ = buf[offset:offset + 16]
            offset += 16
            ip = socket.inet_ntoa(addr[:4])
            add_ip(ip)
        sock.close()
    except Exception:
        pass

    return sorted(discovered)


# ---------------------------------------------------------------------------
# Coleta real de 1 IP de impressora (SNMP completo)
# ---------------------------------------------------------------------------

def collect_printer(ip: str, community: str = "public", timeout: int = 2) -> Optional[PrinterData]:
    sys_descr = _snmp_get(ip, OID_SYS_DESCR, community, timeout)
    if not sys_descr:
        return None

    if not _looks_like_printer(sys_descr):
        logger.debug("%s responde SNMP mas nao parece impressora: %s", ip, sys_descr[:80])
        return None

    model = _snmp_get(ip, OID_PRINTER_MODEL, community, timeout) or sys_descr[:120]
    serial = _snmp_get(ip, OID_PRINTER_SERIAL, community, timeout)
    pages_total = _parse_int(_snmp_get(ip, OID_PAGES_TOTAL, community, timeout))
    pages_bw = _parse_int(_snmp_get(ip, OID_PAGES_BW, community, timeout)) or pages_total
    pages_color = _parse_int(_snmp_get(ip, OID_PAGES_COLOR, community, timeout))

    toner_black = _toner_percent(
        _snmp_get(ip, OID_TONER_LEVEL, community, timeout),
        _snmp_get(ip, OID_TONER_MAX, community, timeout),
    )
    toner_cyan = _toner_percent(
        _snmp_get(ip, OID_TONER_CYAN_LEVEL, community, timeout),
        _snmp_get(ip, OID_TONER_CYAN_MAX, community, timeout),
    )
    toner_magenta = _toner_percent(
        _snmp_get(ip, OID_TONER_MAGENTA_LEVEL, community, timeout),
        _snmp_get(ip, OID_TONER_MAGENTA_MAX, community, timeout),
    )
    toner_yellow = _toner_percent(
        _snmp_get(ip, OID_TONER_YELLOW_LEVEL, community, timeout),
        _snmp_get(ip, OID_TONER_YELLOW_MAX, community, timeout),
    )

    data = PrinterData(
        ip_address=ip,
        model=model.strip() if model else None,
        manufacturer=_guess_manufacturer(sys_descr),
        serial_number=serial.strip() if serial else None,
        status="online",
        pages_total=pages_total,
        pages_bw=pages_bw,
        pages_color=pages_color,
        toner_black=toner_black,
        toner_cyan=toner_cyan,
        toner_magenta=toner_magenta,
        toner_yellow=toner_yellow,
    )

    # Determina se a impressora é MONOCROMÁTICA (Preto & Branco)
    # Regra: NÃO possui páginas coloridas totais impressas OU
    #       NÃO retorna níveis de toner coloridos (todos são None).
    has_color_pages = bool(pages_color and pages_color > 0)
    has_color_toners = any(t is not None for t in (toner_cyan, toner_magenta, toner_yellow))
    is_color_printer = has_color_pages or has_color_toners

    # Alertas básicos de toner (SOMENTE para toners EXISTENTES!)
    alerts: list[str] = []
    toners_to_check: list[tuple[str, Optional[float]]] = [("preto", toner_black)]
    if is_color_printer:
        toners_to_check.extend([
            ("ciano", toner_cyan),
            ("magenta", toner_magenta),
            ("amarelo", toner_yellow),
        ])

    for color, pct in toners_to_check:
        if pct is None:
            continue
        if pct <= 5:
            alerts.append(f"Toner {color} critico: {pct}%")
        elif pct <= 15:
            alerts.append(f"Toner {color} baixo: {pct}%")
    data.alerts = alerts

    return data


# ---------------------------------------------------------------------------
# Varredura paralela (essencial para velocidade!)
# ---------------------------------------------------------------------------

def scan_subnet(
    subnet: str,
    community: str = "public",
    timeout: int = 2,
    max_workers: int = 64,
) -> list[PrinterData]:
    results: list[PrinterData] = []
    try:
        network = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        logger.error("Sub-rede invalida: %s", subnet)
        return results

    hosts = [str(h) for h in network.hosts()]
    logger.info("Varredura rede %s (%d IPs) — pre-triagem (ping/TCP)...", subnet, len(hosts))

    # 1) Pre-triagem em paralelo para filtrar IPs promissores
    candidates: set[str] = set()
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(pre_scan_one, ip, timeout): ip for ip in hosts}
            for fut in as_completed(futures):
                ip = futures[fut]
                try:
                    if fut.result():
                        candidates.add(ip)
                except Exception:
                    continue
    except Exception:
        pass

    logger.info("Pre-triagem %s concluida: %d/%d IPs parecem ativos/impressoras",
                subnet, len(candidates), len(hosts))

    # 2) Coleta SNMP completa apenas dos candidatos
    with ThreadPoolExecutor(max_workers=max_workers // 2 or 1) as pool:
        futures = {
            pool.submit(collect_printer, ip, community, timeout): ip
            for ip in candidates
        }
        for fut in as_completed(futures):
            try:
                data = fut.result()
            except Exception:
                continue
            if data:
                logger.info("  ✓ %s — %s (%s)",
                            data.ip_address, data.model, data.manufacturer or "?")
                results.append(data)

    return results


def collect_targets(
    ips: list[str],
    community: str = "public",
    timeout: int = 2,
) -> list[PrinterData]:
    results: list[PrinterData] = []
    ips_clean = [ip.strip() for ip in ips if ip and ip.strip()]
    if not ips_clean:
        return results

    def do_one(ip: str) -> Optional[PrinterData]:
        try:
            return collect_printer(ip, community, timeout)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=min(len(ips_clean), 32)) as pool:
        for ip, data in zip(ips_clean, pool.map(do_one, ips_clean)):
            if data:
                logger.info("  ✓ %s — %s", ip, data.model)
                results.append(data)
            else:
                logger.warning("  ✗ %s — sem resposta SNMP", ip)
    return results


def collect_all(
    subnets: list[str],
    ips: list[str],
    community: str,
    timeout: int,
) -> list[PrinterData]:
    readings: list[PrinterData] = []
    effective_subnets = list(subnets or [])

    if not effective_subnets and not ips:
        effective_subnets = discover_local_subnets()
        if effective_subnets:
            logger.info("Nenhuma rede configurada; descoberta automatica: %s",
                        ", ".join(effective_subnets))
        else:
            logger.warning("Nenhuma rede configurada e nenhuma sub-rede local descoberta.")

    for subnet in effective_subnets:
        readings.extend(scan_subnet(subnet, community, timeout))

    if ips:
        logger.info("Coleta em IPs fixos...")
        readings.extend(collect_targets(ips, community, timeout))

    # Deduplica por IP
    seen: set[str] = set()
    unique: list[PrinterData] = []
    for r in readings:
        if r.ip_address not in seen:
            seen.add(r.ip_address)
            unique.append(r)
    return unique
