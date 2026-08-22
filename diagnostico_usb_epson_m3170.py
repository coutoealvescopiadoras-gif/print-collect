"""Diagnostico USB PORTA TIL - RODA SEM INSTALAR NADA!
Basta levar esse arquivo em pendrive no PC da CEA e clicar 2x (ou executar
como python se tiver interpretador) que ele salva um relatorio na propria
pasta do arquivo com TUDO: impressoras instaladas, portas, drivers,
contadores de pagina do spooler.

Julio, se o PowerShell estiver bloqueado, use tambem o diagnostico em .bat
que eu criarei junto!
"""
from __future__ import annotations
import os, sys, json, subprocess, re, datetime, platform

SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.argv[0] if len(sys.argv) > 0 else "."))
now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT_FILE = os.path.join(SCRIPT_DIR, f"DIAGNOSTICO_USB_PRINTCOLLECT_{now_str}.txt")

def log(msg: str) -> None:
    print(msg, flush=True)
    try:
        with open(REPORT_FILE, "a", encoding="utf-8", errors="replace") as f:
            f.write(msg + "\n")
    except Exception:
        pass

def run(cmd: list[str], timeout: int = 60) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
        return "[stdout]\n" + (proc.stdout or "") + "\n\n[stderr rc=" + str(proc.returncode) + "]\n" + (proc.stderr or "")
    except Exception as e:
        return f"[EXEC FAIL {type(e).__name__}: {e}]"

