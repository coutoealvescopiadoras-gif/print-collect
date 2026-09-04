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


def _snmp_walk_table(ip: str, base_oid: str, community: str, timeout: int) -> dict[str, int]:
    """Realiza WALK (next_cmd) em uma tabela SNMP completa (todos os indices).
    Retorna dicionario: {'sufixo_oid_ultimos_2_numeros': valor_inteiro}.
    Ex: para base 43.10.2.1.4 retorna {'1.1': 10000, '1.2': 7500, '1.3': 2500}"""
    results: dict[str, int] = {}
    try:
        import asyncio

        from pysnmp.hlapi.v3arch.asyncio import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            next_cmd,
        )

        async def walk():
            try:
                transport = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=1)
                initial_var_bind = ObjectType(ObjectIdentity(base_oid))
                var_binds = initial_var_bind
                while True:
                    error_indication, error_status, error_index, vb_list = await next_cmd(
                        SnmpEngine(),
                        CommunityData(community),
                        transport,
                        ContextData(),
                        var_binds,
                        lexicographicMode=False,
                    )
                    if error_indication:
                        break
                    if error_status:
                        break
                    if not vb_list:
                        break
                    got_any_in_base = False
                    for var_bind in vb_list:
                        oid_str = str(var_bind[0])
                        if not oid_str.startswith(base_oid + ".") and not oid_str.startswith(base_oid):
                            continue
                        got_any_in_base = True
                        suffix = oid_str[len(base_oid):]
                        if suffix.startswith("."):
                            suffix = suffix[1:]
                        value_raw = str(var_bind[1])
                        value_int = _parse_int(value_raw)
                        if value_int > 0:
                            results[suffix] = value_int
                    if not got_any_in_base:
                        break
                    var_binds = vb_list
            except Exception as exc:
                logger.debug("SNMP walk falhou %s %s: %s", ip, base_oid, exc)

        asyncio.run(walk())
    except Exception as exc:
        logger.debug("SNMP walk setup falhou %s %s: %s", ip, base_oid, exc)
    return results


# Chaves de cor para detectar PB/Color na tabela prtMarkerColorantRole 43.12.1.1.4
COLORANT_BLACK_KEYWORDS = ("black", "preto", "processblack", "markerdark", "mono", "monochrome")
COLORANT_COLOR_KEYWORDS = (
    "cyan", "magenta", "yellow", "ciano", "amarelo",
    "processcyan", "processmagenta", "processyellow",
    "red", "green", "blue", "lightcyan", "lightmagenta",
)
BASE_OID_MARKER_LIFE_COUNT = "1.3.6.1.2.1.43.10.2.1.4"
BASE_OID_MARKER_COLORANT_ROLE = "1.3.6.1.2.1.43.12.1.1.4"


