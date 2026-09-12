"""Coleta de impressoras conectadas LOCALMENTE no Windows via USB, WiFi Direct,
LPT, ou qualquer porta que apareça no spooler do Windows (exclui impressoras
virtuais como PDF/XPS/OneNote/Fax).

MODULO ADITIVO 100% - NAO ALTERA NADA DO SNMP, NAO QUEBRA NADA!
Se der qualquer erro, retorna lista vazia e a coleta SNMP continua normal.

Retorna a MESMA classe PrinterData usada pelo snmp.py para que o sender.py
consiga enviar tudo pro backend sem precisar de NENHUMA alteracao.
"""
from __future__ import annotations

import hashlib
import json
import logging
import platform
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Any

# ---------------------------------------------------------------------------
# Import da classe PrinterData (origem no snmp.py, mesmo formato!)
# ---------------------------------------------------------------------------
from print_collect.snmp import PrinterData

logger = logging.getLogger("print-collect-agent")

# ================================================================
# FIX v6.9.4 (CANON G3111 WIFI: porta _1 nao limpava e nao fazia snmp!)
# ================================================================
# 1) Extrair IP/host LIMPO de qualquer porta TCP/IP instalada no Windows
#    Formas conhecidas de porta de REDE:
#      - 192.168.15.50          -> 192.168.15.50
#      - 192.168.15.50_1        -> 192.168.15.50  (Canon G WiFi suf. N!)
#      - IP_192.168.15.50       -> 192.168.15.50
#      - IP_192.168.15.50_3     -> 192.168.15.50
#      - 10.0.0.2               -> 10.0.0.2
#      - 172.16.0.5_1           -> 172.16.0.5
#      - ipp://192.168.15.50:631/ipp/print -> 192.168.15.50
#      - http://print.local:631 -> print.local
# ================================================================
_IPV4_N_SUFFIX = re.compile(r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?:_\d+)?$")

def _extract_host_from_port(port: str) -> Optional[str]:
    """Tenta extrair hostname/ipv4 LIMPO de nome de porta de impressora Windows.
    Retorna None se for porta USB/LPT/Fisico compartilhado (nao tem host).
    """
    if not port:
        return None
    p = port.strip()
    if not p:
        return None

    # 1) Descarta imediatamente USB/LPT/DOT4/COM (fisico!)
    up = p.upper()
    if up.startswith(("USB", "DOT4", "LPT", "COM")):
        return None
    # Descarta compartilhada Windows
    if p.startswith("\\\\"):
        return None

    # 2) IPP/HTTP -> extrai host da URL
    low = p.lower()
    if low.startswith(("ipp://", "ipps://", "http://", "https://", "wsd://")):
        try:
            from urllib.parse import urlparse
            parsed = urlparse(p)
            return parsed.hostname or None
        except Exception:
            return None

    # 3) Prefixo IP_: remove
    if up.startswith("IP_"):
        p = p[3:]

    # 4) IPv4 puro ou com _N no final? (Canon WiFi _1/_2!)
    m = _IPV4_N_SUFFIX.match(p.strip())
    if m:
        return m.group(1)

    # 5) Nao parece rede
    return None


def _snmp_quick_read(host: str, community: str = "public", timeout_sec: float = 4.0) -> Optional[PrinterData]:
    """Tenta coleta SNMP em impressora de REDE (v6.9.5 MELHORADO!).
    MELHORIAS vs 1.5s antigo:
      * Timeout 4s (nao 1.5s!) — rede WiFi lenta de cliente tem tempo de responder.
      * Primeiro tenta community 'public' (padrão), se falhar tenta 'private' (fallback!).
      * Chama collect_printer() 2x se necessário para aumentar chance.
    **NAO TRAVA o loop principal. Se falhar → fallback spooler normal!
    Retorna PrinterData (com pages_color REAL!) se sucesso, None se falhar."""
    try:
        from print_collect.snmp import collect_printer
    except Exception as exc:
        logger.debug("  USB->SNMP quick read import falhou host=%s: %s", host, exc)
        return None

    timeout_ms = int(timeout_sec * 1000)
    communities = [community]
    if community.lower() != "private":
        communities.append("private")

    last_exc = None
    for c in communities:
        for attempt in (1, 2):
            try:
                rd = collect_printer(host, community=c, timeout=timeout_ms)
                if rd is not None and (rd.pages_total > 0 or rd.pages_color > 0 or rd.model):
                    if c != community:
                        logger.info("  USB->SNMP quick_read OK na community alternativa '%s' (host=%s, tentativa %d)",
                                    c, host, attempt)
                    return rd
            except Exception as exc:
                last_exc = exc
                import time as _t
                _t.sleep(0.25)
    logger.debug("  USB->SNMP quick read falhou host=%s communities=%s attempts=2. Ultimo erro: %s (type=%s)",
                 host, communities, last_exc, type(last_exc).__name__ if last_exc else "None")
    return None

# Impressoras VIRTUAIS do Windows - NAO COLETAMOS nada delas
VIRTUAL_KEYWORDS = (
    "microsoft print to pdf",
    "microsoft xps document writer",
    "onenote",
    "fax",
    "send to bluetooth",
    "microsoft shared fax",
    "remote desktop",
    "rdp easy print",
    "webex document loader",
    "snagit",
    "cute pdf",
    "dopdf",
    "bullzip",
    "pdf24",
    "primo pdf",
    "foxit reader pdf printer",
    "nitro pdf creator",
    "google cloud print",
)


