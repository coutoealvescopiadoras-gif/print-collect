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

# =====================================================================
# 🔑 OIDs PRIVADOS POR MARCA (campo-validados: PrinterMS CC-BY-4.0 + MIBs oficiais)
#    Tier A/B = split PB/Color REAL. Tier D = só Total, NÃO INVENTA cor.
# =====================================================================
# HP (PEN 11) - Tier A - escalares diretos 100% confiáveis
_OID_HP_TOTAL = "1.3.6.1.4.1.11.2.3.9.4.2.1.4.1.2.5.0"
_OID_HP_BW    = "1.3.6.1.4.1.11.2.3.9.4.2.1.4.1.2.6.0"
_OID_HP_COLOR = "1.3.6.1.4.1.11.2.3.9.4.2.1.4.1.2.7.0"

# Konica Minolta (PEN 18334) - Tier A - Copy + Print separados (soma = contador OFICIAL)
_OID_KM_TOTAL        = "1.3.6.1.4.1.18334.1.1.1.5.7.2.1.1.0"
_OID_KM_COPY_BW      = "1.3.6.1.4.1.18334.1.1.1.5.1.1.0"
_OID_KM_PRINT_BW     = "1.3.6.1.4.1.18334.1.1.1.5.1.2.0"
_OID_KM_COPY_COLOR   = "1.3.6.1.4.1.18334.1.1.1.5.2.1.0"
_OID_KM_PRINT_COLOR  = "1.3.6.1.4.1.18334.1.1.1.5.2.2.0"
# Konica Minolta: OIDs ALTERNATIVOS (PrinterMS oficial C368/C258/C308 firmwares mais antigas / mais novas)
#   Conjunto B: contadores "Total Counter" split BW/Color direto (não Copy/Print)
_KM_ALT_B_TOTAL_BW   = "1.3.6.1.4.1.18334.1.1.1.5.7.2.0"
_KM_ALT_B_TOTAL_CLR  = "1.3.6.1.4.1.18334.1.1.1.5.7.1.0"
_KM_ALT_B_TOTAL_TOT  = "1.3.6.1.4.1.18334.1.1.1.5.7.3.0"
#   Conjunto C: bizhub C308 firmware 2020+ MIBs (índice .1 em vez de .0)
_KM_ALT_C_COPY_BW    = "1.3.6.1.4.1.18334.1.1.1.5.1.1.1"
_KM_ALT_C_PRINT_BW   = "1.3.6.1.4.1.18334.1.1.1.5.1.2.1"
_KM_ALT_C_COPY_CLR   = "1.3.6.1.4.1.18334.1.1.1.5.2.1.1"
_KM_ALT_C_PRINT_CLR  = "1.3.6.1.4.1.18334.1.1.1.5.2.2.1"
_KM_ALT_C_TOTAL      = "1.3.6.1.4.1.18334.1.1.1.5.7.2.1.1.1"

# Xerox (PEN 253) - Tier A - escalares diretos
_OID_XEROX_TOTAL = "1.3.6.1.4.1.253.8.53.13.2.1.6.1.20.1"
_OID_XEROX_BW    = "1.3.6.1.4.1.253.8.53.13.2.1.6.1.20.34"
_OID_XEROX_COLOR = "1.3.6.1.4.1.253.8.53.13.2.1.6.1.20.33"

# Ricoh (PEN 367) - Tier B - Total privado. PB/Color = WALK da tabela .19.X por LABEL
_OID_RICOH_TOTAL = "1.3.6.1.4.1.367.3.2.1.2.19.1.0"
_BASE_OID_RICOH_COUNTER_LABEL = "1.3.6.1.4.1.367.3.2.1.2.19.3"  # Nome do contador
_BASE_OID_RICOH_COUNTER_VALUE = "1.3.6.1.4.1.367.3.2.1.2.19.5"  # Valor do contador

# Lexmark (PEN 641) - Tier A - WALK por TYPE CODE (3=totalMono, 4=totalColor, 2=total)
_BASE_OID_LEXMARK_COUNT = "1.3.6.1.4.1.641.6.4.2.1.1.4"

# Canon (PEN 1602) - Tier B - WALK por TYPE CODE (101=total, 108=mono, 122+123=color)
_BASE_OID_CANON_COUNT = "1.3.6.1.4.1.1602.1.11.1.3.1.3.1.4"

# Sharp (PEN 2385) - Tier C - escalares fixos
_OID_SHARP_BW    = "1.3.6.1.4.1.2385.1.1.19.2.1.3.5.4.61"
_OID_SHARP_COLOR = "1.3.6.1.4.1.2385.1.1.19.2.1.3.5.4.63"

# Ricoh Toner privado (367.3.2.1.2.24.1.1.5.{1=K,2=C,3=M,4=Y}) - Padrão retorna BOGUS
_BASE_OID_RICOH_TONER_LEVEL = "1.3.6.1.4.1.367.3.2.1.2.24.1.1.5"
_BASE_OID_RICOH_TONER_MAX   = "1.3.6.1.4.1.367.3.2.1.2.24.1.1.4"

# =====================================================================
# 🖨️ PEN (Private Enterprise Number) → nome da marca
#    Extraímos o PEN do 4º campo do OID sysObjectID: 1.3.6.1.4.1.PEN.x.y.z...
# =====================================================================
PEN_TO_MANUFACTURER: dict[int, str] = {
    11:    "HP",
    18334: "Konica Minolta",
    253:   "Xerox",
    367:   "Ricoh",
    641:   "Lexmark",
    1602:  "Canon",
    2385:  "Sharp",
    2435:  "Brother",
    1347:  "Kyocera",
    1248:  "Epson",
    1129:  "Toshiba",
    2001:  "OKI",
    40093: "Pantum",
}

# =====================================================================
# 🎨 Ordem dos índices de toner CMYK (marca → (K, C, M, Y))
#    Padrão RFC (.9.1.1 = preto, .9.1.2 = ciano etc) NÃO funciona p/ todas!
#    Ex: Konica Minolta → 4=Preto, 1=Ciano, 2=Magenta, 3=Amarelo
# =====================================================================
TONER_INDEX_MAP: dict[str, tuple[int, int, int, int]] = {
    # marca = (idx_preto, idx_ciano, idx_magenta, idx_amarelo)
    "HP":             (1, 2, 3, 4),   # Padrão RFC
    "Ricoh":          (1, 2, 3, 4),   # Usa OID privado .367.3.2.1.2.24 depois
    "Xerox":          (1, 2, 3, 4),   # Padrão
    "Lexmark":        (1, 2, 3, 4),   # Padrão
    "Canon":          (1, 2, 3, 4),   # Padrão
    "Sharp":          (1, 2, 3, 4),   # Padrão
    "Brother":        (1, 2, 3, 4),   # (toner RFC é -2/-3, mas mapeamento é esse)
    "Kyocera":        (1, 2, 3, 4),   # Padrão
    "Epson":          (1, 2, 3, 4),   # Padrão (laser)
    "Toshiba":        (1, 2, 3, 4),   # Padrão
    "OKI":            (1, 2, 3, 4),   # Padrão
    "Pantum":         (1, 2, 3, 4),   # Padrão
    # ⬇️ INVERSÃO CONFIRMADA: N-able + campo Konica C258
    "Konica Minolta": (4, 1, 2, 3),   # 4=K, 1=C, 2=M, 3=Y
}

# Marcas Tier D = NÃO EXISTE OID confirmado de split PB/Color → tudo vai para PB, NUNCA inventa cor
MANUFACTURERS_TIER_D_ONLY_TOTAL: frozenset[str] = frozenset([
    "Toshiba", "Epson", "OKI", "Pantum",
])
# Modelos onde a heurística "maior contador = preto" é SEGURA (única exceção)
ALLOW_HEURISTIC_LARGEST_BLACK_MODELS: tuple[str, ...] = (
    "L3150", "L3250", "L3210", "L5190", "L5290", "L4260", "L4160",  # EPSON EcoTank
    "ET-2810", "ET-2850", "ET-3850", "ET-4750", "ET-4850",
)

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
                # v6.9.5: retries=3 (antes era 1!) para rede WiFi instavel cliente
                transport = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=3)
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
                # v6.9.5: retries=3 (antes era 1!) para WiFi instavel do cliente
                transport = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=3)
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


