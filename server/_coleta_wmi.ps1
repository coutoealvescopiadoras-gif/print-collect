$ErrorActionPreference = 'Continue'
$saida = "C:\Users\Julio\Desktop\print-collect\server\_saida_wmi.txt"
Remove-Item -Path $saida -ErrorAction SilentlyContinue

Add-Content -Path $saida -Value "========================================================================"
Add-Content -Path $saida -Value "IMPRESSORAS WIN32_PRINTER (instaladas no Windows)"
Add-Content -Path $saida -Value "========================================================================"
$printers = Get-CimInstance -ClassName Win32_Printer -ErrorAction SilentlyContinue
if (-not $printers) {
    Add-Content -Path $saida -Value "(nenhuma impressora instalada retornada pelo WMI)"
} else {
    foreach ($p in $printers) {
        Add-Content -Path $saida -Value "---"
        Add-Content -Path $saida -Value ("Nome: " + $p.Name)
        Add-Content -Path $saida -Value ("Fabricante: " + $p.Manufacturer)
        Add-Content -Path $saida -Value ("Driver: " + $p.DriverName)
        Add-Content -Path $saida -Value ("Porta: " + $p.PortName)
        Add-Content -Path $saida -Value ("Padrao: " + $p.Default)
        Add-Content -Path $saida -Value ("Status: " + $p.Status)
    }
}

Add-Content -Path $saida -Value ""
Add-Content -Path $saida -Value "========================================================================"
Add-Content -Path $saida -Value "FILAS DE IMPRESSAO (contadores TotalPagesPrinted)"
Add-Content -Path $saida -Value "========================================================================"
$queues = Get-CimInstance -ClassName Win32_PerfFormattedData_Spooler_PrintQueue -ErrorAction SilentlyContinue
if (-not $queues) {
    Add-Content -Path $saida -Value "(nenhuma fila retornada)"
} else {
    foreach ($q in $queues) {
        Add-Content -Path $saida -Value ("Fila: '" + $q.Name + "' PaginasTotal=" + $q.TotalPagesPrinted + "  JobsTotal=" + $q.TotalJobsPrinted)
    }
}
Add-Content -Path $saida -Value ""
Add-Content -Path $saida -Value "FIM."
Write-Host "OK, saida salva em $saida"