def _is_virtual_printer(name: str, driver: str, port: str) -> bool:
    """Retorna True SE E SOMENTE SE for impressora VIRTUAL (PDF, XPS, Fax, etc).
    IMPRESSORAS FISICAS (USB, LPT, DOT4, IPP, WSD, TCPIP ROH) SOB NENHUMA HIPOTESE PODEM SER PULADAS!

    JULIO - BUG 21/08/2026 - AQUI ERA A CAUSA: as portas USB REAIS sao "USB001", "DOT4_001",
    "USBPRINT", etc. Como tem numeral no final, a substring 'usb' as vezes nao pegava, e o
    segundo bloco pulava a impressora. Regra reescrita 100% segura:
        PRIMEIRO checamos PALAVRAS-CHAVE VIRTUAIS CONHECIDAS.
        DEPOIS, usamos LISTA POSITIVA de PORTAS FISICAS CONFIRMADAS.
        QUALQUER coisa na lista positiva NAO EH VIRTUAL, independente do resto.
    """
    if not port:
        port = ""
    if not name:
        name = ""
    if not driver:
        driver = ""

    port_up = port.strip().upper()
    name_lc = name.lower()
    driver_lc = driver.lower()
    haystack = f"{name_lc} {driver_lc}"

    # ================================================================
    # LISTA POSITIVA DE PORTAS FISICAS (qualquer coisa abaixo NAO EH VIRTUAL!)
    #  ================================================================
    PHYSICAL_PORT_PREFIXES = (
        "USB",          # USB001, USB002, USBPRINT, USB003 etc (mais comum!)
        "DOT4",         # DOT4_001, DOT4USB etc (impressoras HP multifunc)
        "LPT1",         # LPT1, LPT2 paralela
        "LPT2",
        "LPT3",
        "COM1",         # Serial antiga
        "COM2",
        "COM3",
        "COM4",
        "IP_",          # IP_192.168.0.100 (porta TCP/IP)
        "192.168.",     # TCP/IP direto
        "10.",
        "172.",
        "WSD",          # WSD-xxxxxxxxxxxx (WS-Discovery rede local)
        "IPP",          # IPP:// (impressao via internet printing protocol)
        "HTTP://",      # IPP/IP
        "HTTPS://",
        "LOCALPORT",    # LocalPort fisico
        "FILE:",        # FILE: pode ser usado para gravar PS, porem NUNCA junto com USB/DOT4
    )
    for pref in PHYSICAL_PORT_PREFIXES:
        if port_up.startswith(pref):
            # Porta fisica confirmada - NAO PODE SER VIRTUAL!
            return False

    # ================================================================
    # SEGUNDA CHANCE: a porta nao bateu na lista positiva?
    # Checa se a haystack (nome+driver) contem palavra de impressora FISICA
    #  ================================================================
    PHYSICAL_MANUFACTURERS = (
        "epson", "hp ", "hewlett", "laserjet", "deskjet",
        "canon", "brother", "ricoh", "xerox", "kyocera", "samsung",
        "lexmark", "oki", "sharp", "konica", "minolta", "toshiba",
        "savin", "develop", "utax", "triump", "pantum", "xerox",
        "lexmark", "oki", "brother",
    )
    for manu in PHYSICAL_MANUFACTURERS:
        if manu in haystack:
            return False

    # ================================================================
    # LISTA NEGATIVA DE VIRTUAIS CONHECIDOS (SO PASSA AQUI SE NENHUMA
    # regra positiva acima bateu)
    #  ================================================================
    VIRTUAL_KEYWORDS = (
        "microsoft print to pdf",
        "microsoft xps document writer",
        "onenote",
        "microsoft shared fax",
        "remote desktop easy print",
        "rdp easy print",
        "webex document loader",
        "snagit",
        "cute pdf", "cutepdf",
        "dopdf",
        "bullzip",
        "pdf24",
        "primo pdf",
        "foxit reader pdf printer",
        "nitro pdf creator",
        "google cloud print",
        "fax",
        "send to bluetooth",
    )
    for k in VIRTUAL_KEYWORDS:
        if k in haystack:
            return True

    # PORTS virtuais conhecidos (se nao bateu lista positiva):
    VIRTUAL_PORT_PREFIXES = ("PORTPROMPT", "NUL:")
    for pref in VIRTUAL_PORT_PREFIXES:
        if port_up.startswith(pref):
            return True

    # Checagem final: se porta eh "FILE:" e nao tem nada de USB/FABRICANTE:
    if port_up.startswith("FILE:") and not any(x in haystack for x in PHYSICAL_MANUFACTURERS):
        return True

    # Nenhuma regra bateu: considera IMPRESSORA FISICA SEGURA (nao pula!)
    return False


def _slugify(text: str, max_len: int = 48) -> str:
    """Limpa texto para gerar 'ip virtual' tipo USB:HP_LaserJet_1020_abcdef12"""
    s = re.sub(r"[^A-Za-z0-9]+", "_", (text or "").strip()).strip("_")
    if len(s) > max_len:
        s = s[:max_len]
    return s or "local_printer"


def _extract_serial_from_port_or_name(port: str, name: str, driver: str) -> Optional[str]:
    """Tentativa leve de pegar serial quando o driver expõe no nome da porta/device."""
    for t in (port, name, driver):
        if not t:
            continue
        m = re.search(r"(?:SN|Serial|Série|S/N|_)\s*[:=\-#]?\s*([A-Za-z0-9]{6,20})", t, re.I)
        if m:
            cand = m.group(1)
            if cand and re.fullmatch(r"[A-Za-z0-9]{6,20}", cand):
                return cand
    return None


_COUNTER_KEY_HINTS = (
    "totalpagesprinted", "totalpages", "pagesprinted", "pagesprintedtotal",
    "pagetotal", "totalcount", "pagecount", "lifetimepages", "lifetimecount",
    "dwxtotalpages", "dwxpagecount", "dwx_total_pages", "totalpagecount",
    "printedpages", "printerpages", "printercounter",
)
_SERIAL_KEY_HINTS = (
    "serialnumber", "serialnbr", "serialno", "serial", "sn",
)


def _extract_page_counter_from_registry(reg_dict: dict[str, Any]) -> Optional[int]:
    """Tenta encontrar contador CUMULATIVO de páginas no registro de impressora.
    Muitos drivers (Epson/HP/Canon) salvam o valor acumulado da vida util aqui.
    Retorna None se nao encontrar nada ou valor for absurdo (<=0 ou <= spooler desde boot).
    """
    if not reg_dict:
        return None
    best: int | None = None
    for raw_key, raw_val in reg_dict.items():
        if raw_key is None or raw_val is None:
            continue
        key = str(raw_key).lower().replace("_", "").replace(" ", "")
        if not any(h in key for h in _COUNTER_KEY_HINTS):
            continue
        try:
            val_int = int(raw_val)
        except Exception:
            continue
        if val_int <= 0:
            continue
        # Filtro de plausibilidade: impressora laser / jato tinta moderna tem
        # tipicamente 0 a ~5 milhoes de paginas em vida util. Nao aceita bilhao+.
        if val_int > 50_000_000:
            continue
        if best is None or val_int > best:
            best = val_int
    return best


def _extract_serial_from_registry(reg_dict: dict[str, Any]) -> Optional[str]:
    """Tenta extrair serial number de chaves do registro (PrinterDriverData etc)."""
    if not reg_dict:
        return None
    for raw_key, raw_val in reg_dict.items():
        if raw_key is None or raw_val is None:
            continue
        key = str(raw_key).lower().replace("_", "").replace(" ", "")
        if not any(h in key for h in _SERIAL_KEY_HINTS):
            continue
        s = str(raw_val).strip()
        if len(s) >= 6 and re.fullmatch(r"[A-Za-z0-9\-]+", s):
            return s
    return None


