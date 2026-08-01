#Requires -RunAsAdministrator
# Instala o coletor Print Collect no Windows
$InstallDir = if ($env:PRINT_COLLECT_DIR) { $env:PRINT_COLLECT_DIR } else { "C:\PrintCollect" }
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonCmd = if (Get-Command py -ErrorAction SilentlyContinue) { "py -3" } elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { $null }

Write-Host "=== Print Collect Agent - Instalacao ===" -ForegroundColor Cyan
Write-Host "Diretorio: $InstallDir"

if (-not $PythonCmd) {
    Write-Host ""
    Write-Host "Python 3.10+ nao encontrado neste computador." -ForegroundColor Red
    Write-Host "Use o instalador standalone (PrintCollectSetup.exe) quando disponivel," -ForegroundColor Yellow
    Write-Host "ou instale Python 3.10+ para usar este pacote PowerShell." -ForegroundColor Yellow
    exit 1
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Recurse -Force "$ScriptDir\print_collect" "$InstallDir\"
Copy-Item -Force "$ScriptDir\pyproject.toml" "$InstallDir\"
if (Test-Path "$ScriptDir\requirements.txt") {
    Copy-Item -Force "$ScriptDir\requirements.txt" "$InstallDir\"
}
if (-not (Test-Path "$InstallDir\config.yaml")) {
    if (Test-Path "$ScriptDir\config.yaml") {
        Copy-Item "$ScriptDir\config.yaml" "$InstallDir\config.yaml"
    } elseif (Test-Path "$ScriptDir\config.example.yaml") {
        Copy-Item "$ScriptDir\config.example.yaml" "$InstallDir\config.yaml"
    }
}

Set-Location $InstallDir
Invoke-Expression "$PythonCmd -m venv .venv"
& "$InstallDir\.venv\Scripts\pip.exe" install -q --upgrade pip
if (Test-Path "$InstallDir\requirements.txt") {
    & "$InstallDir\.venv\Scripts\pip.exe" install -q -r "$InstallDir\requirements.txt"
}
& "$InstallDir\.venv\Scripts\pip.exe" install -q .

Write-Host ""
Write-Host "Instalacao concluida!" -ForegroundColor Green
Write-Host ""
Write-Host "Proximos passos:"
Write-Host "  1. Edite $InstallDir\config.yaml"
Write-Host "  2. $InstallDir\.venv\Scripts\print-collect.exe --test"
Write-Host "  3. $InstallDir\.venv\Scripts\print-collect.exe --once"
Write-Host ""
Write-Host "Para rodar como servico, use o Agendador de Tarefas do Windows"
Write-Host "com acao: $InstallDir\.venv\Scripts\print-collect.exe"
Write-Host ""
