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


def _run_ps(cmd: str) -> str:
    """Executa comando PowerShell retornando stdout como UTF-8 seguro.
    Importante: chcp 65001 ANTES para garantir que acentos (Epson EcoTank Série etc)
    sejam retornados em UTF-8, evitando erros de JSON parse.
    """
    try:
        # cmd = comando PowerShell a rodar. Precisamos rodar PS com MTA (padrão) +
        # força UTF8 no PowerShell, antes de rodar qualquer coisa:
        wrapped = f"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
chcp 65001 > $null
{cmd}
"""
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", wrapped],
            capture_output=True,
            timeout=120,
        )
        out_bytes = proc.stdout or b""
        err_bytes = proc.stderr or b""
        # Tenta UTF8 estrito, se falhar usa latin1 (CP1252 fallback, nunca levanta exceção)
        try:
            text = out_bytes.decode("utf-8", errors="replace")
        except Exception:
            text = out_bytes.decode("latin-1", errors="replace")
        # Se veio stderr não-vazio (e stdout vazio), loga como debug (não quebra nada):
        if err_bytes and not out_bytes:
            try:
                logger.debug("USB/powershell stderr: %s", err_bytes.decode("utf-8", errors="replace")[:800])
            except Exception:
                pass
        return text
    except subprocess.TimeoutExpired as exc:
        logger.warning("USB/PowerShell demorou mais de 120s (timeout): %s", exc)
        return ""
    except Exception as exc:
        logger.warning("USB/powershell erro geral: %s (type=%s)", exc, type(exc).__name__)
        return ""


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
            is_network_shared_port = port.startswith('\\') or port.lower().startswith(("http://", "https://", "wsd://", "ipp://"))
            is_physical_port_candidate = port_up.startswith(("USB", "DOT4", "LPT", "COM", "IP_", "192.168.", "10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31."))
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

            slug_base = _slugify(model + " " + (serial or name))
            slug = slug_base
            i = 2
            while slug in seen_slugs:
                slug = f"{slug_base}_{i}"
                i += 1
            seen_slugs.add(slug)
            ip_virtual = f"USB:{slug}"

            bw = int(pages_total or 0)
            color = 0

            status_lc = status.lower()
            online = not any(k in status_lc for k in ("error", "offline", "unavailable", "paused"))
            if work_offline in ("true", "1"):
                online = False
            status_str = "online" if online else (status_lc or "unknown")
            if len(status_str) > 48:
                status_str = status_str[:48]

            printer = PrinterData(
                ip_address=ip_virtual,
                mac_address=None,
                model=model,
                manufacturer=manufacturer or None,
                serial_number=serial,
                status=status_str,
                pages_total=bw + color,
                pages_bw=bw,
                pages_color=color,
                toner_black=None,
                toner_cyan=None,
                toner_magenta=None,
                toner_yellow=None,
                alerts=[],
            )
            pages_src_parts = []
            if reg_pages_used: pages_src_parts.append("REG_CUMULATIVO")
            if jobs_pages_used: pages_src_parts.append("JOBS_SPOOLER_HISTORICO")
            if (not pages_src_parts) and int(pages_total or 0) > 0: pages_src_parts.append("SPOOLER_DESDE_BOOT")
            if int(pages_total or 0) == 0:
                pages_src_parts.append("ZERO (ou driver nao expoe contador cumulativo ou nenhuma pagina impressa ainda)")
            pages_src_info = " | ".join(pages_src_parts)
            if all_reg_candidates:
                pages_src_info += (" [candidatos_reg: " + ",".join(str(x) for x in all_reg_candidates[:8]) + "]")
            serial_src = "REG" if reg_serial_used else ("PORT/NM" if serial else "NAO_LIDO")

            results.append(printer)
            logger.info("  USB OK [%s] %s | port=%s | pag=%s [%s] | serial=%s [%s] | local=%s | state=%s",
                        ip_virtual, model, port or "?", pages_total, pages_src_info,
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