def _extract_all_plausible_page_counts(reg_dict: dict[str, Any]) -> list[int]:
    """Busca TUDO no registro que PARECE contador de páginas (valor numérico plausível, >=100 e <=5mi).
    Nao se importa com o NOME da chave. Cobre drivers Epson/HP que usam nomes de chave exóticos tipo 'PCT','PC','LPC','TOT' etc.
    Retorna lista ordenada decrescente de valores candidatos (maior primeiro = vida util mais provavel).
    """
    if not reg_dict:
        return []
    found: set[int] = set()
    for raw_key, raw_val in reg_dict.items():
        if raw_key is None or raw_val is None:
            continue
        # Se valor ja for numero (DWORD, QWORD do registro)
        try:
            val_int = int(raw_val)
        except Exception:
            val_int = -1
        if val_int <= 0:
            # Tenta parsear se for string numerica
            s = str(raw_val).strip()
            if not s or len(s) > 12:
                continue
            m = re.fullmatch(r"[0-9]+", s)
            if not m:
                continue
            try:
                val_int = int(s)
            except Exception:
                continue
        if 100 <= val_int <= 5_000_000:
            # Evita valores que sao timestamps (1.7bi+) ou coisas do tipo
            found.add(val_int)
    # Ordena decrescente: valor MAIOR = mais provavel de ser TOTAL vida util
    return sorted(found, reverse=True)


def _run_ps(cmd: str, timeout_sec: int = 90) -> str:
    """Executa comando PowerShell retornando stdout como UTF-8 seguro (v6.9.5).
    MELHORAS:
      * Timeout reduzido 90s (nao 120s!)
      * Loga stderr SEMPRE em WARNING (nao so DEBUG!) para diagnosticar
        por que a coleta USB esta retornando vazio.
      * Retry 2x se primeira chamada der vazio (PowerShell as vezes falha silenciosamente).
      * Força [System.Text.Encoding]::UTF8 em TUDO (Input + Output) + chcp 65001.
      * Usa -MTA para evitar STA deadlock.
    """
    last_err = ""
    for attempt in (1, 2):
        try:
            wrapped = f"""
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$ErrorActionPreference    = 'Continue'
chcp 65001 > $null
{cmd}
"""
            cmd_bytes = wrapped.encode("utf-16-le")
            import base64 as _b64
            encoded_cmd = _b64.b64encode(cmd_bytes).decode("ascii")
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-MTA",
                 "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_cmd],
                capture_output=True,
                timeout=timeout_sec,
            )
            out_bytes = proc.stdout or b""
            err_bytes = proc.stderr or b""
            try:
                text = out_bytes.decode("utf-8", errors="replace")
            except Exception:
                text = out_bytes.decode("latin-1", errors="replace")
            if not text.strip() and out_bytes:
                try:
                    text = out_bytes.decode("cp850", errors="replace")
                except Exception:
                    pass
            # v6.9.5: LOGA stderr SEMPRE (mesmo se stdout vazio!) para diagnostico
            if err_bytes:
                try:
                    err_txt = err_bytes.decode("utf-8", errors="replace").strip()
                except Exception:
                    err_txt = err_bytes.decode("latin-1", errors="replace").strip()
                if err_txt:
                    last_err = err_txt
                    if not text.strip():
                        logger.warning("USB/powershell attempt=%d STDERR (stdout vazio!): %.1200s",
                                       attempt, err_txt[:1200])
                    else:
                        logger.debug("USB/powershell attempt=%d stderr: %.800s", attempt, err_txt[:800])
            if text.strip():
                return text
            # Stdout vazio -> tenta novamente (retry)
            logger.warning("USB/powershell attempt=%d retornou ZERO bytes de stdout. Vamos tentar novamente (retry=%d)...",
                           attempt, 2 if attempt == 1 else 0)
            if attempt == 1:
                import time as _time
                _time.sleep(1.2)
        except subprocess.TimeoutExpired as exc:
            logger.warning("USB/PowerShell attempt=%d timeout %ds: %s", attempt, timeout_sec, exc)
            last_err = f"TimeoutExpired {timeout_sec}s"
            if attempt == 1:
                import time as _time
                _time.sleep(0.8)
        except Exception as exc:
            logger.warning("USB/powershell attempt=%d erro geral: %s (type=%s)", attempt, exc, type(exc).__name__)
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt == 1:
                import time as _time
                _time.sleep(0.8)

    # Se chegamos aqui, as 2 tentativas falharam -> tenta FALLBACK WMIC (ultima chance!)
    logger.warning("USB/powershell 2 tentativas falharam (ultimo erro: %.200s). TENTANDO FALLBACK WMIC.EXE (Get-WMIObject legacy)...",
                   last_err[:200])
    try:
        return _collect_windows_wmic_fallback()
    except Exception as exc:
        logger.warning("USB/powershell fallback WMIC tambem falhou: %s (type=%s). COLETA USB CANCELADA NESTE CICLO.",
                       exc, type(exc).__name__)
        return ""


