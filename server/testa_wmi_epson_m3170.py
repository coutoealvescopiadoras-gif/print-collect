"""Script de TESTE 100% SEGURO - nao altera nada no agente existente!
Apenas LE os dados das impressoras INSTALADAS NO WINDOWS (USB, WiFi, compartilhada, etc)
via WMI/CIM nativo do Windows. Nao precisa de nenhuma dependencia extra!
"""
from __future__ import annotations
import subprocess
import json
import platform
import sys
import re
from pathlib import Path

SAO_PAULO = -3  # UTC-3

# ---------------------------------------------------------------------------
# Metodo 1: Powershell NATIVO (Get-CimInstance) - NAO PRECISA DE NENHUMA LIB!
# ---------------------------------------------------------------------------
def run_powershell(cmd: str) -> str:
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", cmd],
            capture_output=True, text=True, timeout=45,
            encoding="utf-8", errors="replace",
        )
        return (proc.stdout or "") + ("\nSTDERR: " + proc.stderr if proc.stderr else "")
    except Exception as e:
        return f"ERRO powershell: {e}"

def get_printers_via_powershell() -> list[dict]:
    """Retorna lista de dicts com dados das impressoras locais."""
    ps_cmd = r"""
$ErrorActionPreference = 'Stop'
$printers = Get-CimInstance -ClassName Win32_Printer | Select-Object Name,DriverName,Manufacturer,PortName,DeviceID,Status,ExtendedPrinterStatus,Location,Comment,Default | ConvertTo-Json -Depth 3 -Compress
Write-Output "PRINTERS_JSON_BEGIN$($printers)PRINTERS_JSON_END"

# Tenta pegar contadores de pagina do spooler (por fila de impressao)
try {
    $queues = Get-CimInstance -ClassName Win32_PerfFormattedData_Spooler_PrintQueue | Select-Object Name,TotalPagesPrinted,TotalJobsPrinted | ConvertTo-Json -Depth 3 -Compress
    Write-Output "QUEUES_JSON_BEGIN$($queues)QUEUES_JSON_END"
} catch {
    Write-Output "QUEUES_JSON_BEGIN[]QUEUES_JSON_END"
}
"""
    txt = run_powershell(ps_cmd)

    # parse printers
    out: list[dict] = []
    m_pr = re.search(r"PRINTERS_JSON_BEGIN(.*?)PRINTERS_JSON_END", txt, re.S)
    if m_pr:
        try:
            data = json.loads(m_pr.group(1))
            if isinstance(data, dict):
                data = [data]
            if isinstance(data, list):
                for p in data:
                    out.append({
                        "name": p.get("Name") or "",
                        "driver": p.get("DriverName") or "",
                        "manufacturer": p.get("Manufacturer") or "",
                        "port": p.get("PortName") or "",
                        "device_id": p.get("DeviceID") or "",
                        "status": str(p.get("Status") or "Unknown"),
                        "extended_status": str(p.get("ExtendedPrinterStatus") or ""),
                        "default": bool(p.get("Default")),
                    })
        except Exception:
            pass

    # parse queues (contadores) - junta com as impressoras por nome
    m_qu = re.search(r"QUEUES_JSON_BEGIN(.*?)QUEUES_JSON_END", txt, re.S)
    queues_map: dict[str, int] = {}
    if m_qu:
        try:
            qdata = json.loads(m_qu.group(1))
            if isinstance(qdata, dict):
                qdata = [qdata]
            for q in (qdata or []):
                qname = str(q.get("Name") or "").strip()
                pages = q.get("TotalPagesPrinted")
                try:
                    pages_int = int(pages) if pages is not None else 0
                except Exception:
                    pages_int = 0
                if qname and pages_int >= 0:
                    queues_map[qname] = pages_int
        except Exception:
            pass

    # junta
    for p in out:
        nome = (p.get("name") or "").strip()
        if nome and nome in queues_map:
            p["pages_total"] = queues_map[nome]
        else:
            p["pages_total"] = None
    return out


def main() -> None:
    print("=" * 90)
    print("TESTE WMI / CIM - IMPRESSORAS INSTALADAS NO WINDOWS (USB, WiFi, Compartilhada, LPT)")
    print("=" * 90)
    print(f"Sistema: {platform.system()} {platform.release()}")
    print(f"Arquitetura Python: {platform.machine()}")
    print()

    if platform.system().lower() != "windows":
        print("AVISO: Esse teste só funciona no Windows (WMI/CIM nativo).")
        sys.exit(0)

    lista = get_printers_via_powershell()
    print(f">>> Encontradas {len(lista)} impressoras instaladas no Windows")
    print()

    alvo = "m3170"  # Epson M3170, busca case-insensitive
    achou_alvo = False
    for i, p in enumerate(lista, 1):
        nome = (p.get("name") or "")
        fabricante = (p.get("manufacturer") or "")
        driver = (p.get("driver") or "")
        match_alvo = (alvo in nome.lower()) or (alvo in driver.lower())
        prefixo = f"[{i:>2}] "
        if match_alvo:
            prefixo = f"[{i:>2}] 👉🎯 EPSON M3170 ENCONTRADA!!! "
            achou_alvo = True
        print(prefixo + "-" * 88)
        print(f"    Nome impressora:     {nome}")
        print(f"    Driver:              {driver}")
        print(f"    Fabricante:          {fabricante}")
        print(f"    Porta (USB/IP/LPT):  {p.get('port')}")
        print(f"    DeviceID:            {p.get('device_id')}")
        print(f"    Padrão do Windows:   {'SIM' if p.get('default') else 'nao'}")
        print(f"    Status:              {p.get('status')} {p.get('extended_status')}")
        print(f"    Paginas (contador spooler TotalPagesPrinted): {p.get('pages_total')}")
        print()

    if achou_alvo:
        print("=" * 90)
        print("🎊🎊🎊 EPSON M3170 FOI ENCONTRADA NA LISTA DO WINDOWS! 🎊🎊🎊")
        print("  => Agora a gente consegue pegar os dados dela via USB/WMI!")
        print("=" * 90)
    else:
        print("⚠️  Epson M3170 NAO apareceu na lista. Possiveis causas:")
        print("   1. O driver da impressora NAO esta instalado no Windows")
        print("   2. Ela esta conectada em OUTRO PC (nao no que esta rodando o agente)")
        print("   3. Nome do driver/modelo diferente (ex: 'Epson EcoTank M3170 Series' etc)")
        print("   4. USB nao plugado, impressora desligada")
        print()
        print("A lista acima mostra TODAS as impressoras que o Windows consegue ver.")
        print("Verifique se a M3170 aparece com outro nome no topo.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelado.")
        sys.exit(2)