def _collect_pages_from_marker_table(
    ip: str,
    community: str,
    timeout: int,
    has_color_toners_hint: bool = False,
    force_largest_heuristic_disabled: bool = False,
) -> tuple[int, int]:
    """Fallback PODEROSO para impressoras que NAO USAM OIDs fixos 1.2/1.3
    (ex: Konica Minolta bizhub C258, Ricoh, Kyocera, Xerox, Samsung, EPSON EcoTank coloridas etc).

    Faz WALK na tabela prtMarkerLifeCount + prtMarkerColorantRole,
    identifica contadores PB / Color por indice, soma tudo.

    PARAMETROS v6.9.x (coleta segura):
      has_color_toners_hint = True/False (vem da deteccao dos toners CMY > 0% no SNMP)
        Se True = impressora E colorida (tem toners coloridos instalados)
        => HEURISTICA NOVA: nao tem roles de cor? nao joga tudo no PB!
           Split: maior contador = PB, soma dos outros 2/3 = COLORIDO.
        Se False = impressora provavelmente PB => tudo PB, como antes (100% seguro).

      force_largest_heuristic_disabled = True/False (DEFESA EM PROFUNDIDADE 2026-09-21)
        Se True = DESATIVA a heuristica "maior contador = preto", independente de has_color_toners_hint.
        Usado quando o modelo NAO esta na whitelist EPSON EcoTank. NUNCA MAIS inventa paginas coloridas.

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
                # Heuristica 2: se tem role, combina. Se NAO TEM role (EPSON L3250 etc),
                # NAO soma nada aqui — vai para "remaining" logo abaixo (onde a nova heuristica de cor brilha!).
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

        # ==================================================================
        # 2) HEURISTICA NOVA v6.9.1 — SEM ROLES DE COR MAS IMPRESSORA COLORIDA!
        #    (EPSON EcoTank L3250 / L3150 / L5290 / etc!)
        # ==================================================================
        # Se temos has_color_toners_hint = True (toners C/M/Y > 0% coletados!)
        # E ainda sobraram indices NAO-usados pq a tabela de roles nao existe ou
        # nao tem valores reconheciveis, entao:
        #   - ORDENA os remaining por valor DECRESCENTE.
        #   - SE tivermos 2+ indices:
        #       * 1º maior = PRETO (P&B)
        #       * SOMA de todos os outros restantes = COLORIDO
        #   - SE tivermos apenas 1 indice: vai para PB (seguranca)
        #
        # (Regra de SEGURANCA MAXIMA: se has_color_toners_hint = False = PB provavel,
        #  mantemos o comportamento antigo: SOMA TUDO EM PB!)
        # ==================================================================
        remaining = [(suf, v) for suf, v in life_counts.items() if suf not in used]

        if has_color_toners_hint and not force_largest_heuristic_disabled and len(remaining) >= 2:
            # Ordena: MAIOR valor primeiro (maior contador = preto, normalmente)
            remaining_sorted = sorted(remaining, key=lambda t: t[1], reverse=True)
            for i, (_, v) in enumerate(remaining_sorted):
                if i == 0:
                    # Primeiro da lista (maior valor) → Preto / P&B
                    pages_bw_sum += v
                else:
                    # Todos os outros → assumidos Coloridos (heuristica SEGURA pq TEM toner color!)
                    pages_color_sum += v
        else:
            # HEURISTICA ANTIGA (manter 100% compat):
            # indices que sobraram sem role = PEB, duplex, alimentador etc → TUDO PB!
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
                # v6.9.5: retries=3 (antes era 1!) para WiFi instavel do cliente
                transport = await UdpTransportTarget.create((ip, 161), timeout=timeout, retries=3)
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


def _collect_pages_printer_mib_rfc(
    ip: str,
    community: str,
    timeout: int,
    diagnostic_mode: bool = False,
) -> Optional[tuple[int, int, int]]:
    """COLETA RFC 3805 DEFINITIVA: WALK tabela prtMarkerTable (Printer MIB) por ColorantIndex.

    Soma PRETO (colorant=1) e CORES CMY (colorant=2..4+) de TODOS os hrDeviceIndex encontrados.
    NÃO usa índices fixos! Funciona em Konica, Ricoh, HP, Xerox, Lexmark, Canon... tudo!

    Args:
        diagnostic_mode: se True, loga TUDO (walk bruto, linhas descartadas) para debug Konica.

    Returns: (total, bw, color) ou None se nenhum contador >0 for encontrado.
    """
    BASE_OID_PRINTER_MIB_MARKER = "1.3.6.1.2.1.43.10.2.1"
    try:
        raw = _snmp_walk_raw(ip, BASE_OID_PRINTER_MIB_MARKER, community, timeout)
        if diagnostic_mode:
            logger.warning(
                "[DIAG RFC3805 RAW %s] Qtd itens walk=%s | itens=%s",
                ip,
                len(raw) if isinstance(raw, dict) else 0,
                (str(list(raw.items())[:60])[:1800] + ("..." if len(raw) > 60 else "")) if isinstance(raw, dict) else "None",
            )
        if not raw:
            return None
        bw_sum  = 0
        col_sum = 0
        rows: dict[tuple[int, int], dict[int, int]] = {}
        for suffix, val in raw.items():
            parts = suffix.split(".")
            if len(parts) < 3:
                continue
            try:
                col    = int(parts[0])
                hrdev  = int(parts[1])
                marker = int(parts[2])
            except ValueError:
                continue
            key = (hrdev, marker)
            if key not in rows:
                rows[key] = {}
            rows[key][col] = _parse_int(val)

        if diagnostic_mode:
            discarded_rows = []
            used_rows = []
        for key, row in rows.items():
            colorant = row.get(2, 0)
            unit     = row.get(3, 0)
            life_cnt = row.get(4, 0)
            role_raw = row.get(8, b"")
            role_str = ""
            if isinstance(role_raw, bytes):
                try:
                    role_str = role_raw.decode("utf-8", errors="ignore").lower()
                except Exception:
                    role_str = ""
            elif isinstance(role_raw, str):
                role_str = role_raw.lower()
            is_usable = False
            unit_ok = life_cnt > 0 and (unit in (7, 8, 19, 1, 3, 13, 14))
            if unit_ok:
                is_black = False
                is_color = False
                if colorant == 1:
                    is_black = True
                elif colorant >= 2 and colorant <= 32:
                    is_color = True
                if not is_black and not is_color and role_str:
                    if "black" in role_str:
                        is_black = True
                    elif any(c in role_str for c in ("cyan", "magenta", "yellow", "red", "green", "blue", "color")):
                        is_color = True
                if is_black:
                    bw_sum += life_cnt
                    is_usable = True
                elif is_color:
                    col_sum += life_cnt
                    is_usable = True
            if diagnostic_mode:
                entry = f"hr={key[0]} mrk={key[1]} colidx={colorant} unit={unit} life={life_cnt} role={role_str}"
                if is_usable:
                    used_rows.append(entry)
                else:
                    discarded_rows.append(entry)

        if diagnostic_mode:
            logger.warning(
                "[DIAG RFC3805 ROWS %s] USADAS[%s]=%s | DESCARTADAS[%s]=%s",
                ip,
                len(used_rows), ";".join(used_rows[:25]),
                len(discarded_rows), ";".join(discarded_rows[:40]),
            )

        if bw_sum > 0 or col_sum > 0:
            total = bw_sum + col_sum
            return (total, bw_sum, col_sum)
        return None
    except Exception as exc:
        logger.debug("RFC 3805 marker walk exc %s: %s", ip, exc)
        if diagnostic_mode:
            logger.warning("[DIAG RFC3805 EXC %s] %s", ip, exc)
        return None


def _extract_pen(sys_object_id: Optional[str]) -> Optional[int]:
    """Extrai o PEN (Private Enterprise Number) do OID sysObjectID.
    Formato esperado: 1.3.6.1.4.1.PEN.resto_do_oid.
    Ex: '1.3.6.1.4.1.11.2.3.9.1' → PEN=11 (HP).
    Usado para CONFIRMAR marca, sem depender só de texto em sysDescr."""
    if not sys_object_id:
        return None
    parts = str(sys_object_id).strip().strip(".").split(".")
    # Índices: 0=1, 1=3, 2=6, 3=1, 4=4, 5=1, 6=PEN
    if len(parts) >= 7 and parts[0:6] == ["1", "3", "6", "1", "4", "1"]:
        try:
            return int(parts[6])
        except (ValueError, IndexError):
            return None
    return None


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


def _detect_manufacturer_real(
    sys_descr: Optional[str],
    sys_object_id: Optional[str] = None,
) -> Optional[str]:
    """Detecção REAL de marca: PRIORIDADE 1 = PEN do OID oficial,
    PRIORIDADE 2 = heurística sysDescr (fallback).
    Nunca mais erra marca por texto ambíguo."""
    pen = _extract_pen(sys_object_id)
    if pen and pen in PEN_TO_MANUFACTURER:
        return PEN_TO_MANUFACTURER[pen]
    return _guess_manufacturer(sys_descr)


def _collect_toner_by_manufacturer(
    ip: str,
    community: str,
    timeout: int,
    manufacturer: Optional[str],
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Coleta toner NA ORDEM CERTA da marca (corrige Konica 4=Preto etc).
    Retorna tuple: (preto_%, ciano_%, magenta_%, amarelo_%)
    Ricoh usa OID privado porque a tabela RFC padrão retorna BOGUS (alerta PrinterMS)."""
    black_pct: Optional[float] = None
    cyan_pct: Optional[float] = None
    magenta_pct: Optional[float] = None
    yellow_pct: Optional[float] = None

    # Caso especial RICOH: OID privado .367.3.2.1.2.24.1.1.X
    # Tabela RFC padrão retorna valores falsos (PrinterMS Tier B)
    if manufacturer == "Ricoh":
        try:
            oid_map = [("_b", 1), ("_c", 2), ("_m", 3), ("_y", 4)]
            levels: dict[str, Optional[str]] = {}
            maxs: dict[str, Optional[str]] = {}
            for suf, idx in oid_map:
                levels[suf] = _snmp_get(ip, f"{_BASE_OID_RICOH_TONER_LEVEL}.{idx}", community, timeout)
                maxs[suf]   = _snmp_get(ip, f"{_BASE_OID_RICOH_TONER_MAX}.{idx}",   community, timeout)
            black_pct   = _toner_percent(levels["_b"], maxs["_b"])
            cyan_pct    = _toner_percent(levels["_c"], maxs["_c"])
            magenta_pct = _toner_percent(levels["_m"], maxs["_m"])
            yellow_pct  = _toner_percent(levels["_y"], maxs["_y"])
            return black_pct, cyan_pct, magenta_pct, yellow_pct
        except Exception:
            # Fallthrough para método padrão se OID Ricoh privado não responder
            pass

    # Método padrão RFC 43.11 — com ÍNDICES CORRETOS por marca
    idx_k, idx_c, idx_m, idx_y = (1, 2, 3, 4)  # default RFC
    if manufacturer and manufacturer in TONER_INDEX_MAP:
        idx_k, idx_c, idx_m, idx_y = TONER_INDEX_MAP[manufacturer]

    _lvl_k = _snmp_get(ip, f"1.3.6.1.2.1.43.11.1.1.9.1.{idx_k}", community, timeout)
    _max_k = _snmp_get(ip, f"1.3.6.1.2.1.43.11.1.1.8.1.{idx_k}", community, timeout)
    _lvl_c = _snmp_get(ip, f"1.3.6.1.2.1.43.11.1.1.9.1.{idx_c}", community, timeout)
    _max_c = _snmp_get(ip, f"1.3.6.1.2.1.43.11.1.1.8.1.{idx_c}", community, timeout)
    _lvl_m = _snmp_get(ip, f"1.3.6.1.2.1.43.11.1.1.9.1.{idx_m}", community, timeout)
    _max_m = _snmp_get(ip, f"1.3.6.1.2.1.43.11.1.1.8.1.{idx_m}", community, timeout)
    _lvl_y = _snmp_get(ip, f"1.3.6.1.2.1.43.11.1.1.9.1.{idx_y}", community, timeout)
    _max_y = _snmp_get(ip, f"1.3.6.1.2.1.43.11.1.1.8.1.{idx_y}", community, timeout)

    black_pct   = _toner_percent(_lvl_k, _max_k)
    cyan_pct    = _toner_percent(_lvl_c, _max_c)
    magenta_pct = _toner_percent(_lvl_m, _max_m)
    yellow_pct  = _toner_percent(_lvl_y, _max_y)
    return black_pct, cyan_pct, magenta_pct, yellow_pct