def main() -> int:
    print("=" * 90, flush=True)
    print(f"DIAGNOSTICO USB Print Collect - {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 90, flush=True)
    # Cabecalho
    log("=" * 90)
    log(f"DIAGNOSTICO IMPRESSORAS USB / LOCAIS WINDOWS")
    log(f"Horario local: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    log(f"Maquina: {platform.node()}  |  OS: {platform.platform()}  |  Arquitetura: {platform.machine()}")
    log(f"Python: {sys.executable} (v{sys.version})")
    log(f"Relatorio salvo em: {REPORT_FILE}")
    log("=" * 90)

    # Teste rapido: consegue executar powershell?
    log("\n")
    log("===[ 1/3 ] EXECUTANDO POWERSHELL (Win32_Printer + Queue)")
    log("-" * 90)
    ps = r"""
$ErrorActionPreference = 'Continue'
Write-Output ">>>>>> PRINTERS <<<<<<"
try {
    Get-CimInstance Win32_Printer -ErrorAction SilentlyContinue |
        Format-List Name,DriverName,Manufacturer,PortName,DeviceID,WorkOffline,Default,Status,ExtendedPrinterStatus,Location,Comment
} catch { Write-Output "ERRO_PRINTERS: $_" }
Write-Output ">>>>>> QUEUES <<<<<<"
try {
    Get-CimInstance Win32_PerfFormattedData_Spooler_PrintQueue -ErrorAction SilentlyContinue |
        Format-List Name,TotalPagesPrinted,TotalJobsPrinted,Jobs,Errors
} catch { Write-Output "ERRO_QUEUES: $_" }
Write-Output ">>>>>> DRIVER EPSON <<<<<<"
try {
    Get-CimInstance Win32_PrinterDriver -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'Epson|M3170|3170' } | Format-List Name,SupportedPlatform,DependentFiles,Version
} catch { Write-Output "ERRO_DRIVERS: $_" }
"""
    out = run(["powershell.exe", "-NoProfile", "-NonInteractive",
               "-ExecutionPolicy", "Bypass", "-Command", ps])
    log(out)

    # Teste com printui.dll / enum printers Windows API (fallback se WMI bloquear)
    log("\n")
    log("===[ 2/3 ] ENUMERANDO IMPRESSORAS VIA cscript (Windows Script Host - API nativa EnumPrinters)")
    log("-" * 90)
    vbs = os.path.join(SCRIPT_DIR, f"_tmp_enum_printers_{now_str}.vbs")
    try:
        with open(vbs, "w", encoding="utf-8") as f:
            f.write("On Error Resume Next\n")
            f.write("Set objWMIService = GetObject(\"winmgmts:{impersonationLevel=impersonate}!\\\\.\\root\\cimv2\")\n")
            f.write("WScript.Echo \"=== VBS WMI ===\"\n")
            f.write("Set colPrinters = objWMIService.ExecQuery(\"Select * from Win32_Printer\")\n")
            f.write("WScript.Echo \"Numero de impressoras enumeradas (VBS): \" & colPrinters.Count\n")
            f.write("For Each objPrinter in colPrinters\n")
            f.write("    WScript.Echo \"--------------------------------------------------\"\n")
            f.write("    WScript.Echo \"Nome: \" & objPrinter.Name\n")
            f.write("    WScript.Echo \"  Driver: \" & objPrinter.DriverName\n")
            f.write("    WScript.Echo \"  Fabricante: \" & objPrinter.Manufacturer\n")
            f.write("    WScript.Echo \"  Porta: \" & objPrinter.PortName\n")
            f.write("    WScript.Echo \"  DeviceID: \" & objPrinter.DeviceID\n")
            f.write("    WScript.Echo \"  Padrao: \" & objPrinter.Default\n")
            f.write("    WScript.Echo \"  Status: \" & objPrinter.Status\n")
            f.write("Next\n")
        out_vbs = run(["cscript.exe", "//Nologo", vbs])
        log(out_vbs)
    finally:
        try:
            if os.path.exists(vbs):
                os.remove(vbs)
        except Exception:
            pass

    # Mostra se o modulo USB do agente encontraria algo
    log("\n")
    log("===[ 3/3 ] SIMULANDO O MODULO NOVO usb.py DO AGENTE (importando, se possivel)")
    log("-" * 90)
    try:
        # Tenta importar o usb.py (se for executado dentro da pasta agent/print_collect/../)
        sys.path.insert(0, os.path.join(SCRIPT_DIR, "agent"))
        sys.path.insert(0, SCRIPT_DIR)
        from print_collect.usb import collect_all_usb, _collect_windows, _is_virtual_printer
        log("SUCESSO: Importou print_collect.usb (agente novo)")
        lista = collect_all_usb()
        log(f"Quantidade impressoras USB REAIS (pulou virtuais): {len(lista)}")
        if len(lista) == 0:
            log("  >>> RAZAO PROVAVEL: as impressoras instaladas foram puladas por consideradas virtuais.")
            log("  >>> Cheque acima na lista de impressoras: nome, driver, porta — provavelmente a M3170 nao tem driver instalado no Windows, ou porta estranha.")
        for p in lista:
            log(f"  * USB-OK ip_virtual={p.ip_address}  modelo={p.model}  fab={p.manufacturer}  SN={p.serial_number}  pag_total={p.pages_total}  status={p.status}")
    except Exception as e:
        log(f"(AVISO: Nao consegui importar o usb.py do agente aqui. Nao importa - temos os dados de 1/3 e 2/3 acima!) Erro: {type(e).__name__}: {e}")

    # Conclusao para Julio colar no WhatsApp
    log("\n")
    log("=" * 90)
    log("COPIE E COLE ESTE RELATORIO INTEIRO NO WHATSAPP PARA O DESENVOLVEDOR ANALISAR!")
    log("Arquivo salvo em: " + REPORT_FILE)
    log("=" * 90)

    try:
        if os.name == "nt":
            os.startfile(REPORT_FILE)  # abre automaticamente no Notepad para o Julio ver
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except KeyboardInterrupt:
        print("\nCancelado pelo usuario.")
        rc = 2
    input("\n\n=== Pressione ENTER para fechar (copie antes o relatorio acima / arquivo gerado) ===")
    sys.exit(rc)
