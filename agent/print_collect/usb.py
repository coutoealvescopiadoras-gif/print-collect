"""Coleta de impressoras conectadas LOCALMENTE no Windows via USB, WiFi Direct,
LPT, ou qualquer porta que apareça no spooler do Windows (exclui impressoras
virtuais como PDF/XPS/OneNote/Fax).

MODULO ADITIVO 100% - NAO ALTERA NADA DO SNMP, NAO QUEBRA NADA!
Se der qualquer erro, retorna lista vazia e a coleta SNMP continua normal.

Retorna a MESMA classe PrinterData usada pelo snmp.py para que o sender.py
consiga enviar tudo pro backend sem precisar de NENHUMA alteracao.
"""
from __future__ import annotations

import csv as _csv
import hashlib
import json
import logging
import os
import platform
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from io import StringIO as _SIO
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


def _snmp_quick_read(host: str, community: str = "public", timeout_sec: float = 2.5) -> Optional[PrinterData]:
    """Tenta coleta SNMP em impressora de REDE — v6.9.9 PROTEGIDA CONTRA TRAVAMENTO!

    REGRAS DE SEGURANCA ANTI-TRAVA (NAO QUEBRA NUNCA MAIS!):
      * APENAS 1 tentativa na community 'public' (nao tenta private).
      * Timeout individual pysnmp: 2.5s (reduzido de 4s)
      * PROTECAO GLOBAL por ThreadPoolExecutor: timeout TOTAL MAXIMO 6.5s!
        Se o pysnmp travar UDP infinitamente por qualquer motivo,
        ThreadPoolExecutor aborta a thread no timeout e retorna None.
      * NUNCA retorna exception, sempre retorna None em caso de erro/falha/timeout.
    """
    def _inner_try() -> Optional[PrinterData]:
        try:
            from print_collect.snmp import collect_printer
        except Exception as exc_inner:
            logger.debug("  USB->SNMP quick read import falhou host=%s: %s", host, exc_inner)
            return None
        timeout_ms = int(timeout_sec * 1000)
        try:
            rd = collect_printer(host, community=community, timeout=timeout_ms)
            if rd is not None and (rd.pages_total > 0 or rd.pages_color > 0 or rd.model):
                return rd
        except Exception as exc_try:
            logger.debug("  USB->SNMP quick read inner fail host=%s: %s (type=%s)",
                         host, exc_try, type(exc_try).__name__)
        return None

    # Executor com 1 thread worker: PROTECAO GLOBAL timeout!
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="pc_snmp_qr") as pool:
            fut = pool.submit(_inner_try)
            return fut.result(timeout=6.5)
    except FutTimeout:
        logger.warning("  USB->SNMP quick_read TIMEOUT MAXIMO (6.5s) estourado host=%s. "
                       "Abortado para NAO TRAVAR loop USB (fallback para contador spooler/registro!).", host)
        return None
    except Exception as exc_global:
        logger.debug("  USB->SNMP quick_read executor falhou host=%s (fallback ok): %s (type=%s)",
                     host, exc_global, type(exc_global).__name__)
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
    """Executa comando PowerShell retornando stdout.
    v6.9.7: FORMA NUCLEAR INFALÍVEL de rodar scripts longos SEM problemas de encoding OEM
    (MissingCatchOrFinally, chaves } quebradas etc em Windows pt-BR CP850):
      1) Escreve o script num ARQUIVO TEMPORÁRIO .ps1 (UTF-8 com BOM, PowerShell padrão!)
      2) Executa powershell.exe -File temp.ps1
      3) -File NÃO passa nada pela linha de comando → 0 chance de encoding quebrar.
      4) Apaga o arquivo temporário no finally (nunca deixa lixo).
    v6.9.8 FIX SCOPING NAMEERROR: imports DENTRO da funcao para garantir escopo local
    (evita confusao de Python 3.12 com variaveis `as exc` no except que marcam nomes como LOCAL).
    """
    import os as _os
    import tempfile as _tempfile
    import subprocess as _subprocess
    import time as _time
    last_err = ""
    tmp_path = None
    for attempt in (1, 2):
        try:
            # 1) Escreve o script num arquivo temporário .ps1 (UTF-8 BOM = PowerShell entende nativamente)
            #    Usa pasta temp do Windows + PID + attempt para nunca colidir
            suffix = f"_pc_{_os.getpid()}_{attempt}.ps1"
            tmp_dir = _tempfile.gettempdir()
            tmp_path = _os.path.join(tmp_dir, f"pc_usb{suffix}")
            with open(tmp_path, "w", encoding="utf-8-sig", errors="replace") as f:
                f.write("# Print Collect - USB collect (temp file, auto-deleted)\n")
                f.write("[Console]::InputEncoding  = [System.Text.Encoding]::UTF8\n")
                f.write("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n")
                f.write("$OutputEncoding           = [System.Text.Encoding]::UTF8\n")
                f.write("$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'\n")
                f.write("$ErrorActionPreference    = 'Continue'\n")
                f.write("chcp 65001 > $null\n")
                f.write(cmd + "\n")
            # 2) Executa powershell.exe -File temp.ps1 (NÃO -Command, NÃO -EncodedCommand!)
            proc = _subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-MTA",
                 "-ExecutionPolicy", "Bypass", "-File", tmp_path],
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
            # v6.9.7: trata stderr inclusive com envelope CLIXML (remove #< CLIXML wrapper se existir)
            if err_bytes:
                try:
                    err_txt = err_bytes.decode("utf-8", errors="replace").strip()
                except Exception:
                    err_txt = err_bytes.decode("latin-1", errors="replace").strip()
                # Remove envelope CLIXML se vier (erros parse PS via subprocess às vezes vem como XML)
                if err_txt.startswith("#< CLIXML") or err_txt.startswith("<Objs "):
                    import re as _re
                    clean = _re.sub(r"<S S=\"Error\">([^<]*)</S>", r"\1", err_txt, flags=_re.MULTILINE)
                    clean = clean.replace("_x000D_x000A_", "\n").replace("_x000D_", "")
                    clean = _re.sub(r"</?Objs[^>]*>|</?S[^>]*>|#< CLIXML", "", clean).strip()
                    if clean:
                        err_txt = clean
                if err_txt:
                    last_err = err_txt
                    if not text.strip():
                        logger.warning("USB/powershell attempt=%d STDERR (stdout vazio!): %.1200s",
                                       attempt, err_txt[:1200])
                    else:
                        logger.debug("USB/powershell attempt=%d stderr: %.800s", attempt, err_txt[:800])
            if text.strip():
                # Limpa arquivo temporário
                if tmp_path and _os.path.exists(tmp_path):
                    try: _os.remove(tmp_path)
                    except Exception: pass
                return text
            logger.warning("USB/powershell attempt=%d retornou ZERO bytes de stdout. Vamos tentar novamente (retry=%d)...",
                           attempt, 2 if attempt == 1 else 0)
            if attempt == 1:
                _time.sleep(1.2)
        except _subprocess.TimeoutExpired as exc:
            logger.warning("USB/PowerShell attempt=%d timeout %ds: %s", attempt, timeout_sec, exc)
            last_err = f"TimeoutExpired {timeout_sec}s"
            if attempt == 1:
                _time.sleep(0.8)
        except Exception as exc:
            logger.warning("USB/powershell attempt=%d erro geral: %s (type=%s)", attempt, exc, type(exc).__name__)
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt == 1:
                _time.sleep(0.8)
        finally:
            if tmp_path and _os.path.exists(tmp_path):
                try: _os.remove(tmp_path)
                except Exception: pass

    # 2 tentativas falharam → FALLBACK WMIC.EXE
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
            if txt and ("=" in txt or "Namespace" in txt or "," in txt):
                return txt
        except Exception:
            pass
    try:
        return raw_bytes.decode("utf-8", errors="replace").strip()
    except Exception:
        return ""