def _collect_pages_vendor_specific(
    ip: str,
    community: str,
    timeout: int,
    manufacturer: Optional[str],
    model: Optional[str] = None,
) -> tuple[int, int, int]:
    """Tenta COLETA SEGURA usando OIDs PRIVADOS da marca (Tier A/B).
    Retorna tuple (total, bw, color). Zeros = não encontrou OID específico,
    então quem chama cai para o fallback RFC / Marker table.

    ⛔ REGRAS DE COBRANÇA SEGURA (NUNCA INVENTA):
    • TIER D (Toshiba/Epson laser/OKI/Pantum) = SÓ TOTAL → (total, total, 0)
    • HP/Konica/Xerox/Lexmark = leem escalares/WALK OFICIAL.
    • Ricoh = Total privado + WALK tabela .19 por LABEL (não folhas fixas!).
    • Qualquer dúvida = retorna 0,0,0 → quem chama usa fallback."""
    # PATCH 6 (21/09): TRACE de entrada para diagnosticar POR QUE a Konica C308 retornava 0,0,0
    logger.warning(
        "[DIAG VENDOR ENTER] IP=%s manufacturer=[%s] model=[%s] TierD?=%s",
        ip, manufacturer or "NONE", (model or "").strip()[:60],
        manufacturer in MANUFACTURERS_TIER_D_ONLY_TOTAL if manufacturer else "n/a",
    )
    total = 0
    bw = 0
    color = 0

    # ===== TIER D: SÓ EXISTE TOTAL CONFIRMADO → NUNCA INVENTA COLORIDO =====
    if manufacturer in MANUFACTURERS_TIER_D_ONLY_TOTAL:
        # Mesmo Epson LASER (não é EcoTank): só total.
        # EcoTank (L3250 etc) cai aqui mas Marker Table heurística permitida SÓ p/ eles lá embaixo.
        rfc_total = _parse_int(_snmp_get(ip, OID_PAGES_TOTAL, community, timeout)) or 0
        logger.warning("[DIAG VENDOR TIERD] IP=%s manufacturer=%s rfc_total=%s -> retorna (t=%s,b=%s,c=0)", ip, manufacturer, rfc_total, rfc_total, rfc_total)
        if rfc_total > 0:
            return (rfc_total, rfc_total, 0)
        return (0, 0, 0)

    try:
        # ===== HP (Tier A): 3 escalares diretos 100% confiáveis =====
        if manufacturer == "HP":
            hp_t = _parse_int(_snmp_get(ip, _OID_HP_TOTAL, community, timeout)) or 0
            hp_b = _parse_int(_snmp_get(ip, _OID_HP_BW,    community, timeout)) or 0
            hp_c = _parse_int(_snmp_get(ip, _OID_HP_COLOR, community, timeout)) or 0
            if hp_t > 0 or hp_b > 0 or hp_c > 0:
                total = max(total, hp_t, hp_b + hp_c)
                bw    = hp_b
                color = hp_c
                logger.warning("[DIAG VENDOR RETURN] IP=%s src=HP t=%s b=%s c=%s", ip, total, bw, color)
                return (total, bw, color)

        # ===== Konica Minolta (Tier A): Copy + Print somados (contador OFICIAL) =====
        #         CASO ESPECIAL bizhub C308 (cliente 117): firmwares diferentes usam OIDs DIFERENTES!
        #         Tentamos 3 conjuntos (Original / Conjunto B Total direto / Conjunto C indice 1)
        #         + 10 sufixos de 0 a 9 (para cobrir índices de tabela)
        #         PATCH 5 (21/09 16h): Adicionamos TAMBÉM varredura da ÁRVORE GERAL de Contadores KM:
        #           1.3.6.1.4.1.18334.1.1.1.5.7.2.{0..20}.0 → essa árvore tem o TOTAL GERAL (índice 2 que já funciona!)
        #           e os outros índices (0, 1, 3..20) são Total Preto, Total Color, Duplex, A3 etc OFICIAIS!
        if manufacturer == "Konica Minolta":
            logger.warning("[DIAG KONICA BLOCK ENTER] IP=%s model=%s -> EXECUTANDO SUPERBLOCO KONICA MINOLTA PATCH7 PRINTWAYY!", ip, (model or "")[:60])
            def _km_read(base_oid: str) -> int:
                """Lê UM OID com até 10 variações de sufixo (0 a 9). Retorna PRIMEIRO valor >0 encontrado."""
                for suffix in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
                    v = _parse_int(_snmp_get(ip, f"{base_oid}.{suffix}", community, timeout)) or 0
                    if v > 0:
                        return v
                return 0

            # =====================================================================
            # PATCH 7 (21/09 17h): ÁRVORE NOVA PRINTWAYY OFICIAL - EXTRAÍDA DE DLL .NET PAGO
            #   OID base = 1.3.6.1.4.1.18334.1.1.2.1.5.7.20.1.1.9  (árvore DIFERENTE da velha 1.1.1!)
            #   Essa é a árvore que realmente funciona na bizhub C308 cliente 117!
            #
            # PATCH 7.2 (21/09 18h): MODO SUPER-DIAG NAO-CLASSIFICATORIO (SEGURANCA MAXIMA!)
            #   NÃO CLASSIFICA BW / COLOR por tamanho de número NEM POR ÍNDICE SEM PROVA!
            #   Apenas VARRE TODOS os X = 0..30 e sufixos ("", .0, .1, .2, .3, .4, .5, .6, .7, .8, .9)
            #   e LOGA TUDO PARA O TÉCNICO COMPARAR COM O PAINEL FÍSICO FOTOGRAFADO.
            #   Depois que tivermos os valores REAIS do painel (Total = X, BW = Y, Color = Z),
            #   gravamos hardcoded EXATAMENTE qual X (e qual sufixo) corresponde a cada um.
            # =====================================================================
            KM_PRINTWAYY_BASE = "1.3.6.1.4.1.18334.1.1.2.1.5.7.20.1.1.9"
            pw_vals: dict[str, int] = {}  # key = sufixo lido ex: ".2.0", value = valor
            pw_total = 0
            pw_bw = 0
            pw_clr = 0
            pw_src = ""
            SUFS = ("", ".0", ".1", ".2", ".3", ".4", ".5", ".6", ".7", ".8", ".9")
            for pw_x in range(0, 31):  # X de 0 a 30
                for pw_suf in SUFS:
                    oid_full = f"{KM_PRINTWAYY_BASE}.{pw_x}{pw_suf}"
                    v = _parse_int(_snmp_get(ip, oid_full, community, timeout)) or 0
                    if v > 0:
                        key = f".{pw_x}{pw_suf}"
                        pw_vals[key] = v
                        if v > pw_total:
                            pw_total = v
            # ==================================================================
            # TÁTICA #0 (PRIORIDADE MÁXIMA! 100% IGUAL O PRINTWAYY!)
            # USA X=3 (Geral cor total) DIRETO como valor de colorido!
            # O PrintWayy NAO soma "2-cores" no Geral cor total (apenas 3+4 cores),
            # e a gente tem que ficar exatamente igual pra nao ter diferença de cobrança.
            #
            # PROVA MATEMATICA DO CLIENTE 117 (PAPELARIA EXATA):
            #   X=1 (Total)     = 429.799
            #   X=2 (P&B)       = 159.499
            #   X=3 (Color dir) = 270.290 ← USA ESSE AQUI, IGUAL PRINTWAYY!
            #   X=2+X=3         = 429.789 ≈ 429.799 (falta 10 = "2 cores", PrintWayy ignora!)
            #
            # A formula "DIF = X1 - X2" dava 270.300 (inclui as 2-cores) → causava
            # diferença de 10 copias vs PrintWayy. NAO USAR MAIS COMO PRINCIPAL!
            # ==================================================================
            fixed_pair_found = False
            for suf1 in SUFS:
                k_total = f".1{suf1}"
                kbw     = f".2{suf1}"
                kclr    = f".3{suf1}"
                vt = pw_vals.get(k_total, 0)
                vb = pw_vals.get(kbw, 0)
                vc_direct = pw_vals.get(kclr, 0)
                if vb <= 0 or vc_direct <= 0:
                    continue   # X=3 colorido direto tem que existir e ser > 0!

                # VALIDACAO: X=2 (P&B) + X=3 (Color direto) tem que ser ≈ X=1 (Total)
                # Tolerância de ~0.5% (até ~2000 paginas de diferenca por "2-cores" etc)
                pw_check = vt if vt > 0 else pw_total
                s_pb_clr = vb + vc_direct
                if pw_check > 0:
                    if not (pw_check * 0.995 <= s_pb_clr <= pw_check * 1.005):
                        # Mesmo que feche 100% com P&B+Color=Total, aceita!
                        if s_pb_clr != pw_check:
                            continue
                else:
                    if s_pb_clr <= 0:
                        continue

                # ✅ TUDO OK! USA VALOR DIRETO DE X=3 COMO COLORIDO (igual PrintWayy!)
                # 🔒 AJUSTE CRITICO DE FECHAMENTO (PROBLEMA 2-CORES!):
                # PrintWayy exclui "2-cores" do Geral cor total, logo a SOMA
                # P&B(X2) + COLOR(X3) = s_pb_clr = 429.789, e X1 = 429.799 (10 dif!)
                # SE USARMOS X1 COMO TOTAL → RELATORIO NAO FECHA, DIF. DE 10 PÁGINAS!
                # SOLUCAO (IGUAL PRINTWAYY POR BAIXO DOS PANOS): TRAVAR pw_total
                # NA SOMA s_pb_clr (P&B+COLOR). As "2-cores" ficam invisiveis no card
                # TOTAL (como nao cobramos elas de qualquer forma, nao tem problema!)
                pw_total = s_pb_clr
                pw_bw    = vb
                pw_clr   = vc_direct   # 270.290 EXATO IGUAL PRINTWAYY!
                pw_src   = (f"KM-PRINTWAYY-X3-EQUALS-PROOF"
                           f"(X2BW={vb},X3COLOR={vc_direct},"
                           f"SOMA-TRAVADA={s_pb_clr},X1_TOTAL_NAO_USADO={pw_check if pw_check>0 else 'N/A'},"
                           f"2CORES_EXCLUIDAS_OK)")
                fixed_pair_found = True
                break
            if not fixed_pair_found:
                # ==============================================================
                # TÁTICA #0B (FALLBACK SE X=3 = 0 OU QUEBROU):
                # AÍ SIM USA A DIFERENÇA (Total - P&B) pra não perder colorido!
                # ==============================================================
                for suf1 in SUFS:
                    k_total = f".1{suf1}"
                    kbw     = f".2{suf1}"
                    kclr    = f".3{suf1}"
                    vt = pw_vals.get(k_total, 0)
                    vb = pw_vals.get(kbw, 0)
                    if vt <= 0 or vb <= 0:
                        continue
                    if vb > vt:
                        continue
                    vc_calc = vt - vb
                    if vc_calc < 0:
                        continue
                    # Aceita se a soma fecha (sempre fecha por construção!)
                    pw_total = max(pw_total, vt)
                    pw_bw    = vb
                    pw_clr   = vc_calc
                    pw_src   = (f"KM-PRINTWAYY-DIF-FALLBACK"
                               f"(X3=0→USOU-DIF={vt}-{vb}=COLOR={vc_calc})")
                    fixed_pair_found = True
                    break
            if not fixed_pair_found:
                # ==============================================================
                # TÁTICA #1 (FALLBACK SE DIF JULIO NAO FUNCIONAR):
                # X=2 SEMPRE BW / X=3 SEMPRE COLOR, como confirmado na PrintWayy
                # ==============================================================
                for suf1 in SUFS:
                    k_total = f".1{suf1}"
                    kbw     = f".2{suf1}"
                    kclr    = f".3{suf1}"
                    vt = pw_vals.get(k_total, 0)
                    vb = pw_vals.get(kbw, 0)
                    vc = pw_vals.get(kclr, 0)
                    if vb <= 0 or vc <= 0:
                        continue
                    s = vb + vc
                    pw_check = vt if vt > 0 else pw_total
                    if pw_check > 0 and (pw_check * 0.92 <= s <= pw_check * 1.08):
                        pw_total = max(pw_total, s, vt)
                        pw_bw   = vb           # NÃO INVERTE NUNCA! X=2 é SEMPRE BW
                        pw_clr  = vc           # NÃO INVERTE NUNCA! X=3 é SEMPRE COLOR
                        pw_src  = (f"KM-PRINTWAYY-FIXEDIDX-PROOF"
                                   f"(X=1=TOTAL={vt if vt>0 else s},"
                                   f"X=2=BW={vb},"
                                   f"X=3=CLR={vc},"
                                   f"SOMA={s}≈{pw_check})")
                        fixed_pair_found = True
                        break
            if not fixed_pair_found and pw_total > 0 and len(pw_vals) >= 2:
                # ==============================================================
                # TATICA #2 (FALLBACK SEGURO - APENAS SE FIXEDIDX NÃO BATER!)
                # NOVA REGRA FALLBACK: busca QUALQUER PAR DE X (a,b) que some ≈ total
                # SEM INVERTER A ORDEM DOS ÍNDICES (sempre X menor = BW, X maior = Color)
                # Baseado no padrão Konica (índice baixo = BW / índice alto = Color)
                # ==============================================================
                items_kv = sorted(pw_vals.items(),
                                  key=lambda kv: tuple(int(p) for p in kv[0].strip('.').split('.') if p))
                best_pair_pw_sum = 0
                best_pair_pw_kv = None
                pw_threshold_skip_total = pw_total * 0.95
                for i in range(len(items_kv)):
                    ki, vi = items_kv[i]
                    if vi <= 0 or vi >= pw_threshold_skip_total:
                        continue
                    for j in range(len(items_kv)):
                        if i == j: continue
                        kj, vj = items_kv[j]
                        # ORDEM DOS ÍNDICES (padrão Konica): ki vem ANTES que kj?
                        #   → vi = BW  (menor índice)
                        #   → vj = CLR (maior índice)
                        # SE NÃO ESTIVEREM EM ORDEM, PULA (evita inverter!)
                        parts_i = tuple(int(p) for p in ki.strip('.').split('.') if p)
                        parts_j = tuple(int(p) for p in kj.strip('.').split('.') if p)
                        if parts_i >= parts_j:
                            continue
                        if vj <= 0 or vj >= pw_threshold_skip_total:
                            continue
                        s = vi + vj
                        if (pw_total * 0.92 <= s <= pw_total * 1.08) and s > best_pair_pw_sum:
                            best_pair_pw_sum = s
                            best_pair_pw_kv = ((ki, vi), (kj, vj))
                if best_pair_pw_kv is not None:
                    (ki, vi), (kj, vj) = best_pair_pw_kv
                    diff_ratio = (max(vi, vj) - min(vi, vj)) / pw_total if pw_total > 0 else 99
                    if diff_ratio < 0.20:
                        pw_bw = pw_total
                        pw_clr = 0
                        pw_src = f"KM-PRINTWAYY(INCONCLUSIVE-same-magnitude→{ki}={vi}|{kj}={vj}→total-only)"
                    else:
                        # ORDEM KONICA (índice baixo = BW, índice alto = Color) NÃO INVERTE!
                        pw_bw, pw_clr = vi, vj
                        pw_src  = (f"KM-PRINTWAYY-FALLBACK-IDX-ORDER"
                                   f"({ki}=BW={vi},{kj}=CLR={vj},SOMA={best_pair_pw_sum}≈{pw_total})")
                elif pw_total > 0:
                    pw_bw = pw_total
                    pw_clr = 0
                    pw_src = f"KM-PRINTWAYY(total-only={pw_total})"
            if pw_total > 0 and pw_bw == 0 and pw_clr == 0:
                pw_bw = pw_total
                pw_clr = 0
                pw_src = f"KM-PRINTWAYY(total-only={pw_total})"
            # ================================================================
            # SUPER LOG DIAGNOSTICO (TODOS OS VALORES, NA MESMA LINHA!)
            # Isso é a PROVA REAL: o técnico comparar com a FOTO DO PAINEL FÍSICO.
            # Formato: X=valor (ordenado por X)
            # ================================================================
            def _sorted_keys_numeric(d: dict) -> list:
                def kparse(k: str):
                    parts = [p for p in k.strip('.').split('.') if p]
                    return tuple(int(p) for p in parts)
                return sorted(d.keys(), key=kparse)
            pw_pairs_diag = " ".join(f"{k}={pw_vals[k]}" for k in _sorted_keys_numeric(pw_vals))
            logger.warning(
                "[DIAG KONICA PRINTWAYY SUPERDIAG-CLIENTE117] IP=%s base=%s TOTAL_GERAL=%s PARES_ORDENADOS_POR_X=[%s] RESULTADO=%s (t=%s b=%s c=%s) | COMPARAR COM FOTO PAINEL FISICO!",
                ip, KM_PRINTWAYY_BASE, pw_total, pw_pairs_diag, pw_src or "NONE", pw_total, pw_bw, pw_clr,
            )

            # ===== PATCH 5b: VARREDURA GERAL CONTADORES KONICA (1.3.6.1.4.1.18334.1.1.1.5.7.2.{idx}.0) =====
            #   SABEMOS QUE idx=2 funciona (364477 / 429815)! Vamos ler idx 0..20 pra ver quais existem!
            KM_GENERAL_COUNTERS_BASE = "1.3.6.1.4.1.18334.1.1.1.5.7.2"
            gen_counters_vals: list[int] = []
            gen_counters_str_parts: list[str] = []
            for km_idx in range(0, 21):  # 0 a 20 inclusive
                v = _parse_int(
                    _snmp_get(ip, f"{KM_GENERAL_COUNTERS_BASE}.{km_idx}.0", community, timeout)
                ) or 0
                gen_counters_vals.append(v)
                if v > 0:
                    gen_counters_str_parts.append(f".{km_idx}.0={v}")
            gen_counters_hint_bw = 0
            gen_counters_hint_clr = 0
            gen_counters_hint_used = ""
            # Tenta encontrar o melhor par (idx_x, idx_y) tal que idx_x + idx_y ≈ maior_valor (total geral idx=2
            max_gen_total = gen_counters_vals[2] if len(gen_counters_vals) > 2 else 0
            if max_gen_total <= 0:
                max_gen_total = max(gen_counters_vals) if gen_counters_vals else 0
            if max_gen_total > 0:
                    best_pair_sum = 0
                    best_pair = None
                    for i in range(len(gen_counters_vals)):
                        vi = gen_counters_vals[i]
                        if vi <= 0 or vi >= max_gen_total * 1.05:
                            continue
                        for j in range(len(gen_counters_vals)):
                            if i == j:
                                continue
                            vj = gen_counters_vals[j]
                            if vj <= 0:
                                continue
                            s = vi + vj
                            if (max_gen_total * 0.92 <= s <= max_gen_total * 1.08) and s > best_pair_sum:
                                best_pair_sum = s
                                best_pair = (i, j)
                    if best_pair is not None:
                        # Assume MENOR = Color, MAIOR = BW (regra conservadora! Depois confirmamos com is_color)
                        ia, ib = best_pair
                        va, vb = gen_counters_vals[ia], gen_counters_vals[ib]
                        if va <= vb:
                            gen_counters_hint_clr, gen_counters_hint_bw = va, vb
                            order = "cl={ia}+bw={ib}"
                        else:
                            gen_counters_hint_clr, gen_counters_hint_bw = vb, va
                            order = f"bw={ib}+cl={ia}"
                        gen_counters_hint_used = f"GENERAL[{order}={gen_counters_hint_bw}+{gen_counters_hint_clr}≈{best_pair_sum}"

            # Leitura de DIAGNÓSTICO (todas as 3 fontes + valores originais SEM fallback)
            # Conjunto A (original, Copy/Print BW/Color separados)
            setA_copy_b  = _km_read(_OID_KM_COPY_BW.rsplit(".", 1)[0])
            setA_print_b = _km_read(_OID_KM_PRINT_BW.rsplit(".", 1)[0])
            setA_copy_c  = _km_read(_OID_KM_COPY_COLOR.rsplit(".", 1)[0])
            setA_print_c = _km_read(_OID_KM_PRINT_COLOR.rsplit(".", 1)[0])
            setA_tot     = _km_read(_OID_KM_TOTAL.rsplit(".", 1)[0])
            setA_bw      = setA_copy_b + setA_print_b
            setA_clr     = setA_copy_c + setA_print_c

            # Conjunto B (Total Counter BW/Color/TOT direto — Conjunto PrinterMS C368)
            setB_bw      = _km_read(_KM_ALT_B_TOTAL_BW.rsplit(".", 1)[0])
            setB_clr     = _km_read(_KM_ALT_B_TOTAL_CLR.rsplit(".", 1)[0])
            setB_tot     = _km_read(_KM_ALT_B_TOTAL_TOT.rsplit(".", 1)[0])

            # Conjunto C (índice .1 — bizhub C308 firmware 2020+)
            setC_copy_b  = _km_read(_KM_ALT_C_COPY_BW.rsplit(".", 1)[0])
            setC_print_b = _km_read(_KM_ALT_C_PRINT_BW.rsplit(".", 1)[0])
            setC_copy_c  = _km_read(_KM_ALT_C_COPY_CLR.rsplit(".", 1)[0])
            setC_print_c = _km_read(_KM_ALT_C_PRINT_CLR.rsplit(".", 1)[0])
            setC_tot     = _km_read(_KM_ALT_C_TOTAL.rsplit(".", 1)[0])
            setC_bw      = setC_copy_b + setC_print_b
            setC_clr     = setC_copy_c + setC_print_c

            # Diagnóstico: pega o RESULTADO do RFC 3805 já calculado (para loggar se >0)
            rfc3805_for_km: Optional[tuple[int, int, int]] = None

            # ===== ESCOLHE QUAL CONJUNTO DE OIDs RETORNA O MELHOR RESULTADO =====
            # Prioridade -1 (PATCH 7 PRINTWAYY!): ÁRVORE NOVA 1.1.2.1.5.7.20.1.1.9 - MÁXIMA PRIORIDADE
            # ⚠️ AJUSTE 7.4b CLIENTE 117 ATUALIZAÇÃO FIRMWARE: SE pw_total < 1000 É MODELO/SERIAL, NÃO É CONTADOR!
            chosen_tot = 0
            chosen_bw  = 0
            chosen_clr = 0
            chosen_src = ""
            pw_cand_total = max(pw_total, pw_bw + pw_clr)
            pw_is_real_counter = pw_cand_total >= 1000 and (pw_clr > 0 or pw_bw > 0)
            if pw_is_real_counter:
                chosen_tot = pw_cand_total
                chosen_bw  = pw_bw
                chosen_clr = pw_clr
                chosen_src = pw_src or "KM-PRINTWAYY"
            # Prioridade 0: CONTADORES GERAIS (árvore 7.2.*) se achou par E PRINTWAYY não deu COLOR>0
            if gen_counters_hint_bw > 0 and gen_counters_hint_clr > 0 and chosen_clr == 0:
                cand_tot = max(max_gen_total, gen_counters_hint_bw + gen_counters_hint_clr)
                if cand_tot >= chosen_tot * 0.9 or chosen_tot == 0:
                    chosen_tot = cand_tot
                    chosen_bw  = gen_counters_hint_bw
                    chosen_clr = gen_counters_hint_clr
                    chosen_src = f"KM-GENERAL({gen_counters_hint_used})"
            # Prioridade 1: quem tiver COLOR REAL > 0 GANHA (independente de conjunto)
            # Tenta Conjunto A (se tem color >0 ou total maior e PRINTWAYY/Gen não resolveram color)
            if (setA_clr > 0 and (setA_bw + setA_clr) > 0) or (setA_tot > 0 and not chosen_src):
                cand_tot = max(setA_tot, setA_bw + setA_clr)
                if (setA_clr > 0 and cand_tot >= chosen_tot * 0.9) or chosen_clr == 0:
                    chosen_tot = cand_tot
                    chosen_bw  = setA_bw
                    chosen_clr = setA_clr
                    chosen_src = "KM-SetA(CopyPrint)"
            # Tenta Conjunto B (se tem COLOR REAL > 0, SOBRESCREVE o A!)
            if setB_clr > 0 and (setB_bw + setB_clr) > 0:
                cand_tot = max(setB_tot, setB_bw + setB_clr)
                if cand_tot >= chosen_tot * 0.9 or chosen_clr == 0:
                    chosen_tot = cand_tot
                    chosen_bw  = setB_bw
                    chosen_clr = setB_clr
                    chosen_src = "KM-SetB(TotalDireto)"
            # Tenta Conjunto C (se tem COLOR REAL > 0, SOBRESCREVE!)
            if setC_clr > 0 and (setC_bw + setC_clr) > 0:
                cand_tot = max(setC_tot, setC_bw + setC_clr)
                if cand_tot >= chosen_tot * 0.9 or chosen_clr == 0:
                    chosen_tot = cand_tot
                    chosen_bw  = setC_bw
                    chosen_clr = setC_clr
                    chosen_src = "KM-SetC(idx1)"
            # Se nenhum conjunto retornou COLOR > 0, retorna o que tem o TOTAL MAIOR
            if chosen_clr == 0:
                candidates = [
                    (pw_total, pw_bw, pw_clr, pw_src or "KM-PRINTWAYY"),
                    (max(setA_tot, setA_bw + setA_clr), setA_bw, setA_clr, "KM-SetA(CopyPrint)"),
                    (max(setB_tot, setB_bw + setB_clr), setB_bw, setB_clr, "KM-SetB(TotalDireto)"),
                    (max(setC_tot, setC_bw + setC_clr), setC_bw, setC_clr, "KM-SetC(idx1)"),
                ]
                candidates.sort(key=lambda x: x[0], reverse=True)
                if candidates[0][0] > 0 and (not chosen_src or candidates[0][0] > chosen_tot * 1.05):
                    chosen_tot, chosen_bw, chosen_clr, chosen_src = candidates[0]

            # ===== FALLBACK RFC 3805 SE AINDA TIVER COLOR=0 =====
            # PATCH 5: Chamamos com diagnostic_mode=True para logar TUDO (bruto!)
            if chosen_clr == 0 and chosen_tot > 0:
                rfc3805_for_km = _collect_pages_printer_mib_rfc(ip, community, timeout, diagnostic_mode=True)
                if rfc3805_for_km and rfc3805_for_km[2] > 0:
                    rfc_t, rfc_b, rfc_c = rfc3805_for_km
                    chosen_tot = max(chosen_tot, rfc_t)
                    chosen_clr = rfc_c
                    chosen_bw  = max(0, chosen_tot - chosen_clr)
                    chosen_src = f"{chosen_src}+RFC3805"

            # ===== LOG DE DIAGNÓSTICO AUTOMÁTICO (aparece SEMPRE em Konica!) =====
            #   O funcionário NÃO PRECISA FAZER NADA! O log já sai no coleta automática de 30/30 min,
            #   e a gente vê no retorno do backend / leitura da impressora.
            gen_str = " ".join(gen_counters_str_parts) if gen_counters_str_parts else "N/A"
            rfc_str = (f"tot={rfc3805_for_km[0]} bw={rfc3805_for_km[1]} clr={rfc3805_for_km[2]}") if rfc3805_for_km else "N/A"
            pw_summary = f"src={pw_src or 'NONE'} vals=[{pw_diag_str}]"
            logger.warning(
                "[DIAG KONICA %s] IP=%s PW[%s tot=%s bw=%s clr=%s] "
                "SetA[tot=%s bw=%s(cp=%s+pr=%s) clr=%s(cp=%s+pr=%s)] "
                "SetB[tot=%s bw=%s clr=%s] SetC[tot=%s bw=%s(cp=%s+pr=%s) clr=%s(cp=%s+pr=%s)] "
                "GEN[%s] RFC3805=%s CHOSEN[src=%s tot=%s bw=%s clr=%s]",
                (model or "").strip() or "?", ip,
                pw_summary, pw_total, pw_bw, pw_clr,
                setA_tot, setA_bw, setA_copy_b, setA_print_b, setA_clr, setA_copy_c, setA_print_c,
                setB_tot, setB_bw, setB_clr,
                setC_tot, setC_bw, setC_copy_b, setC_print_b, setC_clr, setC_copy_c, setC_print_c,
                gen_str, rfc_str,
                chosen_src or "NONE", chosen_tot, chosen_bw, chosen_clr,
            )

            if chosen_tot > 0 or chosen_bw > 0 or chosen_clr > 0:
                return (chosen_tot, chosen_bw, chosen_clr)

        # ===== Xerox (Tier A): 3 escalares diretos =====
        if manufacturer == "Xerox":
            xe_t = _parse_int(_snmp_get(ip, _OID_XEROX_TOTAL, community, timeout)) or 0
            xe_b = _parse_int(_snmp_get(ip, _OID_XEROX_BW,    community, timeout)) or 0
            xe_c = _parse_int(_snmp_get(ip, _OID_XEROX_COLOR, community, timeout)) or 0
            if xe_t > 0 or xe_b > 0 or xe_c > 0:
                total = max(xe_t, xe_b + xe_c)
                bw    = xe_b
                color = xe_c
                return (total, bw, color)

        # ===== Sharp (Tier C): escalares PB/Color fixos =====
        if manufacturer == "Sharp":
            sh_b = _parse_int(_snmp_get(ip, _OID_SHARP_BW,    community, timeout)) or 0
            sh_c = _parse_int(_snmp_get(ip, _OID_SHARP_COLOR, community, timeout)) or 0
            if sh_b > 0 or sh_c > 0:
                rfc_t = _parse_int(_snmp_get(ip, OID_PAGES_TOTAL, community, timeout)) or 0
                total = max(rfc_t, sh_b + sh_c)
                bw    = sh_b
                color = sh_c
                return (total, bw, color)

        # ===== Ricoh (Tier B): WALK tabela .19.X, resolve PB/Color POR LABEL =====
        #        (PrinterMS alerta: NÃO USAR folhas fixas .9.22/.9.21 — refutadas em campo!)
        if manufacturer == "Ricoh":
            ric_total_priv = _parse_int(_snmp_get(ip, _OID_RICOH_TOTAL, community, timeout)) or 0
            try:
                labels = _snmp_walk_table_raw_strings(ip, _BASE_OID_RICOH_COUNTER_LABEL, community, timeout)
                values = _snmp_walk_table(ip, _BASE_OID_RICOH_COUNTER_VALUE, community, timeout)
                r_bw = 0
                r_col = 0
                for k, val in values.items():
                    lbl_raw = labels.get(k, "")
                    if not lbl_raw:
                        continue
                    lbl_low = str(lbl_raw).lower()
                    # PALAVRAS QUE DEFINEM PRETO & BRANCO no painel Ricoh
                    is_bw = (
                        "black" in lbl_low or "mono" in lbl_low or "monochrome" in lbl_low
                        or "b&w" in lbl_low or "bw" in lbl_low or "preto" in lbl_low
                        or "pb" in lbl_low or "p&b" in lbl_low
                        or ("copier" in lbl_low and "color" not in lbl_low and "full" not in lbl_low)
                    )
                    # PALAVRAS QUE DEFINEM COLORIDO
                    is_col = (
                        "color" in lbl_low or "colour" in lbl_low
                        or "full" in lbl_low and "color" in lbl_low
                        or "colorido" in lbl_low or "cor" in lbl_low
                    )
                    # Ignora contadores de duplex, A3, scanner, fax, economia etc.
                    only_side = any(w in lbl_low for w in (
                        "side", "face", "duplex", "a3", "a4", "letter", "legal",
                        "sheet", "faxes", "fax", "scanner", "scan", "send",
                        "economy", "econ", "low cov", "coverage", "mid cov", "high cov",
                    )) and not ("bw" in lbl_low or "black" in lbl_low or "color" in lbl_low or "copy" in lbl_low or "print" in lbl_low or "total" in lbl_low)
                    if only_side:
                        continue
                    if is_col:
                        r_col += val
                    elif is_bw:
                        r_bw += val
                    # labels ambíguas (só "copy" sem bw/color) = soma em PB (segurança)
                    elif any(w in lbl_low for w in ("total", "copy", "print", "printer")):
                        # Contador "Total Geral", "Printer Total", "Copier Total" etc = PB (segurança, não inventa cor)
                        pass  # não usa, pois temos total privado separado
                if r_bw > 0 or r_col > 0:
                    total = max(ric_total_priv, r_bw + r_col)
                    bw    = r_bw
                    color = r_col
                    return (total, bw, color)
                elif ric_total_priv > 0:
                    # Tem total, mas não conseguiu split por label → só total, fallback PB
                    return (ric_total_priv, ric_total_priv, 0)
            except Exception:
                if ric_total_priv > 0:
                    return (ric_total_priv, ric_total_priv, 0)

        # ===== Lexmark (Tier A): WALK type codes — 3=totalMono, 4=totalColor, 2=total =====
        if manufacturer == "Lexmark":
            lex_walk = _snmp_walk_table(ip, _BASE_OID_LEXMARK_COUNT, community, timeout)
            # Formato walk: key = "1.TYPECODE" ou "TYPECODE" direto
            lx: dict[int, int] = {}
            for k, v in lex_walk.items():
                try:
                    t = int(k.split(".")[-1])
                    if t > 0 and v > 0:
                        lx[t] = lx.get(t, 0) + v
                except Exception:
                    continue
            if 2 in lx or 3 in lx or 4 in lx:
                total = max(lx.get(2, 0), lx.get(3, 0) + lx.get(4, 0))
                bw    = lx.get(3, 0)
                color = lx.get(4, 0)
                return (total, bw, color)

        # ===== Canon (Tier B): WALK type codes — 101=total, 108=mono, 122+123=color =====
        if manufacturer == "Canon":
            cn_walk = _snmp_walk_table(ip, _BASE_OID_CANON_COUNT, community, timeout)
            cn: dict[int, int] = {}
            for k, v in cn_walk.items():
                try:
                    t = int(k.split(".")[-1])
                    if t > 0 and v > 0:
                        cn[t] = cn.get(t, 0) + v
                except Exception:
                    continue
            if 101 in cn or 108 in cn or 122 in cn or 123 in cn:
                cn_t = cn.get(101, 0)
                cn_b = cn.get(108, 0)
                cn_c = cn.get(122, 0) + cn.get(123, 0)
                total = max(cn_t, cn_b + cn_c)
                bw    = cn_b
                color = cn_c
                logger.warning("[DIAG VENDOR RETURN] IP=%s src=Canon-101/108/122/123 t=%s b=%s c=%s", ip, total, bw, color)
                return (total, bw, color)

    except Exception as e_vendor:
        logger.warning("[DIAG VENDOR EXCEPTION] IP=%s manufacturer=%s err=%s exc_type=%s", ip, manufacturer or "?", str(e_vendor)[:200], type(e_vendor).__name__)
        logger.debug("vendor_specific pages falhou %s (%s): %s", ip, manufacturer or "?", e_vendor)

    # 🔧 FALLBACK GLOBAL RFC 3805: Se nenhum OID privado respondeu (ou retornou zeros),
    #    tenta WALK tabela prtMarkerTable por ColorantIndex (funciona em QUALQUER impressora!)
    try:
        rfc3805 = _collect_pages_printer_mib_rfc(ip, community, timeout)
        if rfc3805 and (rfc3805[0] > 0 or rfc3805[1] > 0 or rfc3805[2] > 0):
            logger.warning("[DIAG VENDOR RETURN] IP=%s src=fallback_global_RFC3805 t=%s b=%s c=%s", ip, rfc3805[0], rfc3805[1], rfc3805[2])
            return rfc3805
    except Exception as exc:
        logger.warning("[DIAG VENDOR RFC3805_EXCEPTION] IP=%s err=%s", ip, str(exc)[:200])
        logger.debug("fallback global RFC3805 exc %s: %s", ip, exc)

    # Nenhum OID privado respondeu → retorna zeros, quem chama usa fallback RFC
    logger.warning("[DIAG VENDOR RETURN] IP=%s src=NONE (vendor+fallback RFC3805 ALL ZEROS) -> retorna 0,0,0 (Marker Table sera usada!)", ip)
    return (0, 0, 0)


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

