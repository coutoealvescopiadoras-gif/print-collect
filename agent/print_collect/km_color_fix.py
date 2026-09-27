"""Corrige o contador colorido da Konica Minolta sem alterar snmp.py.

O ciclo de 30 minutos continua no collector: este modulo so completa
pages_color / pages_bw / pages_total depois que a coleta original termina.
Na bizhub C308 os contadores oficiais ficam na arvore PrintWayy:

    1.3.6.1.4.1.18334.1.1.2.1.5.7.20.1.1.9
        .1 = total, .2 = preto, .3 = colorido
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("print-collect-agent")

_KM_BASE = "1.3.6.1.4.1.18334.1.1.2.1.5.7.20.1.1.9"
# Sufixo vazio e .0/.1 sao os que a C308 responde. Os demais cobrem firmware
# que publica a folha em .1.0 ou .1.1.0.
_KM_TAILS = ("", ".0", ".1", ".1.0", ".1.1", ".1.1.0", ".4")

_LEGACY_GROUPS = (
    (
        "km-copy-print",
        "1.3.6.1.4.1.18334.1.1.1.5.7.2.1.1.0",
        ("1.3.6.1.4.1.18334.1.1.1.5.1.1.0", "1.3.6.1.4.1.18334.1.1.1.5.1.2.0"),
        ("1.3.6.1.4.1.18334.1.1.1.5.2.1.0", "1.3.6.1.4.1.18334.1.1.1.5.2.2.0"),
    ),
    (
        "km-counter-table",
        "1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.1.1",
        ("1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.1.2",),
        ("1.3.6.1.4.1.18334.1.1.1.5.7.2.2.1.5.1.3",),
    ),
)

_CACHE: dict[tuple[str, str], tuple[float, tuple[int, int, int, str] | None]] = {}
_CACHE_TTL_SEC = 120.0
_APPLIED = False


def _looks_konica(manufacturer: str | None, model: str | None) -> bool:
    text = f"{manufacturer or ''} {model or ''}".lower()
    return any(token in text for token in ("konica", "minolta", "bizhub", "c308"))


def _get(snmp_mod, ip: str, oid: str, community: str, timeout: int) -> int:
    return snmp_mod._parse_int(snmp_mod._snmp_get(ip, oid, community, timeout)) or 0


def _sum_oids(snmp_mod, ip: str, oids: tuple[str, ...], community: str, timeout: int) -> int:
    total = 0
    for oid in oids:
        total += _get(snmp_mod, ip, oid, community, timeout)
    return total


def choose_counters(groups: list[tuple[str, int, int, int]]) -> tuple[int, int, int, str] | None:
    """Escolhe o trio total/preto/cor cujo preto+cor fecha o total.

    groups: (rotulo, total, preto, cor)
    """
    best: tuple[int, int, int, str] | None = None
    best_gap = 99.0
    for label, total, bw, color in groups:
        if total <= 0 or bw <= 0 or color <= 0:
            continue
        summed = bw + color
        gap = abs(summed - total) / total
        if gap > 0.15:
            continue
        use_total = summed if gap <= 0.02 else max(total, summed)
        if best is None or gap < best_gap:
            best = (use_total, bw, color, label)
            best_gap = gap
    if best is not None:
        return best
    best_dif: tuple[int, int, int, str] | None = None
    for label, total, bw, color in groups:
        if color > 0 or total <= bw or bw <= 0:
            continue
        derived = total - bw
        if derived <= 0:
            continue
        if best_dif is None or total > best_dif[0]:
            best_dif = (total, bw, derived, f"{label}-dif")
    return best_dif


def _read_km_color(snmp_mod, ip: str, community: str, timeout: int) -> tuple[int, int, int, str] | None:
    key = (ip, community)
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached is not None and (now - cached[0]) < _CACHE_TTL_SEC:
        return cached[1]

    groups: list[tuple[str, int, int, int]] = []
    for tail in _KM_TAILS:
        label = f"printwayy{tail or '.folha'}"
        groups.append(
            (
                label,
                _get(snmp_mod, ip, f"{_KM_BASE}.1{tail}", community, timeout),
                _get(snmp_mod, ip, f"{_KM_BASE}.2{tail}", community, timeout),
                _get(snmp_mod, ip, f"{_KM_BASE}.3{tail}", community, timeout),
            )
        )
        chosen = choose_counters(groups)
        if chosen is not None and not str(chosen[3]).endswith("-dif"):
            summed = chosen[1] + chosen[2]
            if chosen[0] > 0 and abs(summed - chosen[0]) / chosen[0] <= 0.02:
                _CACHE[key] = (now, chosen)
                return chosen

    for label, total_oid, bw_oids, color_oids in _LEGACY_GROUPS:
        groups.append(
            (
                label,
                _get(snmp_mod, ip, total_oid, community, timeout),
                _sum_oids(snmp_mod, ip, bw_oids, community, timeout),
                _sum_oids(snmp_mod, ip, color_oids, community, timeout),
            )
        )

    chosen = choose_counters(groups)
    _CACHE[key] = (now, chosen)
    return chosen


def apply() -> None:
    """Troca a leitura Konica em memoria. snmp.py no disco nao e alterado."""
    global _APPLIED
    if _APPLIED:
        return

    import print_collect.snmp as snmp

    original_vendor = snmp._collect_pages_vendor_specific
    original_collect = snmp.collect_printer

    def vendor(ip, community, timeout, manufacturer, model=None):
        if manufacturer == "Konica Minolta" or _looks_konica(manufacturer, model):
            found = _read_km_color(snmp, ip, community, timeout)
            if found is not None:
                total, bw, color, src = found
                logger.info(
                    "Konica colorido %s via %s | total=%s bw=%s color=%s",
                    ip, src, total, bw, color,
                )
                return (total, bw, color)
            logger.info("Konica %s sem trio PB/cor nos OIDs diretos; segue fallback.", ip)
            return (0, 0, 0)
        return original_vendor(ip, community, timeout, manufacturer, model=model)

    def collect_printer(ip, community="public", timeout=5):
        data = original_collect(ip, community, timeout)
        if data is None or data.pages_color > 0:
            return data
        if not _looks_konica(data.manufacturer, data.model):
            return data
        found = _read_km_color(snmp, ip, community, timeout)
        if found is None:
            return data
        total, bw, color, src = found
        data.pages_bw = bw
        data.pages_color = color
        data.pages_total = max(data.pages_total, total, bw + color)
        if not data.manufacturer:
            data.manufacturer = "Konica Minolta"
        logger.info(
            "Konica colorido aplicado depois da coleta %s via %s | total=%s bw=%s color=%s",
            ip, src, data.pages_total, data.pages_bw, data.pages_color,
        )
        return data

    snmp._collect_pages_vendor_specific = vendor
    snmp.collect_printer = collect_printer
    _APPLIED = True
    logger.info(
        "Correcao de contador colorido Konica ativa (C308). "
        "O intervalo de coleta nao muda: continua o do config, 30 minutos."
    )