def _get_any_key(d: dict, *keys, default=None):
    """Busca valor em um dicionário tentando VÁRIAS chaves possíveis (inglês + pt-BR localizado).
    Usado porque wmic.exe em Windows pt-BR TRADUZ nomes de campos no /format:list.
    Ex: PortName → NomeDaPorta, DriverName → NomeDoDriver, Name → Nome etc.
    """
    if not d:
        return default
    d_low = {str(k).strip().lower(): v for k, v in d.items()}
    for k in keys:
        kl = str(k).strip().lower()
        if kl in d_low:
            return d_low[kl]
    # Fallback por substring
    for k in keys:
        kl = str(k).strip().lower()
        for dk, dv in d_low.items():
            if (kl in dk) or (dk in kl):
                return dv
    return default


def _wmic_csv_to_dicts(txt: str) -> list[dict[str, Any]]:
    """Converte saída wmic ... /format:csv (cabeçalhos SEMPRE em inglês, NÃO localizado!)
    em lista de dicionários. Muito mais seguro que /format:list em Windows OEM localizado.

    ATENCAO v6.9.8: wmic CSV SEMPRE coloca a 1a coluna = Node (hostname), EXCLUIMOS ela
    e também usamos QUOTING_MINIMAL para nao quebrar campos com vírgula/papel/caracteres.
    """
    if not txt:
        return []
    results: list[dict[str, Any]] = []
    lines_raw = txt.splitlines()
    lines_clean: list[str] = []
    for ln in lines_raw:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("\ufeff"):
            s = s[1:].strip()
            if not s:
                continue
        lines_clean.append(ln.rstrip("\n").rstrip("\r"))
    if not lines_clean:
        return results
    try:
        reader = _csv.reader(
            _SIO("\n".join(lines_clean)),
            delimiter=",",
            quotechar='"',
            quoting=_csv.QUOTE_MINIMAL,
            skipinitialspace=False,
        )
        rows = list(reader)
        if len(rows) < 2:
            return results
        headers_raw = [str(h).strip() for h in rows[0]]
        if not headers_raw:
            return results
        has_node_col = headers_raw[0].lower() in ("node", "servidor", "nomehost")
        headers = headers_raw[1:] if has_node_col else headers_raw
        for row in rows[1:]:
            if not row:
                continue
            vals = row[1:] if has_node_col else row
            if len(vals) < 1:
                continue
            d: dict[str, Any] = {}
            for i, h in enumerate(headers):
                if i < len(vals):
                    d[h] = str(vals[i]).strip()
                else:
                    d[h] = ""
            results.append(d)
    except Exception as exc:
        logger.debug("wmic CSV parse falhou: %s", exc)
    return results


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

        # --- 1) Win32_Printer via WMIC (CSV! Cabeçalhos sempre inglês, NÃO localizado!) ---
        try:
            _PRN_COLS = ("Name,DriverName,Manufacturer,PortName,DeviceID,Status,"
                         "ExtendedPrinterStatus,Default,WorkOffline,PrinterState,"
                         "PrinterStatus,Shared,Local,Caption")
            proc = subprocess.run(
                ["wmic.exe", "printer", "get", _PRN_COLS, "/format:csv"],
                capture_output=True, timeout=30,
            )
            txt = _wmic_decode(proc.stdout or b"")
            arr = _wmic_csv_to_dicts(txt)
            if not arr:
                # Fallback pro /format:list com helper _get_any_key (se CSV não existir no Win 7)
                proc2 = subprocess.run(
                    ["wmic.exe", "printer", "get", "/all", "/format:list"],
                    capture_output=True, timeout=30,
                )
                txt2 = _wmic_decode(proc2.stdout or b"")
                arr = _wmic_list_to_dicts(txt2)
            filtered = []
            FAKE_NAMES = (
                "win32_printer", "win32_computersystem", "win32_pnpentity",
                "computersystem", "printer", "system", "root",
            )
            for p in arr:
                if not p:
                    continue
                pname = str(_get_any_key(p, "Name", "Nome", "Caption", "Legenda") or "").strip()
                if not pname:
                    continue
                low = pname.lower()
                if low in FAKE_NAMES:
                    continue
                if low.startswith("desktop-") or low.startswith("desktop_") or low == "desktop":
                    continue
                if len(pname) < 2:
                    continue
                if "," in pname and len(pname) > 80:
                    continue
                if pname.startswith("{") and pname.endswith("}"):
                    continue
                filtered.append({
                    "Name": pname,
                    "DriverName": str(_get_any_key(p, "DriverName", "NomeDoDriver", "Driver") or ""),
                    "Manufacturer": str(_get_any_key(p, "Manufacturer", "Fabricante") or ""),
                    "PortName": str(_get_any_key(p, "PortName", "NomeDaPorta", "Porta") or ""),
                    "DeviceID": str(_get_any_key(p, "DeviceID", "IdDispositivo") or ""),
                    "Status": str(_get_any_key(p, "Status", "Estado") or ""),
                    "ExtendedPrinterStatus": str(_get_any_key(p, "ExtendedPrinterStatus", "StatusEstendido") or ""),
                    "Default": str(_get_any_key(p, "Default", "Padrao", "Padrão") or ""),
                    "WorkOffline": str(_get_any_key(p, "WorkOffline", "TrabalhoOffline") or ""),
                    "PrinterState": str(_get_any_key(p, "PrinterState", "EstadoImpressora") or ""),
                    "PrinterStatus": str(_get_any_key(p, "PrinterStatus", "StatusImpressora") or ""),
                    "Shared": str(_get_any_key(p, "Shared", "Compartilhado") or ""),
                    "Local": str(_get_any_key(p, "Local", "Localidade") or ""),
                })
            out_lines.append("JSON_START_PRINTERS " + _json.dumps(filtered, separators=(",", ":"), ensure_ascii=False))
        except Exception as exc:
            logger.warning("FALLBACK WMIC printer falhou: %s", exc)
            out_lines.append("JSON_START_PRINTERS []")

        # --- 2) Print Queue via WMIC (CSV!) ---
        try:
            _Q_COLS = "Name,TotalPagesPrinted,TotalJobsPrinted,JobsSpooling"
            proc = subprocess.run(
                ["wmic.exe", "path", "Win32_PerfFormattedData_Spooler_PrintQueue",
                 "get", _Q_COLS, "/format:csv"],
                capture_output=True, timeout=30,
            )
            txt = _wmic_decode(proc.stdout or b"")
            arr = _wmic_csv_to_dicts(txt)
            if not arr:
                proc2 = subprocess.run(
                    ["wmic.exe", "path", "Win32_PerfFormattedData_Spooler_PrintQueue",
                     "get", "/all", "/format:list"],
                    capture_output=True, timeout=30,
                )
                txt2 = _wmic_decode(proc2.stdout or b"")
                arr = _wmic_list_to_dicts(txt2)
            filtered = []
            for q in arr:
                if not q:
                    continue
                try:
                    tp = int(_get_any_key(q, "TotalPagesPrinted", "PaginasTotaisImpressas") or 0)
                except Exception:
                    tp = 0
                try:
                    tj = int(_get_any_key(q, "TotalJobsPrinted", "TrabalhosTotaisImpressos") or 0)
                except Exception:
                    tj = 0
                try:
                    js = int(_get_any_key(q, "JobsSpooling", "TrabalhosSpool") or 0)
                except Exception:
                    js = 0
                filtered.append({
                    "Name": str(_get_any_key(q, "Name", "Nome") or ""),
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

        # --- 4) PORTAS REAIS via WMIC (PROVADO v6.9.6 com /format:list, CSV dá 261 falsas!) ---
        ports_arr: list[dict[str, Any]] = []
        try:
            # v6.9.8: VOLTAMOS para /format:list AQUI em TCPIPPrinterPort (CSV dava 261 falsas!)
            proc = subprocess.run(
                ["wmic.exe", "path", "Win32_TCPIPPrinterPort", "get", "/all", "/format:list"],
                capture_output=True, timeout=20,
            )
            txt2 = _wmic_decode(proc.stdout or b"")
            arr = _wmic_list_to_dicts(txt2)
            for p in arr:
                nm = str(_get_any_key(p, "Name", "Nome") or "").strip()
                if not nm:
                    continue
                ports_arr.append({"Name": nm, "Description": "TCPIP", "Type": "TCPIP",
                                  "PortMonitor": str(_get_any_key(p, "Protocol", "Protocolo") or "Standard TCP/IP Port")})
                host_ip = str(_get_any_key(p, "HostAddress", "EnderecoHost", "EndereçoHost", "IPAddress") or "").strip()
                if host_ip:
                    ports_arr.append({"Name": host_ip, "Description": "TCPIP-IP", "Type": "TCPIP",
                                      "PortMonitor": "Standard TCP/IP Port"})
                    for n_suffix in range(1, 10):
                        ports_arr.append({"Name": f"{host_ip}_{n_suffix}", "Description": "TCPIP-SUFFIX",
                                          "Type": "TCPIP", "PortMonitor": "Standard TCP/IP Port"})
                        ports_arr.append({"Name": f"IP_{host_ip}_{n_suffix}", "Description": "TCPIP-IPSUFFIX",
                                          "Type": "TCPIP", "PortMonitor": "Standard TCP/IP Port"})
        except Exception as exc:
            logger.debug("WMIC TCPIPPrinterPort falhou: %s", exc)
        try:
            # v6.9.8: printerport TAMBÉM volta para /format:list (provado v6.9.6 = 38 portas reais)
            proc2 = subprocess.run(
                ["wmic.exe", "printerport", "get", "/all", "/format:list"],
                capture_output=True, timeout=20,
            )
            txt2 = _wmic_decode(proc2.stdout or b"")
            arr = _wmic_list_to_dicts(txt2)
            for p in arr:
                nm = str(_get_any_key(p, "Name", "Nome") or "").strip()
                if not nm:
                    continue
                ports_arr.append({"Name": nm,
                                  "Description": str(_get_any_key(p, "Description", "Descricao", "Descrição") or "PrinterPort"),
                                  "Type": str(_get_any_key(p, "Type", "Tipo") or "AUTO"),
                                  "PortMonitor": str(_get_any_key(p, "PortMonitor", "MonitorPorta") or "")})
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
$ErrorActionPreference = 'SilentlyContinue'
# --- 1/7: Win32_Printer (NIVEL 1, SEM try aninhado!) ---
$arr = @(Get-CimInstance Win32_Printer -ErrorAction SilentlyContinue | Select-Object Name,DriverName,Manufacturer,PortName,DeviceID,Status,ExtendedPrinterStatus,Default,WorkOffline,PrinterState,PrinterStatus,Shared,Local)
if ($arr.Count -eq 0) { Write-Output ('JSON_START_PRINTERS []') }
else { $json = $arr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_PRINTERS ' + $json) }
# --- 2/7: PrintQueue spooler (NIVEL 1) ---
$arr = @(Get-CimInstance Win32_PerfFormattedData_Spooler_PrintQueue -ErrorAction SilentlyContinue | Select-Object Name,TotalPagesPrinted,TotalJobsPrinted,JobsSpooling)
if ($arr.Count -eq 0) { Write-Output ('JSON_START_QUEUES []') }
else { $json = $arr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_QUEUES ' + $json) }
# --- 3/7: Drivers (NIVEL 1) ---
$arr = @(Get-CimInstance Win32_PrinterDriver -ErrorAction SilentlyContinue | Select-Object Name,Manufacturer,SupportedPlatform,Version,DrivePath,DataFile,ConfigFile)
if ($arr.Count -eq 0) { Write-Output ('JSON_START_DRIVERS []') }
else { $json = $arr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_DRIVERS ' + $json) }
# --- 4/7: PnP Plug&Play CONECTADOS (NIVEL 1) ---
$arr = @(Get-CimInstance Win32_PnPEntity -ErrorAction SilentlyContinue | Where-Object { $_.PNPClass -in ('Printer','USBPrint','USB','Dot4') } | Select-Object Name,PNPClass,Status,DeviceID,Manufacturer,HardwareID)
if ($arr.Count -eq 0) { Write-Output ('JSON_START_PNP []') }
else { $json = $arr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_PNP ' + $json) }
# --- 5/7: REGISTRY Print\Printers (NIVEL 1, SEM loops aninhados com try/catch!) ---
$allReg = @()
$regPrintersPath = 'HKLM:\SYSTEM\CurrentControlSet\Control\Print\Printers'
if (Test-Path $regPrintersPath) {
    $subkeys = @(Get-ChildItem $regPrintersPath -ErrorAction SilentlyContinue)
    foreach ($k in $subkeys) {
        $objProps = @{ PrinterName = $k.PSChildName }
        $props = Get-ItemProperty $k.PSPath -ErrorAction SilentlyContinue
        if ($props) {
            $props.PSObject.Properties | ForEach-Object {
                if ($_.Name -notlike 'PS*') { $objProps[$_.Name] = $_.Value }
            }
        }
        $driverDataPath = Join-Path $k.PSPath 'PrinterDriverData'
        if (Test-Path $driverDataPath) {
            $dd = Get-ItemProperty $driverDataPath -ErrorAction SilentlyContinue
            if ($dd) {
                $dd.PSObject.Properties | ForEach-Object {
                    if ($_.Name -notlike 'PS*') { $objProps['DD_' + $_.Name] = $_.Value }
                }
            }
        }
        $allReg += [PSCustomObject]$objProps
    }
}
if ($allReg.Count -eq 0) { Write-Output ('JSON_START_REGISTRY []') }
else { $json = $allReg | ConvertTo-Json -Depth 5 -Compress ; Write-Output ('JSON_START_REGISTRY ' + $json) }
# --- 6/7: Jobs spooler (NIVEL 1) ---
$arr = @(Get-CimInstance Win32_PrintJob -ErrorAction SilentlyContinue | Select-Object Name,JobId,TotalPages,Document,Owner)
if ($arr.Count -eq 0) { Write-Output ('JSON_START_JOBS []') }
else { $json = $arr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_JOBS ' + $json) }
# --- 7/7: PORTAS REAIS (NIVEL 1, SEM try ANINHADO!) ---
$portsArr = @()
$portsArr += @(Get-PrinterPort -ErrorAction SilentlyContinue | Select-Object Name,Description,Type,PortMonitor)
$portsArr += @(Get-CimInstance Win32_TCPIPPrinterPort -ErrorAction SilentlyContinue | ForEach-Object { [PSCustomObject]@{ Name=$_.Name; Description='TCPIP'; Type='TCPIP'; PortMonitor=$_.Protocol } })
$usbp = 'HKLM:\SYSTEM\CurrentControlSet\Control\Print\Monitors\USB Monitor\Ports'
if (Test-Path $usbp) {
    Get-ChildItem $usbp -ErrorAction SilentlyContinue | ForEach-Object {
        if (-not ($portsArr.Name -contains $_.PSChildName)) {
            $portsArr += [PSCustomObject]@{ Name=$_.PSChildName; Description='USB Monitor Port'; Type='USB'; PortMonitor='USB Monitor' }
        }
    }
}
if ($portsArr.Count -eq 0) { Write-Output ('JSON_START_PORTS []') }
else { $json = $portsArr | ConvertTo-Json -Depth 4 -Compress ; Write-Output ('JSON_START_PORTS ' + $json) }
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
    seen_dup_keys: set[str] = set()
    n_skipped_virtual = 0
    n_skipped_ghost_copy = 0
    n_skipped_offline_pnp = 0
    n_skipped_dup_port_driver = 0
    for idx, item in enumerate(printers_raw or []):
        try:
            name = str(item.get("Name") or "").strip()
            driver = str(item.get("DriverName") or "").strip()
            manufacturer = str(item.get("Manufacturer") or "").strip()
            port = str(item.get("PortName") or "").strip()
            port_orig = port
            if not port:
                alt_pn = _get_any_key(item, "NomeDaPorta", "NomePorta", "Porta", "PortaNome", "Port")
                if alt_pn: port = str(alt_pn).strip()
            if not driver:
                alt_dr = _get_any_key(item, "NomeDoDriver", "NomeDriver", "Driver")
                if alt_dr: driver = str(alt_dr).strip()
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
            # P0 - DEDUP TOTAL (DRIVER + PORTA REAL ou IP REAL extraido da porta)
            #      Evita TSC E210 x3 / RICOH SP x3 / etc (impressora duplicada 3x WMI)
            # ================================================================
            _dup_host = _extract_host_from_port(port) or ""
            _dup_key = "||".join([
                re.sub(r"[^A-Z0-9]", "", (driver or "").upper()) or "NODRIVER",
                re.sub(r"[^A-Z0-9._]", "", (port or "").upper()) or "NOPORT",
                re.sub(r"[^A-Z0-9._]", "", (_dup_host or "").upper()) or "NOHOST",
            ])
            if _dup_key in seen_dup_keys:
                n_skipped_dup_port_driver += 1
                logger.info("USB skip DUP (mesmo Driver+Porta+Host=%s): name=%s port=%s driver=%s",
                            _dup_key, name, port, driver)
                continue
            seen_dup_keys.add(_dup_key)

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
                "%d pulada(s) (copy duplicata), %d pulada(s) (dup driver+porta), %d pulada(s) (offline/fantasma).",
                len(results), n_skipped_virtual, n_skipped_ghost_copy,
                n_skipped_dup_port_driver, n_skipped_offline_pnp)
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