def collect_printer(ip: str, community: str = "public", timeout: int = 5) -> Optional[PrinterData]:
    # ==========================================================================
    # 🏆 NOVO FLUXO DE COLETA SEGURA — NUNCA MAIS INVENTA PÁGINAS COLORIDAS!
    #    Ordem de prioridade (do MAIS SEGURO → fallback):
    #      1) 🥇 DETECTA MARCA (PEN sysObjectID + sysDescr) ANTES de coletar!
    #      2) 🥇 OIDs PRIVADOS DA MARCA (Tier A/B) → _collect_pages_vendor_specific
    #      3) 🥈 OIDs FIXOS RFC .1.2 / .1.3 (HP antigo / marcas Tier D)
    #      4) 🟣 Marker Table COM roles CMYK (prtMarkerColorantRole)
    #      5) 🟡 SÓ EXCEÇÃO: Marker SEM roles + Epson EcoTank (L3xxx) + toner CMY>0%
    #            → Roda heurística maior=preto SÓ NESSE CASO.
    #      6) 🟢 FALLBACK FINAL SEGURO: só total → tudo PB, color = 0.
    # ==========================================================================

    # ========= PASSO 0: Dados básicos + valida que É impressora =========
    sys_descr = _snmp_get(ip, OID_SYS_DESCR, community, timeout)
    if not sys_descr:
        return None
    if not _looks_like_printer(sys_descr):
        logger.debug("%s responde SNMP mas nao parece impressora: %s", ip, sys_descr[:80])
        return None

    model = _snmp_get(ip, OID_PRINTER_MODEL, community, timeout) or sys_descr[:120]
    if model:
        model = model.strip()
    serial_raw = _snmp_get(ip, OID_PRINTER_SERIAL, community, timeout)
    serial = serial_raw.strip() if serial_raw else None

    # ========= PASSO 1: MARCA REAL (PEN do sysObjectID OFICIAL + sysDescr fallback) =========
    sys_oid = _snmp_get(ip, OID_SYS_OBJECT_ID, community, timeout)
    manufacturer = _detect_manufacturer_real(sys_descr, sys_oid)

    # ========= PASSO 2: TONER NA ORDEM CERTA DA MARCA (corrige Konica 4=Preto / Ricoh privado) =========
    toner_black, toner_cyan, toner_magenta, toner_yellow = _collect_toner_by_manufacturer(
        ip, community, timeout, manufacturer,
    )

    # ========= PRÓXIMOS PASSOS VÃO NOS PRÓXIMOS MINI-BLOCOS 3B/3C/3D =========
    has_color_toners_hint = False  # placeholder, preenchemos no bloco 3B
    pages_total = 0
    pages_bw = 0
    pages_color = 0
    v_total, v_bw, v_color = (0, 0, 0)
    rfc_total, rfc_pb, rfc_color = (0, 0, 0)
    marker_pb, marker_color = (0, 0)
    fonte_usada = "nenhuma"
    allow_largest_heuristic = False
    model_low = ""

    # ========== (continuação) Calcula has_color_toners_hint (sem REPETIR coleta de toners!) ==========
    # Dica real de "tem toner colorido?" (NÃO confunde valor 0 com "existe"):
    has_color_toners_hint = False
    for _pt in (toner_cyan, toner_magenta, toner_yellow):
        if _pt is None:
            continue
        try:
            if float(_pt) > 0:
                has_color_toners_hint = True
                break
        except Exception:
            continue
    logger.debug("%s marca=%s model=%s toner_color_hint=%s (C=%s M=%s Y=%s K=%s)",
                 ip, manufacturer or "?", model or "?",
                 has_color_toners_hint, toner_cyan, toner_magenta, toner_yellow, toner_black)

    # ========= PASSO 3: 🥇 CONTADORES PRIVADOS DA MARCA (Tier A/B) — PRIORIDADE MÁXIMA! =========
    v_total, v_bw, v_color = _collect_pages_vendor_specific(
        ip, community, timeout, manufacturer, model=model,
    )

    # ========= PASSO 4: 🥈 OIDs FIXOS RFC .1.1 / .1.2 / .1.3 (antigo, fallback retrocompatibilidade) =========
    rfc_total = _parse_int(_snmp_get(ip, OID_PAGES_TOTAL, community, timeout)) or 0
    rfc_pb    = _parse_int(_snmp_get(ip, OID_PAGES_BW,    community, timeout)) or 0
    rfc_color = _parse_int(_snmp_get(ip, OID_PAGES_COLOR, community, timeout)) or 0

    # ========= PASSO 4.5: 🏆 MÉTODO RFC 3805 OFICIAL (WALK TABELA por ColorantIndex) =========
    #         Esse é o MÉTODO MAIS CONFIÁVEL! Não usa índices fixos.
    #         Lê TODAS as linhas da prtMarkerTable, identifica cor por prtMarkerColorantIndex:
    #           colorant=1 → Preto, colorant=2..32 → Cores CMY (soma como coloridas)
    #         Funciona em KONICA MINOLTA bizhub C308/C368/C258/C287 etc que não respondem
    #         corretamente aos OIDs RFC com índices fixos .1.2 / .1.3!
    rfc3805_total = 0
    rfc3805_pb    = 0
    rfc3805_color = 0
    rfc3805_ok    = False
    try:
        _rfc3805 = _collect_pages_printer_mib_rfc(ip, community, timeout)
        if _rfc3805 and (_rfc3805[0] > 0 or _rfc3805[1] > 0 or _rfc3805[2] > 0):
            rfc3805_total, rfc3805_pb, rfc3805_color = _rfc3805
            rfc3805_ok = True
    except Exception as exc:
        logger.debug("collect_printer RFC3805 exc %s: %s", ip, exc)

    # ========= PASSO 5: 🟣 Marker Table (preparação — rodaremos no bloco 3C) =========
    marker_pb = 0
    marker_color = 0
    # Variáveis locais extras usadas apenas pela versão antiga ainda rodando os fallback blocks:
    _pre_has_color_toners = has_color_toners_hint
    _t_black_percent = toner_black
    _t_cyan_percent = toner_cyan
    _t_magenta_percent = toner_magenta
    _t_yellow_percent = toner_yellow
    oid_total = rfc_total
    oid_pb = rfc_pb
    oid_color = rfc_color
    _oid_rfc_split_real = (oid_pb > 0) or (oid_color > 0)
    # ========= PASSO 5: 🟣 Marker Table (SÓ RODA SE AINDA NÃO TEMOS SPLIT REAL!) =========
    model_low = (model or "").lower()
    allow_largest_heuristic = (
        manufacturer == "Epson"
        and any(low_mdl in model_low for low_mdl in (
            m.lower() for m in ALLOW_HEURISTIC_LARGEST_BLACK_MODELS
        ))
        and has_color_toners_hint
    )
    # Só roda Marker Table se NENHUM dos métodos acima (vendor / RFC / RFC3805) deu split REAL ainda
    nao_tem_split_real = not (
        (v_bw > 0 or v_color > 0)
        or (rfc_pb > 0 or rfc_color > 0)
        or (rfc3805_ok and (rfc3805_pb > 0 or rfc3805_color > 0))
    )
    if nao_tem_split_real:
        # Dupla proteção: hint SÓ p/ EcoTank. Força disable p/ todo o resto!
        marker_table_hint = has_color_toners_hint if allow_largest_heuristic else False
        force_disable_heur = not allow_largest_heuristic
        marker_pb, marker_color = _collect_pages_from_marker_table(
            ip, community, timeout,
            has_color_toners_hint=marker_table_hint,
            force_largest_heuristic_disabled=force_disable_heur,
        )
        marker_pb    = marker_pb    or 0
        marker_color = marker_color or 0
        if not allow_largest_heuristic and marker_color > 0 and has_color_toners_hint:
            # Reverte por segurança caso alguma condição interna ainda deixou passar heurística
            marker_pb = marker_pb + marker_color
            marker_color = 0

    # ========= PASSO 6: APLICA PRIORIDADE DAS FONTES (nunca inventa!) =========
    # Ordem de PRIORIDADE (1 mais importante → 6 menos):
    #   1) Vendor OID privado específico (Tier A/B Konica/HP/Xerox/Ricoh etc)
    #        |— PASSO 6B: se vendor color=0, mas tem RFC 3805 NOVO color >0 REAL → mescla!
    #   2) RFC 3805 OFICIAL (WALK por ColorantIndex) — método MAIS CONFIÁVEL GENÉRICO
    #   3) OIDs RFC fixos (.1.1 / .1.2 / .1.3) — retrocompatibilidade
    #   4) Marker Table (só Epson EcoTank)
    #   5) RFC total-only (só OID_PAGES_TOTAL)
    pages_total = 0
    pages_bw    = 0
    pages_color = 0
    if v_total > 0 or v_bw > 0 or v_color > 0:
        pages_bw    = v_bw
        pages_color = v_color
        pages_total = v_total
        fonte_usada = f"vendor:{manufacturer or '?'}"
        # ========= PASSO 6B: FALLBACK ANTI-COLOR=0 RUIM (ex: Konica C308 firmware)! =========
        #         Regra: se vendor disse color=0, mas temos color REAL >0 provado por método RFC:
        #         PRIORIDADE -> PRIMEIRO TENTA O MÉTODO NOVO RFC 3805 (ColorantIndex WALK) [MAIS CONFIÁVEL]
        #         SE NÃO TIVER, FALLBACK PARA OS OIDs RFC FIXOS ANTIGOS [retrocompatibilidade]
        if pages_color == 0 and pages_total > 0:
            # 🏆 PRIMEIRO: Usa o método NOVO RFC 3805 (ColorantIndex) — funciona em Konica C308!
            if rfc3805_ok and (rfc3805_pb > 0 or rfc3805_color > 0) and rfc3805_color > 0:
                rfc3805_sum = rfc3805_pb + rfc3805_color
                rfc3805_ok_color = (
                    rfc3805_sum > 0 and rfc3805_color > 0
                    and rfc3805_sum >= pages_bw
                    and rfc3805_sum <= pages_total * 2
                )
                if rfc3805_ok_color:
                    pages_total = max(pages_total, rfc3805_total) if rfc3805_total > 0 else pages_total
                    pages_color = rfc3805_color
                    pages_bw    = max(0, pages_total - pages_color)
                    fonte_usada = f"vendor:{manufacturer or '?'}+rfc3805-color-fallback"
            # 🥈 SEGUNDO: Só se o RFC 3805 NÃO funcionou — usa OIDs RFC fixos antigos [.1.2/.1.3]
            if pages_color == 0 and (rfc_pb > 0 or rfc_color > 0):
                rfc_sum = rfc_pb + rfc_color
                rfc_color_rel_ok = (rfc_sum > 0) and (rfc_color > 0) and (rfc_sum >= pages_bw) and (rfc_sum <= pages_total * 2)
                if rfc_color_rel_ok:
                    pages_total = max(pages_total, rfc_total) if rfc_total > 0 else pages_total
                    pages_color = rfc_color
                    pages_bw    = max(0, pages_total - pages_color)
                    fonte_usada = f"vendor:{manufacturer or '?'}+rfc-color-fallback"
    # ===== NÍVEL 2 de prioridade: MÉTODO RFC 3805 OFICIAL (ColorantIndex) =====
    elif rfc3805_ok and (rfc3805_pb > 0 or rfc3805_color > 0):
        pages_bw    = rfc3805_pb
        pages_color = rfc3805_color
        pages_total = rfc3805_total
        fonte_usada = "rfc3805-official"
    # ===== NÍVEL 3: Método RFC fixos antigos (retrocompatibilidade) =====
    elif rfc_pb > 0 or rfc_color > 0:
        pages_bw    = rfc_pb
        pages_color = rfc_color
        pages_total = rfc_total
        fonte_usada = "rfc-fixed"
    elif marker_pb > 0 or marker_color > 0:
        pages_bw    = marker_pb
        pages_color = marker_color
        pages_total = marker_pb + marker_color
        fonte_usada = "marker-table"
    elif rfc_total > 0:
        pages_bw    = rfc_total
        pages_color = 0
        pages_total = rfc_total
        fonte_usada = "rfc-total-only"
    else:
        pages_total = 0
        pages_bw    = 0
        pages_color = 0
        fonte_usada = "nenhuma"

    # ========= PASSO 7: VALIDAÇÕES DE SEGURANÇA MÁXIMA (anti-cobrança errada) =========
    # 7.1 TIER D (Toshiba, Epson laser, OKI, Pantum) → Color = 0 OBRIGATÓRIO!
    if manufacturer in MANUFACTURERS_TIER_D_ONLY_TOTAL:
        is_ecotank_exception = (
            manufacturer == "Epson" and marker_color > 0 and allow_largest_heuristic
        )
        if not is_ecotank_exception:
            pages_color = 0
    # 7.2 pages_total NUNCA MENOR que split real (pb + color)
    sum_real_split = pages_bw + pages_color
    if sum_real_split > pages_total:
        pages_total = sum_real_split
    if pages_total <= 0 and sum_real_split > 0:
        pages_total = sum_real_split
    # 7.3 Nenhuma fonte deu? joga tudo em PB
    if pages_total > 0 and pages_bw <= 0 and pages_color <= 0:
        pages_bw = pages_total
        pages_color = 0
    # 7.4 NUNCA deixa color > total, NUNCA bw > total
    if pages_total > 0 and pages_color > pages_total:
        pages_color = max(0, pages_total - pages_bw) if pages_bw > 0 else 0
        pages_color = max(0, pages_color)
    if pages_total > 0 and pages_bw > pages_total:
        pages_bw = pages_total

    # Toners (já coletamos NO PASSO 2 usando _collect_toner_by_manufacturer! Reutilizamos!):
    # ========= PASSO 8: CORREÇÃO 2026-09-21: is_color = PROVA REAL (não dica de toner!) =========
    #    Ricoh SP 4510SF e outras PB tem slot CMY "fantasma" em 0% ou vazio que
    #    gerava has_color_toners=True FALSO. Agora só consideramos colorida SE:
    #       1) Tem páginas coloridas REALMENTE impressas (pages_color > 0 E < total)
    #       -- OU --
    #       2) As 3 cores C+M+Y todas tem toners > 0% (nenhuma fantasma em 0%/None)
    #    🔥 FIX 21/09 vespertino KONICA C308: se a FONTE é vendor:* (OID privado Tier A/B
    #       da marca - Xerox, Konica, HP, etc) e pages_color veio >0 REAL DESSE OID, CONSERVA
    #       o pages_color REAL e marca is_color=True MESMO que os TONERS ainda nao tenham
    #       sido detectados (slot vazio, leitura vazia primeira coleta etc). NUNCA ZERAMOS
    #       um contador colorido que veio de OID PRIVADO OFICIAL da marca.
    has_vendor_color_real = bool(
        fonte_usada and fonte_usada.startswith("vendor:")
        and pages_color and 0 < pages_color < pages_total
    )
    has_color_pages_real = bool(pages_color and 0 < pages_color < pages_total)
    has_3_color_toners_all_ok = True
    _count_ok = 0
    for _t in (toner_cyan, toner_magenta, toner_yellow):
        try:
            _v = float(_t) if _t is not None else 0
        except Exception:
            _v = 0
        if _v > 0:
            _count_ok += 1
    has_3_color_toners_all_ok = (_count_ok == 3)

    is_color_printer = has_vendor_color_real or has_color_pages_real or has_3_color_toners_all_ok

    # ⛔ Não é colorida? Zera tudo que é cor (NÃO manda dado mentiroso pro backend)
    #    🔥 FIX KONICA C308: EXCEÇÃO - se pages_color REAL veio de vendor:Konica/vendor:HP/vendor:Xerox
    #    etc (OID privado oficial Tier A/B), NUNCA ZERAMOS pages_color, pois ele é PROVA REAL
    #    de páginas coloridas, mesmo que os toners ainda não tenham sido lidos direito!
    if not is_color_printer:
        if not has_vendor_color_real:
            toner_cyan = None
            toner_magenta = None
            toner_yellow = None
            pages_color = 0
            if pages_total > 0:
                pages_bw = pages_total
            elif pages_bw > 0:
                pages_total = pages_bw
    else:
        # É colorida mas ainda NÃO TEM SPLIT REAL? → NÃO INVENTA! Tudo PB, color = 0.
        #    🔥 FIX 21/09: EXCEÇÃO - se já tem pages_color de vendor:* OID privado real,
        #    NÃO ZERA (mantém como provou)!
        if (pages_color <= 0 or not has_vendor_color_real) and pages_total > 0:
            pages_bw = pages_total
            pages_color = 0
        if pages_bw + pages_color > pages_total:
            pages_total = pages_bw + pages_color

    # ========= PASSO 9: Monta PrinterData, alertas, log final =========
    data = PrinterData(
        ip_address=ip,
        model=model or None,
        manufacturer=manufacturer,
        serial_number=serial or None,
        status="online",
        pages_total=max(0, pages_total),
        pages_bw=max(0, pages_bw),
        pages_color=max(0, pages_color),
        toner_black=toner_black,
        toner_cyan=toner_cyan,
        toner_magenta=toner_magenta,
        toner_yellow=toner_yellow,
    )

    # Alertas de toner (SÓ p/ toners que REALMENTE existem)
    alerts: list[str] = []
    toners_to_check: list[tuple[str, Optional[float]]] = [("preto", toner_black)]
    if is_color_printer:
        toners_to_check.extend([
            ("ciano", toner_cyan),
            ("magenta", toner_magenta),
            ("amarelo", toner_yellow),
        ])
    for c, pct in toners_to_check:
        if pct is None:
            continue
        if pct <= 5:
            alerts.append(f"Toner {c} critico: {pct}%")
        elif pct <= 15:
            alerts.append(f"Toner {c} baixo: {pct}%")
    data.alerts = alerts
    data.toner_cyan = toner_cyan
    data.toner_magenta = toner_magenta
    data.toner_yellow = toner_yellow
    data.pages_total = max(0, pages_total)
    data.pages_bw    = max(0, pages_bw)
    data.pages_color = max(0, pages_color)

    logger.info(
        "%s %s %s | total=%d bw=%d color=%d | fonte=%s | is_color=%s",
        ip,
        f"[{manufacturer}]" if manufacturer else "[marca=?]",
        model or "model=?",
        data.pages_total, data.pages_bw, data.pages_color,
        fonte_usada,
        is_color_printer,
    )
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

    # ============= 🏆 BANNER: Coleta Segura de OIDs por Marca (2026-09-21) =============
    logger.info("="*78)
    logger.info(" PRINT COLLECT AGENT — v6.9.12-KM-PRINTWAYY-OIDS-20260921-7  ")
    logger.info(" OIDs privados Tier A/B ATIVOS: HP / Konica Minolta / Ricoh / Xerox / ")
    logger.info("     Lexmark / Canon / Sharp — contadores PB e Color REAIS (NÃO INVENTADOS!)")
    logger.info(" Konica Minolta: ÁRVORE NOVA PRINTWAYY 1.1.2.1.5.7.20.1.1.9 (PRIORIDADE!)")
    logger.info(" Heurística 'maior=preto' LIBERADA SÓ p/ EPSON EcoTank L3xxx whitelist.")
    logger.info(" Demais impressoras: Color=0 (segurança) se não houver OID específico.")
    logger.info("="*78)
    # ==============================================================================

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
