#Requires -RunAsAdministrator
# Instala o coletor Print Collect no Windows
$InstallDir = if ($env:PRINT_COLLECT_DIR) { $env:PRINT_COLLECT_DIR } else { "C:\PrintCollect" }
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "=== Print Collect Agent - Instalacao ===" -ForegroundColor Cyan
Write-Host "Diretorio: $InstallDir"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Copy-Item -Recurse -Force "$ScriptDir\print_collect" "$InstallDir\"
Copy-Item -Force "$ScriptDir\pyproject.toml" "$InstallDir\"
if (-not (Test-Path "$InstallDir\config.yaml")) {
    Copy-Item "$ScriptDir\config.example.yaml" "$InstallDir\config.yaml"
}

Set-Location $InstallDir
python -m venv .venv
& "$InstallDir\.venv\Scripts\pip.exe" install -q --upgrade pip
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