def _wmic_decode(raw_bytes: bytes) -> str:
    """WMIC.exe usa OEM/CP850 por padrão em pt-BR (não UTF-8!). Tenta decodificar em ordem segura."""
    if not raw_bytes:
        return ""
    for enc in ("cp850", "latin-1", "utf-8", "cp1252"):
        try:
            txt = raw_bytes.decode(enc, errors="replace").strip()
            if txt and ("=" in txt or "Namespace" in txt):
                return txt
        except Exception:
            pass
    try:
        return raw_bytes.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _collect_windows_wmic_fallback() -> str:
    """FALLBACK ULTIMA CHANCE se PowerShell Get-CimInstance falhar.
    Usa WMIC.EXE (legado, existe em TODO Windows desde XP) para pegar
    Win32_Printer, Win32_PerfFormattedData_Spooler_PrintQueue, Drivers, Jobs, PORTAS!
    Gera as mesmas linhas JSON_START_* que o PowerShell normal.
    """
    out_lines: list[str] = []
    try:
        import json as _json
        import re as _re

        # --- 1) Win32_Printer via WMIC ---
        try:
            proc = subprocess.run(
                ["wmic.exe", "printer", "get", "/all", "/format:list"],
                capture_output=True, timeout=30,
            )
            txt = _wmic_decode(proc.stdout or b"")
            arr = _wmic_list_to_dicts(txt)
            filtered = []
            for p in arr:
                if not p:
                    continue
                pname = (p.get("Name") or p.get("Caption") or "").strip()
                if not pname:
                    continue
                filtered.append({
                    "Name": pname,
                    "DriverName": p.get("DriverName"),
                    "Manufacturer": p.get("Manufacturer"),
                    "PortName": p.get("PortName"),
                    "DeviceID": p.get("DeviceID"),
                    "Status": p.get("Status"),
                    "ExtendedPrinterStatus": p.get("ExtendedPrinterStatus"),
                    "Default": p.get("Default"),
                    "WorkOffline": p.get("WorkOffline"),
                    "PrinterState": p.get("PrinterState"),
                    "PrinterStatus": p.get("PrinterStatus"),
                    "Shared": p.get("Shared"),
                    "Local": p.get("Local"),
                })
            out_lines.append("JSON_START_PRINTERS " + _json.dumps(filtered, separators=(",", ":"), ensure_ascii=False))
        except Exception as exc:
            logger.warning("FALLBACK WMIC printer falhou: %s", exc)
            out_lines.append("JSON_START_PRINTERS []")

        # --- 2) Print Queue via WMIC ---
        try:
            proc = subprocess.run(
                ["wmic.exe", "path", "Win32_PerfFormattedData_Spooler_PrintQueue", "get", "/all", "/format:list"],
                capture_output=True, timeout=30,
            )
            txt = _wmic_decode(proc.stdout or b"")
            arr = _wmic_list_to_dicts(txt)
            filtered = []
            for q in arr:
                if not q:
                    continue
                try:
                    tp = int(q.get("TotalPagesPrinted") or 0)
                except Exception:
                    tp = 0
                try:
                    tj = int(q.get("TotalJobsPrinted") or 0)
                except Exception:
                    tj = 0
                try:
                    js = int(q.get("JobsSpooling") or 0)
                except Exception:
                    js = 0
                filtered.append({
                    "Name": q.get("Name"),
                    "TotalPagesPrinted": tp,
                    "TotalJobsPrinted": tj,
                    "JobsSpooling": js,
                })
            out_lines.append("JSON_START_QUEUES " + _json.dumps(filtered, separators=(",", ":"), ensure_ascii=False))
        except Exception as exc:
            logger.warning("FALLBACK WMIC printqueue falhou: %s", exc)
            out_lines.append("JSON_START_QUEUES []")

        # --- 3) Drivers, PnP, Registry, Jobs fallback [] (melhor que nada!) ---
        out_lines.append("JSON_START_DRIVERS []")
        out_lines.append("JSON_START_PNP []")
        out_lines.append("JSON_START_REGISTRY []")
        out_lines.append("JSON_START_JOBS []")

        # --- 4) PORTAS REAIS via WMIC (TCPIP Printer Port!) + USB Monitor registry (agora USB: nao 0 portas!) ---
        ports_arr: list[dict[str, Any]] = []
        try:
            proc = subprocess.run(
                ["wmic.exe", "path", "Win32_TCPIPPrinterPort", "get", "/all", "/format:list"],
                capture_output=True, timeout=20,
            )
            txt = _wmic_decode(proc.stdout or b"")
            arr = _wmic_list_to_dicts(txt)
            for p in arr:
                nm = (p.get("Name") or "").strip()
                if not nm:
                    continue
                ports_arr.append({"Name": nm, "Description": "TCPIP", "Type": "TCPIP",
                                  "PortMonitor": p.get("Protocol") or "Standard TCP/IP Port"})
                host_ip = (p.get("HostAddress") or "").strip()
                if host_ip:
                    # Tambem adiciona porta sem _N variantes que podem existir so no driver
                    ports_arr.append({"Name": host_ip, "Description": "TCPIP-IP", "Type": "TCPIP",
                                      "PortMonitor": "Standard TCP/IP Port"})
                    # E tambem as versoes com _N no final (192.168.15.50_1 etc)
                    for n_suffix in range(1, 10):
                        ports_arr.append({"Name": f"{host_ip}_{n_suffix}", "Description": "TCPIP-SUFFIX",
                                          "Type": "TCPIP", "PortMonitor": "Standard TCP/IP Port"})
                        ports_arr.append({"Name": f"IP_{host_ip}_{n_suffix}", "Description": "TCPIP-IPSUFFIX",
                                          "Type": "TCPIP", "PortMonitor": "Standard TCP/IP Port"})
        except Exception as exc:
            logger.debug("WMIC TCPIPPrinterPort falhou: %s", exc)
        try:
            proc = subprocess.run(
                ["wmic.exe", "printerport", "get", "/all", "/format:list"],
                capture_output=True, timeout=20,
            )
            txt = _wmic_decode(proc.stdout or b"")
            arr = _wmic_list_to_dicts(txt)
            for p in arr:
                nm = (p.get("Name") or "").strip()
                if not nm:
                    continue
                ports_arr.append({"Name": nm,
                                  "Description": p.get("Description") or "PrinterPort",
                                  "Type": "AUTO",
                                  "PortMonitor": p.get("PortMonitor") or ""})
        except Exception as exc:
            logger.debug("WMIC printerport falhou: %s", exc)
        try:
            # Fallback USB/LPT/DOT4 hardcode (portas padrão sempre existem em maquinas com impressora fisica!)
            for p in ["USB001", "USB002", "USB003", "USB004", "USB005",
                      "DOT4_001", "DOT4_002", "DOT4USB001", "DOT4USB002",
                      "LPT1:", "LPT2:", "LPT3:", "COM1:", "COM2:"]:
                ports_arr.append({"Name": p, "Description": "FALLBACK_FISICO", "Type": "FISICO",
                                  "PortMonitor": "USB Monitor/DOT4"})
        except Exception:
            pass
        # Deduplica
        seen_port_names: set[str] = set()
        final_ports: list[dict[str, Any]] = []
        for p in ports_arr:
            nm = str(p.get("Name") or "").strip()
            if not nm or nm in seen_port_names:
                continue
            seen_port_names.add(nm)
            final_ports.append(p)
        out_lines.append("JSON_START_PORTS " + _json.dumps(final_ports, separators=(",", ":"), ensure_ascii=False))

        return "\n".join(out_lines) + "\n"
    except Exception as exc:
        logger.warning("_collect_windows_wmic_fallback erro geral: %s", exc)
        return ""


def _wmic_list_to_dicts(txt: str) -> list[dict[str, Any]]:
    """Converte saida wmic.exe ... /format:list (blocos chave=valor separados por linha em branco)
    em uma lista de dicionarios Python."""
    results: list[dict[str, Any]] = []
    cur: dict[str, Any] = {}
    if not txt:
        return results
    for raw_line in txt.splitlines():
        line = raw_line.strip()
        if not line:
            if cur:
                results.append(cur)
                cur = {}
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        cur[k.strip()] = v.strip()
    if cur:
        results.append(cur)
    return results


