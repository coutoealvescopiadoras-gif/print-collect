# ============================================================
# DIAGNOSTICO EPSON M3170 USB - SEM ERRO DE SINTAXE!
# Como usar: clique 2x nesse arquivo (ou clique direito -> Executar com PowerShell)
# Ele salva um relatorio .txt na MESMA PASTA onde esta esse script.
# ============================================================

$ErrorActionPreference = "Continue"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$reportFile = Join-Path $scriptDir "DIAGNOSTICO_EPSON_CEA_$ts.txt"

function Write-Both {
    param([string]$msg, [ConsoleColor]$color = [ConsoleColor]::White)
    Write-Host $msg -ForegroundColor $color
    try {
        Add-Content -Path $reportFile -Value $msg -Encoding UTF8
    } catch {}
}

Write-Both "========================================================================" Cyan
Write-Both " DIAGNOSTICO IMPRESSORAS USB - HORA: $((Get-Date).ToString('dd/MM/yyyy HH:mm:ss')) " Cyan
Write-Both " Relatorio salvo em: $reportFile " Cyan
Write-Both "========================================================================" Cyan

Write-Both ""
Write-Both "[1] IMPRESSORAS INSTALADAS (Win32_Printer):" Yellow
Write-Both "--------------------------------------------------------" Yellow
try {
    $printers = Get-CimInstance Win32_Printer -ErrorAction Stop
    if (-not $printers) {
        Write-Both "   >>> NENHUMA IMPRESSORA ENCONTRADA NA WMI! <<<" Red
    } else {
        foreach ($p in $printers) {
            Write-Both ("  Nome:         " + $p.Name)
            Write-Both ("    Fabricante: " + $p.Manufacturer)
            Write-Both ("    Driver:     " + $p.DriverName)
            Write-Both ("    Porta:      " + $p.PortName)
            Write-Both ("    Padrao:     " + $p.Default)
            Write-Both ("    Status:     " + $p.Status + "  |  " + $p.ExtendedPrinterStatus)
            Write-Both ("    DeviceID:   " + $p.DeviceID)
            Write-Both ""
        }
    }
} catch {
    Write-Both ("ERRO WMI Printers: " + $_.Exception.Message) Red
}

Write-Both "[2] CONTADORES DE FILAS DE IMPRESSAO (Spooler - TotalPagesPrinted):" Yellow
Write-Both "--------------------------------------------------------" Yellow
try {
    $qs = Get-CimInstance Win32_PerfFormattedData_Spooler_PrintQueue -ErrorAction Stop
    if (-not $qs) {
        Write-Both "   (sem filas retornadas - Normalmente tem pelo menos a _Total)"
    } else {
        foreach ($q in $qs) {
            Write-Both ("  Fila: [" + $q.Name + "]   TotalPagesPrinted = " + $q.TotalPagesPrinted + "   JobsSpooling = " + $q.JobsSpooling)
        }
    }
} catch {
    Write-Both ("ERRO Spooler Queues: " + $_.Exception.Message) Red
}

Write-Both ""
Write-Both "[3] DRIVERS EPSON / M3170 detectados no Windows:" Yellow
Write-Both "--------------------------------------------------------" Yellow
try {
    $drv = Get-CimInstance Win32_PrinterDriver -ErrorAction Stop | Where-Object { $_.Name -match 'Epson|M3170|3170' }
    if (-not $drv) {
        Write-Both "  (Nenhum driver com nome Epson ou M3170 encontrado)"
    } else {
        foreach ($d in $drv) {
            Write-Both ("  Driver: " + $d.Name + "   Platform: " + $d.SupportedPlatform + "   Version: " + $d.Version)
        }
    }
} catch {
    Write-Both ("ERRO Drivers: " + $_.Exception.Message) Red
}

Write-Both ""
Write-Both "[4] PASTAS DE SPOOLER (pra confirmar servico Print Spooler rodando):" Yellow
try {
    $sp = Get-Service Spooler -ErrorAction Stop
    Write-Both ("  Servico Print Spooler = Status=[" + $sp.Status + "]  StartType=[" + $sp.StartType + "]")
} catch {
    Write-Both ("  (erro ao consultar servico: " + $_.Exception.Message + ")")
}

Write-Both ""
Write-Both "========================================================================" Green
Write-Both "  >>> FIM. COPIE ESSE ARQUIVO:  $reportFile  <- E COLE NO WHATSAPP! <<<" Green
Write-Both "========================================================================" Green

# Tenta abrir automaticamente o TXT pro Julio ver
try {
    Start-Process notepad.exe -ArgumentList $reportFile
} catch {}

# Espera enter antes de fechar (para Julio nao perder a tela)
Write-Host ""
Read-Host "=== Pressione ENTER para fechar (antes salve/copie o arquivo TXT acima) ==="