def _collect_pages_from_marker_table(ip: str, community: str, timeout: int) -> tuple[int, int]:
    """Fallback PODEROSO para impressoras que NAO USAM OIDs fixos 1.2/1.3
    (ex: Konica Minolta bizhub C258, Ricoh, Kyocera, Xerox, Samsung etc).
    Faz WALK na tabela prtMarkerLifeCount + prtMarkerColorantRole,
    identifica contadores PB / Color por indice, soma tudo.
    Retorna tuple (pages_bw_total, pages_color_total)."""
    try:
        life_counts = _snmp_walk_table(ip, BASE_OID_MARKER_LIFE_COUNT, community, timeout)
        if not life_counts:
            return 0, 0

        colorant_roles = _snmp_walk_table_raw_strings(ip, BASE_OID_MARKER_COLORANT_ROLE, community, timeout)

        pages_bw_sum = 0
        pages_color_sum = 0
        used = set()

        # 1) Prioridade 1: tabela COLORANT ROLE exatamente combinando marker index
        #    Formato OID 43.10.2.1.4.HRDEV.MARKER  → corresponde 43.12.1.1.4.HRDEV.COLORANT
        for lc_suffix, val in life_counts.items():
            # marker_suffix exemplo: "1.1" (hrDeviceIndex=1, markerIndex=1)
            parts = lc_suffix.split(".")
            if len(parts) < 2:
                continue
            hr_dev = parts[0]
            marker_idx = parts[-1]
            # Tenta combinações do colorant index igual ou diferente
            matched_role_str: Optional[str] = None
            for col_suffix, role_raw in colorant_roles.items():
                col_parts = col_suffix.split(".")
                if len(col_parts) < 2:
                    continue
                if col_parts[0] == hr_dev and (col_parts[-1] == marker_idx or col_parts[-1] == str(int(marker_idx) - 1) or col_parts[-1] == str(int(marker_idx) + 1)):
                    matched_role_str = role_raw
                    break
            if matched_role_str is None:
                # Heuristica 2: markerIndex 1 ou prefixo 1 → preto se nao tiver role
                if marker_idx == "1" and len(parts) == 2:
                    continue
                continue

            role_low = str(matched_role_str).lower().strip().strip('"').strip("'")
            if not role_low:
                continue
            if any(k in role_low for k in COLORANT_BLACK_KEYWORDS):
                pages_bw_sum += val
                used.add(lc_suffix)
            elif any(k in role_low for k in COLORANT_COLOR_KEYWORDS):
                pages_color_sum += val
                used.add(lc_suffix)

        # 2) Heuristica 3: indices que sobraram (não tiveram role de cor reconhecida).
        #    Estes índices são PEB (páginas em branco), contador duplex, alimentador,
        #    ou OUTROS contadores NÃO-coloridos. Portanto:
        #    ✅ SOMA TUDO EM pages_bw_sum (PEB é PB! NUNCA vai para color!)
        remaining = [(suf, v) for suf, v in life_counts.items() if suf not in used]
        if remaining:
            def sort_key(tup):
                parts = tup[0].split(".")
                return tuple(int(p) for p in parts if p.isdigit())
            remaining_sorted = sorted(remaining, key=sort_key)
            for _, v in remaining_sorted:
                pages_bw_sum += v

        return max(0, pages_bw_sum), max(0, pages_color_sum)
    except Exception as exc:
        logger.debug("collect_pages_from_marker_table exc %s: %s", ip, exc)
        return 0, 0


def _snmp_walk_table_raw_strings(ip: str, base_oid: str, community: str, timeout: int) -> dict[str, str]:
    """Walk retornando strings brutas (para roles de cor etc)."""
    results: dict[str, str] = {}
    try:
        import asyncio

        from pysnmp.hlapi.v3arch.asyncio import (
            CommunityData,
            ContextData,
            ObjectIdentity,
            ObjectType,
            SnmpEngine,
            UdpTransportTarget,
            next_cmd,
        )

        async def walk():
            try:
                transport = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=1)
                initial_var_bind = ObjectType(ObjectIdentity(base_oid))
                var_binds = initial_var_bind
                while True:
                    error_indication, error_status, _, vb_list = await next_cmd(
                        SnmpEngine(),
                        CommunityData(community),
                        transport,
                        ContextData(),
                        var_binds,
                        lexicographicMode=False,
                    )
                    if error_indication or error_status:
                        break
                    if not vb_list:
                        break
                    got_any = False
                    for var_bind in vb_list:
                        oid_str = str(var_bind[0])
                        if not oid_str.startswith(base_oid + ".") and not oid_str.startswith(base_oid):
                            continue
                        got_any = True
                        suffix = oid_str[len(base_oid):]
                        if suffix.startswith("."):
                            suffix = suffix[1:]
                        results[suffix] = str(var_bind[1])
                    if not got_any:
                        break
                    var_binds = vb_list
            except Exception as exc:
                logger.debug("walk raw exc %s %s: %s", ip, base_oid, exc)

        asyncio.run(walk())
    except Exception as exc:
        logger.debug("walk raw setup exc %s %s: %s", ip, base_oid, exc)
    return results


def _parse_int(value: Optional[str]) -> int:
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        s = str(value).strip()
        is_negative = False
        for ch in s:
            if ch == "-":
                is_negative = True
                break
            if ch == "+":
                break
            if ch.isdigit():
                break
        digits = "".join(c for c in s if c.isdigit())
        if not digits:
            return 0
        num = int(digits)
        return -num if is_negative else num