def _collect_windows() -> list[PrinterData]:
    """Coleta impressoras locais Windows.
    Formato do stdout do PowerShell (garantido, NÃO HÁ envelope JSON - evita dupla serializacao bug):
        LINHA 1 = JSON_START_PRINTERS <JSON de Win32_Printer>
        LINHA 2 = JSON_START_QUEUES   <JSON de Spooler PrintQueue>
        LINHA 3 = JSON_START_DRIVERS  <JSON de Win32_PrinterDriver (se houver)>
        LINHA 4 = JSON_START_PNP      <JSON de Win32_PnPEntity (dispositivos USB conectados AGORA!)>
    """
    ps_cmd = r"""
$ErrorActionPreference = 'Continue'
# --- Linha 1: impressoras WMI Win32_Printer (todas as propriedades, incluindo WorkOffline!) ---
try {
    $arr = @(Get-CimInstance Win32_Printer -ErrorAction Stop | Select-Object Name,DriverName,Manufacturer,PortName,DeviceID,Status,ExtendedPrinterStatus,Default,WorkOffline,PrinterState,PrinterStatus,Shared,Local)
    if ($arr.Count -eq 0) { Write-Output ('JSON_START_PRINTERS []') }
    else { $json = $arr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_PRINTERS ' + $json) }
} catch {
    Write-Output ('JSON_START_PRINTERS []')
}
# --- Linha 2: filas spooler + contadores (DESDE BOOT, mas melhor que nada) ---
try {
    $arr = @(Get-CimInstance Win32_PerfFormattedData_Spooler_PrintQueue -ErrorAction Stop | Select-Object Name,TotalPagesPrinted,TotalJobsPrinted,JobsSpooling)
    if ($arr.Count -eq 0) { Write-Output ('JSON_START_QUEUES []') }
    else { $json = $arr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_QUEUES ' + $json) }
} catch {
    Write-Output ('JSON_START_QUEUES []')
}
# --- Linha 3: Drivers instalados (para ver se DriverDate/Version existe e se Epson tem DriverInfo cumulativo) ---
try {
    $arr = @(Get-CimInstance Win32_PrinterDriver -ErrorAction Stop | Select-Object Name,Manufacturer,SupportedPlatform,Version,DrivePath,DataFile,ConfigFile)
    if ($arr.Count -eq 0) { Write-Output ('JSON_START_DRIVERS []') }
    else { $json = $arr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_DRIVERS ' + $json) }
} catch {
    Write-Output ('JSON_START_DRIVERS []')
}
# --- Linha 4: Win32_PnPEntity (dispositivos Plug&Play CONECTADOS AGORA!) ---
try {
    $arr = @(Get-CimInstance Win32_PnPEntity -ErrorAction Stop | Where-Object { $_.PNPClass -in ('Printer','USBPrint','USB','Dot4') } | Select-Object Name,PNPClass,Status,DeviceID,Manufacturer,HardwareID)
    if ($arr.Count -eq 0) { Write-Output ('JSON_START_PNP []') }
    else { $json = $arr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_PNP ' + $json) }
} catch {
    Write-Output ('JSON_START_PNP []')
}
# --- Linha 5: Registro do Windows HKLM...Print\Printers (CONTADOR CUMULATIVO da vida util!) ---
# Muitos fabricantes (Epson, HP, Canon) salvam TotalPages CUMULATIVO (nao desde boot!) aqui.
try {
    $regPrintersPath = 'HKLM:\SYSTEM\CurrentControlSet\Control\Print\Printers'
    $allReg = @()
    if (Test-Path $regPrintersPath) {
        $subkeys = @(Get-ChildItem $regPrintersPath -ErrorAction SilentlyContinue)
        foreach ($k in $subkeys) {
            $objProps = @{
                PrinterName = $k.PSChildName
            }
            try {
                $props = Get-ItemProperty $k.PSPath -ErrorAction SilentlyContinue
                if ($props) {
                    $props.PSObject.Properties | ForEach-Object {
                        if ($_.Name -notlike 'PS*') {
                            $objProps[$_.Name] = $_.Value
                        }
                    }
                }
            } catch {}
            try {
                $driverDataPath = Join-Path $k.PSPath 'PrinterDriverData'
                if (Test-Path $driverDataPath) {
                    $dd = Get-ItemProperty $driverDataPath -ErrorAction SilentlyContinue
                    if ($dd) {
                        $dd.PSObject.Properties | ForEach-Object {
                            if ($_.Name -notlike 'PS*') {
                                $objProps['DD_' + $_.Name] = $_.Value
                            }
                        }
                    }
                }
            } catch {}
            $allReg += [PSCustomObject]$objProps
        }
    }
    if ($allReg.Count -eq 0) { Write-Output ('JSON_START_REGISTRY []') }
    else { $json = $allReg | ConvertTo-Json -Depth 5 -Compress ; Write-Output ('JSON_START_REGISTRY ' + $json) }
} catch {
    Write-Output ('JSON_START_REGISTRY []')
}
# --- Linha 6: Win32_PrintJob (JOBS JA PROCESSADOS NO SPOOLER, HISTORICO DE TRABALHOS!) ---
# Estimativa EXCELENTE para vida util cumulativa: soma TotalPages de todos JOBS que jah passaram!
try {
    $arr = @(Get-CimInstance Win32_PrintJob -ErrorAction Stop | Select-Object Name,JobId,TotalPages,Document,Owner)
    if ($arr.Count -eq 0) { Write-Output ('JSON_START_JOBS []') }
    else { $json = $arr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_JOBS ' + $json) }
} catch {
    Write-Output ('JSON_START_JOBS []')
}
# --- Linha 7: PORTAS REAIS EXISTENTES (se a porta nao existe aqui, FANTASMA!) ---
try {
    $arr = @()
    try {
        $arr += @(Get-PrinterPort -ErrorAction Stop | Select-Object Name,Description,Type,PortMonitor)
    } catch {
        # Fallback para Windows 7 que nao tem modulo PrintManagement
        try { Get-CimInstance Win32_TCPIPPrinterPort -ErrorAction Stop | ForEach-Object { $arr += [PSCustomObject]@{ Name=$_.Name; Description='TCPIP'; Type='TCPIP'; PortMonitor=$_.Protocol } } catch {}
    }
    # Adiciona portas USB/LPT/DOT4 que existem em Port Monitors do registro (fallback!)
    try {
        $usbp = 'HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors\USB Monitor\Ports'
        if (Test-Path $usbp) { Get-ChildItem $usbp -ErrorAction SilentlyContinue | ForEach-Object { if (-not ($arr.Name -contains $_.PSChildName)) { $arr += [PSCustomObject]@{ Name=$_.PSChildName; Description='USB Monitor Port'; Type='USB'; PortMonitor='USB Monitor' } } }
    } catch {}
    if ($arr.Count -eq 0) { Write-Output ('JSON_START_PORTS []') }
    else { $json = $arr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_PORTS ' + $json) }
} catch {
    Write-Output ('JSON_START_PORTS []')
}
"""
    raw = _run_ps(ps_cmd)
    if not raw:
        logger.warning("USB/powershell retornou vazio. Nenhuma coleta USB feita neste ciclo.")
        return []

    printers_raw = None
    queues_raw = None
    drivers_raw = None
    pnp_raw = None
    registry_raw = None
    jobs_raw = None
    ports_raw = None
    for line in raw.splitlines():
        if not line:
            continue
        if line.startswith("JSON_START_PRINTERS "):
            try:
                printers_raw = json.loads(line[len("JSON_START_PRINTERS "):])
            except Exception as exc:
                logger.warning("USB parse JSON impressoras falhou: %s (prefixo OK, parte=%.120s)",
                               exc, line[len("JSON_START_PRINTERS "):])
        elif line.startswith("JSON_START_QUEUES "):
            try:
                queues_raw = json.loads(line[len("JSON_START_QUEUES "):])
            except Exception as exc:
                logger.warning("USB parse JSON filas spooler falhou: %s (parte=%.120s)",
                               exc, line[len("JSON_START_QUEUES "):])
        elif line.startswith("JSON_START_DRIVERS "):
            try:
                drivers_raw = json.loads(line[len("JSON_START_DRIVERS "):])
            except Exception as exc:
                logger.debug("USB parse JSON drivers falhou: %s", exc)
        elif line.startswith("JSON_START_PNP "):
            try:
                pnp_raw = json.loads(line[len("JSON_START_PNP "):])
            except Exception as exc:
                logger.debug("USB parse JSON PnP falhou: %s", exc)
        elif line.startswith("JSON_START_REGISTRY "):
            try:
                registry_raw = json.loads(line[len("JSON_START_REGISTRY "):])
            except Exception as exc:
                logger.debug("USB parse JSON Registry falhou: %s", exc)
        elif line.startswith("JSON_START_JOBS "):
            try:
                jobs_raw = json.loads(line[len("JSON_START_JOBS "):])
            except Exception as exc:
                logger.debug("USB parse JSON Jobs falhou: %s", exc)
        elif line.startswith("JSON_START_PORTS "):
            try:
                ports_raw = json.loads(line[len("JSON_START_PORTS "):])
            except Exception as exc:
                logger.debug("USB parse JSON Ports falhou: %s", exc)

    if printers_raw is None:
        logger.warning("USB: bloco JSON_START_PRINTERS nao foi encontrado no output PowerShell. Nenhuma impressora USB. (raw primeiras 500ch: %.500s)", raw)
        return []
    if isinstance(printers_raw, dict):
        printers_raw = [printers_raw]

    queues_map: dict[str, int] = {}
    if isinstance(queues_raw, dict):
        queues_raw = [queues_raw]
    for q in (queues_raw or []):
        try:
            qname = str(q.get("Name") or "").strip()
            try:
                pgs = int(q.get("TotalPagesPrinted") or 0)
            except Exception:
                pgs = 0
            if qname and pgs >= 0:
                queues_map[qname] = pgs
        except Exception as ex:
            logger.debug("USB queue parse erro: %s", ex)

    # --- P1: Contador cumulativo via registro ---
    registry_map: dict[str, dict[str, Any]] = {}
    if isinstance(registry_raw, dict):
        registry_raw = [registry_raw]
    for item in (registry_raw or []):
        try:
            printer_name = str(item.get("PrinterName") or "").strip()
            if printer_name:
                registry_map[printer_name] = {k: v for k, v in item.items()}
        except Exception as ex:
            logger.debug("USB registry item parse erro: %s", ex)

    # --- P1 MELHORADO: Contador por JOBS processados no spooler (Win32_PrintJob)! ---
    # Muitas impressoras Epson a gente consegue somar os trabalhos que jah passaram!
    jobs_map: dict[str, int] = {}
    if isinstance(jobs_raw, dict):
        jobs_raw = [jobs_raw]
    for j in (jobs_raw or []):
        try:
            # Nome tipo: "Epson M3170, Job 123" - separa pelo ", Job"
            full_name = str(j.get("Name") or "").strip()
            tp = j.get("TotalPages")
            try:
                tpi = int(tp) if tp else 0
            except Exception:
                tpi = 0
            if tpi <= 0:
                continue
            prn_name = full_name.split(", Job")[0].strip() if (", Job" in full_name) else full_name
            if prn_name:
                jobs_map[prn_name] = jobs_map.get(prn_name, 0) + tpi
        except Exception as ex:
            logger.debug("USB job parse erro: %s", ex)

    # --- P2 MAIS AGRESSIVO: PORTAS QUE EXISTEM REALMENTE ---
    # Se a impressora aponta para uma porta que NAO EXISTE nessa lista = FANTASMA (100% certeza!)
    ports_exist: set[str] = set()
    if isinstance(ports_raw, dict):
        ports_raw = [ports_raw]
    for p in (ports_raw or []):
        nm = str(p.get("Name") or "").strip()
        if nm:
            ports_exist.add(nm)
    if logger.isEnabledFor(logging.INFO):
        logger.info("USB: %d porta(s) real(is) instaladas no Windows (PrinterPort + USB Monitor).", len(ports_exist))
        if ports_exist:
            logger.info("  Lista portas: %s", ", ".join(sorted(ports_exist))[:400])

    # --- P2: Filtro DE DISPOSITIVOS CONECTADOS AGORA (PnP entities) ---
    # Usado para pular impressoras fantasmas (desinstaladas mas ainda no WMI)
    pnp_names: list[str] = []
    pnp_ports_usb_connected = False
    if isinstance(pnp_raw, list) and pnp_raw:
        for p in pnp_raw:
            nm = str(p.get("Name") or "").lower().strip()
            if nm:
                pnp_names.append(nm)
            did = str(p.get("DeviceID") or "").upper().strip()
            if did and ("USB\\" in did or "USBPRINT\\" in did or "DOT4\\" in did):
                pnp_ports_usb_connected = True
        logger.info("USB PnP entities conectadas agora: %d (USB/DOT4 detectado=%s)",
                    len(pnp_names), pnp_ports_usb_connected)

    if logger.isEnabledFor(logging.INFO):
        logger.info("USB WMI retornou %d impressora(s) bruta(s) e %d fila(s) spooler.",
                    len(printers_raw or []), len(queues_map))

    results: list[PrinterData] = []
    seen_slugs: set[str] = set()
    n_skipped_virtual = 0
    n_skipped_ghost_copy = 0
    n_skipped_offline_pnp = 0
    for idx, item in enumerate(printers_raw or []):
        try:
            name = str(item.get("Name") or "").strip()
            driver = str(item.get("DriverName") or "").strip()
            manufacturer = str(item.get("Manufacturer") or "").strip()
            port = str(item.get("PortName") or "").strip()
            status = str(item.get("Status") or item.get("ExtendedPrinterStatus") or "Unknown").strip()
            work_offline = str(item.get("WorkOffline") or "").strip().lower()
            printer_state = str(item.get("PrinterState") or item.get("PrinterStatus") or "").strip()
            local_flag = str(item.get("Local") or "").strip().lower()

            if not name:
                logger.debug("USB impressora idx=%d sem Name? pulado.", idx)
                continue

            if _is_virtual_printer(name, driver, port):
                n_skipped_virtual += 1
                logger.debug("USB skip virtual (pulado): name=%s port=%s driver=%s", name, port, driver)
                continue

            # ================================================================
            # P2 - FILTRO DE IMPRESSORAS FANTASMA / DESINSTALADAS / DUPLICADAS
            # ================================================================
            # Regra ZERO (MAIS AGRESSIVA, 100% INFALIVEL!):
            # Se a PORTA REAL da impressora NAO EXISTE na lista de portas reais do Windows
            # (ports_exist), essa impressora NAO EXISTE DE VERDADE (desinstalada ou fantasma!)
            # Exceto se for porta de REDE COMPARTILHADA tipo "\\servidor\impressora" etc
            port_up = port.upper()
            is_network_shared_port = port.startswith('\\') or port.lower().startswith(("http://", "https://", "wsd://", "ipp://", "ipps://"))
            is_physical_port_candidate = (
                port_up.startswith(("USB", "DOT4", "LPT", "COM", "IP_", "192.168.", "10.",
                                    "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.",
                                    "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.",
                                    "172.28.", "172.29.", "172.30.", "172.31.", "WSD", "IPP", "IPPS"))
                or bool(_IPV4_N_SUFFIX.match(port.strip()))
            )
            port_for_ghost_check = _IPV4_N_SUFFIX.match(port.strip())
            if port_for_ghost_check and (port not in ports_exist):
                if port_for_ghost_check.group(1) in ports_exist:
                    ports_exist.add(port)
            if port and not is_network_shared_port and is_physical_port_candidate:
                if port not in ports_exist:
                    n_skipped_offline_pnp += 1
                    logger.info("USB skip FANTASMA (Porta=%s NAO EXISTE em PrinterPort real! Impressora desinstalada.): name=%s", port, name)
                    continue

            # Regra 1: Nome com "(Copy 1)", "(Copy 2)", "(Copy 3)" etc = duplicata lixo
            if re.search(r"\(Copy\s*\d+\)", name, re.IGNORECASE):
                n_skipped_ghost_copy += 1
                logger.info("USB skip copia duplicada (lixo): name=%s", name)
                continue

            # Regra 2: WorkOffline = True / 1 (Windows marcou impressora como OFFLINE explicitamente)
            if work_offline in ("true", "1", "yes", "sim"):
                n_skipped_offline_pnp += 1
                logger.info("USB skip WorkOffline=True (nao conectada agora): name=%s port=%s", name, port)
                continue

            # Regra 3: ExtendedPrinterStatus = 1 (Unknown) OU Status vazio/Unknown + nao tem PnP match
            status_ext_raw = str(item.get("ExtendedPrinterStatus") or "").strip()
            is_physical_port = is_physical_port_candidate
            status_unknown = status.lower() in ("unknown", "", "none", "0") and status_ext_raw in ("1", "Unknown", "0", "")
            if is_physical_port and status_unknown and pnp_ports_usb_connected:
                name_match_pnp = any((n and n in name.lower()) or (name.lower() in n) for n in pnp_names)
                if not name_match_pnp:
                    n_skipped_offline_pnp += 1
                    logger.info("USB skip fantasma (sem match PnP + Status Unknown): name=%s port=%s", name, port)
                    continue

            # --- Paginas ---
            pages_total = queues_map.get(name)
            if pages_total is None:
                for qn, qp in queues_map.items():
                    if qn and (qn.lower() in name.lower() or name.lower() in qn.lower()):
                        pages_total = qp
                        break
            if pages_total is None:
                pages_total = 0
            # Se veio 0 mas temos TotalJobsPrinted na queue, usa ao menos isso (melhor que 0)
            if pages_total == 0 and isinstance(queues_raw, list):
                for q in queues_raw:
                    qname = str(q.get("Name") or "").strip()
                    if qname and qname.lower() == name.lower():
                        try:
                            tj = int(q.get("TotalJobsPrinted") or 0)
                            if tj > 0:
                                pages_total = tj
                        except Exception:
                            pass

            # ================================================================
            # P1 - CONTADOR CUMULATIVO VIA REGISTRO DO WINDOWS (HKLM Print\Printers)
            # + NOVO: _extract_all_plausible_page_counts (busca QUALQUER valor numerico >=100
            # em TODAS as chaves/subchaves, independente do nome da chave!)
            # + NOVO: jobs_map (soma TotalPages de todos os Win32_PrintJob historicos!)
            # ================================================================
            reg_dict = registry_map.get(name) if (registry_map and name) else None
            reg_pages_used = False
            reg_serial_used = False
            jobs_pages_used = False
            all_reg_candidates: list[int] = []
            if reg_dict:
                # 1) Tenta o extrator oficial por nome de chave
                reg_pages = _extract_page_counter_from_registry(reg_dict)
                if reg_pages is not None and (reg_pages > int(pages_total or 0)):
                    pages_total = int(reg_pages)
                    reg_pages_used = True
                # 2) Tenta extrator GENERICO por valor numerico plausivel (>=100) - cobre chaves exoticas Epson!
                all_reg_candidates = _extract_all_plausible_page_counts(reg_dict)
                for candidate in all_reg_candidates:
                    if candidate > int(pages_total or 0):
                        pages_total = int(candidate)
                        reg_pages_used = True
                # Log dos candidatos encontrados (para debug!)
                if logger.isEnabledFor(logging.DEBUG) and all_reg_candidates:
                    logger.debug("  USB REG candidatos contador para '%s': %s", name, all_reg_candidates[:10])
                # Também tenta pegar SERIAL NUMBER do registro (muitos drivers Epson salvam lá!)

            # 3) Usa JOBS historicos (Win32_PrintJob soma TotalPages processados!) - MELHOR estimativa vida util!
            job_pages = jobs_map.get(name)
            if job_pages is None and jobs_map:
                for jn, jp in jobs_map.items():
                    if jn and (jn.lower() in name.lower() or name.lower() in jn.lower()):
                        job_pages = jp
                        break
            if job_pages is not None and int(job_pages) > int(pages_total or 0):
                pages_total = int(job_pages)
                jobs_pages_used = True

            # Atualiza flags no logger
            model = driver or name
            serial = _extract_serial_from_port_or_name(port, name, driver)
            # Se temos serial melhor (do registro!), sobreescreve o regex guess:
            if reg_dict:
                try:
                    reg_serial_val = _extract_serial_from_registry(reg_dict)
                    if reg_serial_val and len(str(reg_serial_val)) >= 6:
                        serial = str(reg_serial_val)
                        reg_serial_used = True
                except Exception:
                    pass

            # ================================================================
            # FIX v6.9.4 CANON WIFI: TENTAR SNMP QUICK READ na porta de REDE!
            # Se a impressora for TCP/IP instalada manualmente (Canon WiFi etc),
            # extrai IP LIMPO da porta (remove IP_ prefixo + _N sufixo!) e tenta
            # SNMP de 1.5s. Se responder, usa CONTADORES REAIS DA IMPRESSORA e
            # seta ip_address com IP REAL para deduplicação não duplicar!
            # ================================================================
            host_from_port = _extract_host_from_port(port)
            snmp_ok = False
            toner_black_final: Optional[float] = None
            toner_cyan_final: Optional[float] = None
            toner_magenta_final: Optional[float] = None
            toner_yellow_final: Optional[float] = None
            alerts_final: list[str] = []

            if host_from_port:
                logger.debug("  USB->SNMP: porta=%s extraiu host=%s → tentando quick read 1.5s...",
                             port, host_from_port)
                rd = _snmp_quick_read(host_from_port)
                if rd is not None and (rd.pages_total > 0 or rd.model or rd.pages_color > 0):
                    # ================= SNMP DEU CERTO! USA DADOS REAIS! =================
                    snmp_ok = True
                    logger.info("  USB->SNMP OK! host=%s model=%s pag_total=%s pag_color=%s [usar estes contadores OFICIAIS!]",
                                host_from_port, rd.model or "(null)", rd.pages_total, rd.pages_color)
                    # Sobrescreve campos que vieram do SNMP pois são MELHORES!
                    if rd.pages_total >= int(pages_total or 0):
                        pages_total = int(rd.pages_total)
                    if rd.pages_bw is not None:
                        pages_bw_snmp = int(rd.pages_bw)
                    else:
                        pages_bw_snmp = 0
                    pages_color_snmp = int(rd.pages_color)
                    # Se paginas SNMP forem >0, confia em bw/color do SNMP 100%!
                    if rd.pages_total > 0 or pages_color_snmp > 0 or pages_bw_snmp > 0:
                        pages_bw_final = pages_bw_snmp
                        pages_color_final = pages_color_snmp
                        pages_total_final = int(rd.pages_total)
                    else:
                        pages_bw_final = int(pages_total or 0)
                        pages_color_final = 0
                        pages_total_final = int(pages_total or 0)
                    if rd.model:
                        model = str(rd.model)
                    if rd.manufacturer:
                        manufacturer = str(rd.manufacturer)
                    if rd.serial_number and len(str(rd.serial_number)) >= 4:
                        serial = str(rd.serial_number)
                        reg_serial_used = False
                    if rd.toner_black is not None:   toner_black_final   = rd.toner_black
                    if rd.toner_cyan is not None:    toner_cyan_final    = rd.toner_cyan
                    if rd.toner_magenta is not None: toner_magenta_final = rd.toner_magenta
                    if rd.toner_yellow is not None:  toner_yellow_final  = rd.toner_yellow
                    if rd.alerts:                    alerts_final        = list(rd.alerts)
                    # IP REAL! (para deduplicação com coleta SNMP broadcast funcionar!)
                    final_ip_address = host_from_port
                else:
                    pages_bw_final = int(pages_total or 0)
                    pages_color_final = 0
                    pages_total_final = int(pages_total or 0)
                    final_ip_address = None  # vai cair no USB:slug abaixo
            else:
                pages_bw_final = int(pages_total or 0)
                pages_color_final = 0
                pages_total_final = int(pages_total or 0)
                final_ip_address = None

            # ------------------ Se nao temos IP real (USB/SNMP falhou) -> fallback slug
            if final_ip_address is None:
                slug_base = _slugify(model + " " + (serial or name))
                slug = slug_base
                i = 2
                while slug in seen_slugs:
                    slug = f"{slug_base}_{i}"
                    i += 1
                seen_slugs.add(slug)
                final_ip_address = f"USB:{slug}"

            status_lc = status.lower()
            online = not any(k in status_lc for k in ("error", "offline", "unavailable", "paused"))
            if work_offline in ("true", "1"):
                online = False
            status_str = "online" if online else (status_lc or "unknown")
            if len(status_str) > 48:
                status_str = status_str[:48]

            printer = PrinterData(
                ip_address=final_ip_address,
                mac_address=None,
                model=model,
                manufacturer=manufacturer or None,
                serial_number=serial,
                status=status_str,
                pages_total=max(0, pages_total_final),
                pages_bw=max(0, pages_bw_final),
                pages_color=max(0, pages_color_final),
                toner_black=toner_black_final,
                toner_cyan=toner_cyan_final,
                toner_magenta=toner_magenta_final,
                toner_yellow=toner_yellow_final,
                alerts=alerts_final,
            )
            pages_src_parts = []
            if reg_pages_used: pages_src_parts.append("REG_CUMULATIVO")
            if jobs_pages_used: pages_src_parts.append("JOBS_SPOOLER_HISTORICO")
            if (not pages_src_parts) and int(pages_total or 0) > 0: pages_src_parts.append("SPOOLER_DESDE_BOOT")
            if int(pages_total or 0) == 0:
                pages_src_parts.append("ZERO (ou driver nao expoe contador cumulativo ou nenhuma pagina impressa ainda)")
            pages_src_info = " | ".join(pages_src_parts)
            if snmp_ok:
                pages_src_info = "SNMP_QUICK_READ (REDE TCP/IP!) | " + pages_src_info
            if all_reg_candidates:
                pages_src_info += (" [candidatos_reg: " + ",".join(str(x) for x in all_reg_candidates[:8]) + "]")
            serial_src = "REG" if reg_serial_used else ("PORT/NM" if serial else "NAO_LIDO")

            results.append(printer)
            logger.info("  USB OK [%s] %s | port=%s | pag=%s [%s] | serial=%s [%s] | local=%s | state=%s",
                        final_ip_address, model, port or "?", pages_total_final, pages_src_info,
                        serial or "(nao lido)", serial_src,
                        local_flag or "?", printer_state or "")
        except Exception as ex:
            logger.warning("USB item parse erro idx=%d item=%.200s: %s (type=%s)",
                           idx, str(item), ex, type(ex).__name__, exc_info=True)
            continue

    logger.info("USB final: %d impressora(s) coletadas, %d pulada(s) (virtual), "
                "%d pulada(s) (copy duplicata), %d pulada(s) (offline/fantasma).",
                len(results), n_skipped_virtual, n_skipped_ghost_copy, n_skipped_offline_pnp)
    return results


def collect_all_usb() -> list[PrinterData]:
    """Entry point principal. Chama a funcao correta conforme SO.
    Qualquer erro retorna [] - NAO QUEBRA a coleta SNMP (ADITIVO 100%).
    """
    try:
        system = platform.system().lower()
        if system != "windows":
            logger.debug("Coleta USB skip: SO=%s (apenas Windows por enquanto)", system)
            return []
        n = _collect_windows()
        if n:
            logger.info("Coleta USB: %d impressora(s) fisica(s) locais encontradas.", len(n))
        else:
            logger.info("Coleta USB: nenhuma impressora fisica local encontrada neste ciclo (pode ser normal se nao houver USB/LPT/Shared).")
        return n
    except Exception as exc:
        logger.warning("Coleta USB FALHOU de maneira geral (ignorado, SNMP continua ok): %s (type=%s)",
                       exc, type(exc).__name__, exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Teste standalone: python -m print_collect.usb
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
    lst = collect_all_usb()
    print(f"\nEncontradas {len(lst)} impressora(s) USB/Local via Windows:")
    for r in lst:
        print(f"  - ip_virtual={r.ip_address} modelo={r.model} fabricante={r.manufacturer} "
              f"serial={r.serial_number} pag_total={r.pages_total} status={r.status}")