def _toner_percent(level: Optional[str], maximum: Optional[str]) -> Optional[float]:
    lvl = _parse_int(level)
    mx = _parse_int(maximum)
    if lvl < 0:
        return None
    if mx <= 0:
        return None
    if mx == 100:
        pct = float(lvl)
    else:
        if lvl > mx * 2:
            return None
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

    # ==================================================================
    # 🏆 REGRAS DE OURO — COBRANÇA SEGURA (JULIO NÃO PODE COBRAR ERRADO!)
    # ==================================================================
    #
    # REGRA 1 — NUNCA INVENTA PÁGINAS COLORIDAS (prioridade MÁXIMA!)
    #   Só confia em pages_color se OID FIXO RFC .1.3 > 0 OU
    #   se marker table retornou COLORIDO > 0 (col_walk > 0) E (OID .1.3 = 0/inválido)
    #   → Qualquer outra situação = pages_color = 0 (Tudo P&B!).
    #
    # REGRA 2 — SE TIVER DÚVIDA, TUDO VAI PARA P&B!
    #   PEB (páginas em branco), feeder, duplex, toners sem role de cor → TUDO PB.
    #   Melhor você NÃO cobrar por uma cor que a impressora não confirmou
    #   do que cobrar errado e ter problema com cliente!
    #
    # REGRA 3 — PRIORIDADE DE FONTE (do mais seguro pro menos seguro):
    #   1) 🔵 OID FIXO RFC .1.1 (total), .1.2 (pb), .1.3 (color)  [MELHOR / OFICIAL]
    #   2) 🟣 Marker table COM roles CMYK detectados                 [SEGURO]
    #   3) 🟢 Só o .1.1 (total) existe → pages_bw = total, color=0  [FALLBACK PB]
    #
    # REGRA 4 — pages_total SEMPRE = max(OID total, pb+color_real)
    #   Nunca deixa o total ser MENOR que o split correto (pois split real = realidade).
    # ==================================================================

    # ========== PASSO 1: OIDs FIXOS PADRAO RFC (MELHOR FONTE, 100% confiavel) ==========
    oid_total = _parse_int(_snmp_get(ip, OID_PAGES_TOTAL, community, timeout)) or 0
    oid_pb    = _parse_int(_snmp_get(ip, OID_PAGES_BW,    community, timeout)) or 0
    oid_color = _parse_int(_snmp_get(ip, OID_PAGES_COLOR, community, timeout)) or 0

    # ========== PASSO 2: MARKER TABLE (RICOH / KONICA / KYOCERA — SÓ SE OIDs RFC VAZIOS!) ==========
    marker_pb = 0
    marker_color = 0
    _oid_rfc_split_ok = (oid_pb > 0) or (oid_color > 0)
    if not _oid_rfc_split_ok:
        marker_pb, marker_color = _collect_pages_from_marker_table(ip, community, timeout)
        marker_pb    = marker_pb    or 0
        marker_color = marker_color or 0

    # ========== PASSO 3: APLICA REGRAS — NUNCA INVENTA COLORIDO! ==========
    pages_total = oid_total or 0
    pages_bw    = 0
    pages_color = 0

    # --- (FONTE 1) OID FIXO RFC .1.2 e .1.3 são os MELHORES. Usa eles primeiro! ---
    if oid_pb > 0 or oid_color > 0:
        pages_bw    = oid_pb
        pages_color = oid_color  # só usa colorido SE OID .1.3 REALMENTE disse >0!
    # --- (FONTE 2) MARKER TABLE — só se OIDs RFC split não existiam ---
    elif marker_pb > 0 or marker_color > 0:
        pages_bw    = marker_pb
        pages_color = marker_color  # só usa colorido SE marker disse color>0 REALMENTE!
        if pages_total <= 0:
            pages_total = pages_bw + pages_color
    # --- (FONTE 3) NENHUM contador separado REAL existe → TUDO P&B! ---
    else:
        pages_bw    = pages_total  # Tudo = P&B!
        pages_color = 0
        # Se só tem pages_total (sem split), já está correto acima.

    # ========== PASSO 4: pages_total NUNCA fica MENOR que o split real ==========
    sum_real_split = pages_bw + pages_color
    if sum_real_split > pages_total:
        pages_total = sum_real_split
    # pages_bw nunca pode ser 0 se temos total. Se split ainda é 0 por nao ter fontes,
    # joga tudo para PB.
    if pages_total > 0 and pages_bw <= 0 and pages_color <= 0:
        pages_bw = pages_total
        pages_color = 0

    # ========== REGRA EXTRA: NUNCA DEIXA pages_color MAIOR QUE TOTAL! ==========
    # (segurança extra contra qualquer bug de SNMP)
    if pages_total > 0 and pages_color > pages_total:
        pages_color = max(0, pages_total - pages_bw) if pages_bw > 0 else 0
        if pages_color < 0: pages_color = 0
    if pages_total > 0 and pages_bw > pages_total:
        pages_bw = pages_total

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
    # ⚠️ REGRA CRÍTICA ANTI-FALSO-POSITIVO (Julio pediu várias vezes!):
    #   Muitas impressoras PB (ex: Ricoh SP 3710SF) reportam OID de ciano/magenta/amarelo
    #   com VALOR 0 (não None) via SNMP! "Nenhum = 0"
    #   ANTES: has_color_toners = any(t is not None) → interpretava 0 como "EXISTE" ❌
    #   DEPOIS: has_color_toners = any(t is not None and float(t) > 0) → só >0 conta como EXISTE ✅
    has_color_pages = bool(pages_color and pages_color > 0)
    has_color_toners = False
    for _t in (toner_cyan, toner_magenta, toner_yellow):
        if _t is None:
            continue
        try:
            if float(_t) > 0:
                has_color_toners = True
                break
        except Exception:
            continue
    is_color_printer = has_color_pages or has_color_toners

    # ⛔ IMPRESSORA PB CONFIRMADA: NÃO EXISTEM toners ciano/magenta/amarelo de verdade.
    # Apaga QUALQUER valor reportado como 0 ou None → deixa None (nao manda dado mentiroso para o backend)
    if not is_color_printer:
        toner_cyan = None
        toner_magenta = None
        toner_yellow = None
        data.toner_cyan = None
        data.toner_magenta = None
        data.toner_yellow = None
        # PRETO & BRANCO (COBRANÇA SEGURA):
        #   1 contador = TOTAL REAL DO SNMP (oid_total).
        #   Não calcula, não divide, não inventa.
        pages_color = 0
        data.pages_color = 0
        if pages_total > 0:
            pages_bw = pages_total
            data.pages_bw = pages_total
        elif pages_bw > 0:
            pages_total = pages_bw
            data.pages_total = pages_total
    else:
        # ===== IMPRESSORA COLORIDA — JÁ COLETADA COM REGRAS SEGURAS ACIMA =====
        # A coleta (PASSOS 1-4) já garantiu:
        #   pages_color = 0 A MENOS QUE oid_color > 0 REAL OU marker_color > 0 REAL.
        #   NÃO INVENTA pages_color = total - bw. NÃO há chutes.
        # Só garantimos aqui a monotonicidade básica e salvamos.
        # Se a impressora é colorida mas NÃO reportou split reais (color=0):
        #   → NÃO cobramos por cor de qualquer jeito. pages_color = 0 e bw = total.
        if pages_color <= 0 and pages_total > 0:
            pages_bw = pages_total
            pages_color = 0
        if pages_bw + pages_color > pages_total:
            pages_total = pages_bw + pages_color
        data.pages_bw = pages_bw
        data.pages_color = pages_color
        data.pages_total = pages_total

    # Alertas básicos de toner (SOMENTE para toners EXISTENTES CONFIRMADOS!)
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

    # Atualiza os dados no PrinterData (apos correcoes de PB acima)
    data.toner_cyan = toner_cyan
    data.toner_magenta = toner_magenta
    data.toner_yellow = toner_yellow
    data.pages_bw = pages_bw
    data.pages_color = pages_color
    data.pages_total = pages_total

    logger.info("Contadores %s: total=%d bw=%d color=%d is_color=%s",
                data.model or data.ip_address, data.pages_total, data.pages_bw, data.pages_color, is_color_printer)

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
