# Build do instalador Windows do Print Collect Agent
# Requer: Python 3.10+, pip. Winget instala Inno Setup automaticamente se necessario.

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AgentDir = Join-Path $ProjectRoot "agent"
$VenvDir = Join-Path $AgentDir ".venv"
$SpecFile = Join-Path $AgentDir "PrintCollectAgent.spec"
$IssFile = Join-Path $AgentDir "windows\PrintCollectSetup.iss"
$DistDir = Join-Path $AgentDir "dist"
$BuildDir = Join-Path $AgentDir "build"
$ExeAgent = Join-Path $DistDir "PrintCollectAgent.exe"
$RuntimeDir = Join-Path $AgentDir "windows\runtime"
$WindowsDir = Join-Path $AgentDir "windows"
$OutputSetupExe = Join-Path $DistDir "PrintCollectSetup.exe"

function Write-Step { param($n, $m) Write-Host ""; Write-Host "[$n] $m" -ForegroundColor Cyan }
function Write-OK { param($m) Write-Host "  OK  $m" -ForegroundColor Green }
function Write-Fail { param($m) Write-Host "  FAIL $m" -ForegroundColor Red }

# 1) Venv
Write-Step 1 "Verificando ambiente virtual do agente em: $VenvDir"
if (-not (Test-Path $VenvDir)) {
    $python = Get-Command python.exe -ErrorAction Stop
    Write-Host "  Criando venv com: $($python.Source)"
    & $python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar venv" }
    Write-OK "venv criado"
} else {
    Write-OK "venv ja existe"
}

$PythonVenv = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $PythonVenv)) { throw "Python do venv nao encontrado: $PythonVenv" }
$PipVenv = Join-Path $VenvDir "Scripts\pip.exe"
$PyInstaller = Join-Path $VenvDir "Scripts\pyinstaller.exe"

# 2) Dependencias agente
Write-Step 2 "Instalando dependencias do agente"
& $PipVenv install --disable-pip-version-check -r (Join-Path $AgentDir "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar requirements.txt" }

# 3) PyInstaller
Write-Step 3 "Verificando PyInstaller"
if (-not (Test-Path $PyInstaller)) {
    Write-Host "  Instalando PyInstaller..."
    & $PipVenv install --disable-pip-version-check "pyinstaller>=6.0"
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar PyInstaller" }
}
Write-OK "PyInstaller pronto em: $PyInstaller"

# 4) Build PrintCollectAgent.exe via .spec
Write-Step 4 "Buildando PrintCollectAgent.exe (isso pode levar varios minutos)"
if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force -ErrorAction SilentlyContinue }

if (-not (Test-Path $SpecFile)) { throw "Spec file nao encontrado: $SpecFile" }

Push-Location $AgentDir
try {
    & $PyInstaller --noconfirm --clean $SpecFile
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller retornou erro $LASTEXITCODE" }
} finally {
    Pop-Location
}

if (-not (Test-Path $ExeAgent)) { throw "PrintCollectAgent.exe nao gerado em $ExeAgent" }
Write-OK "Agente buildado: $ExeAgent"

# 5) Copiar PrintCollectAgent.exe + .bats do runtime para windows/
Write-Step 5 "Preparando arquivos do instalador (runtime + exe)"
$RuntimeFiles = @(
    (Join-Path $RuntimeDir "run-once.bat"),
    (Join-Path $RuntimeDir "test-agent.bat"),
    (Join-Path $RuntimeDir "open-config.bat"),
    (Join-Path $RuntimeDir "list-printers.bat"),
    (Join-Path $RuntimeDir "register-startup-task.bat"),
    (Join-Path $RuntimeDir "register-startup-task-silent.bat"),
    (Join-Path $RuntimeDir "unregister-startup-task.bat")
)
foreach ($file in $RuntimeFiles) {
    if (-not (Test-Path $file)) { throw "Arquivo runtime faltando: $file" }
    Copy-Item $file $DistDir -Force
}
Copy-Item $ExeAgent $WindowsDir -Force
foreach ($file in $RuntimeFiles) {
    Copy-Item $file $WindowsDir -Force
}
Write-OK "Arquivos copiados para $DistDir e $WindowsDir"

# 6) Inno Setup (ISCC)
Write-Step 6 "Localizando Inno Setup (ISCC.exe)"
function Find-Iscc {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 5\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 5\ISCC.exe",
        "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe",
        "${env:LOCALAPPDATA}\Programs\Inno Setup 5\ISCC.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$iscc = Find-Iscc
if (-not $iscc) {
    Write-Host "  Inno Setup nao encontrado. Tentando instalar via winget..."
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if ($winget) {
        & $winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
        Start-Sleep -Seconds 2
        $iscc = Find-Iscc
    }
}
if (-not $iscc) { throw "Nao foi possivel encontrar/instalar Inno Setup. Instale manualmente: https://jrsoftware.org/isdl.php" }
Write-OK "ISCC em: $iscc"

# 7) Gerar setup.exe
Write-Step 7 "Compilando instalador: $IssFile"
if (-not (Test-Path $IssFile)) { throw "ISS nao encontrado: $IssFile" }

& $iscc $IssFile
if ($LASTEXITCODE -ne 0) { throw "ISCC retornou erro $LASTEXITCODE" }

if (-not (Test-Path $OutputSetupExe)) {
    # Inno as vezes joga em OutputDir do .iss. Vamos procurar
    $found = Get-ChildItem (Split-Path -Parent $IssFile) -Filter "*.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*Setup*" -or $_.Name -like "*setup*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($found) {
        $OutputSetupExe = $found.FullName
    } else {
        throw "Instalador nao encontrado apos build ISCC"
    }
}

Write-Host ""
Write-Host "================ BUILD CONCLUIDO ================" -ForegroundColor Green
$file = Get-Item $OutputSetupExe
Write-Host "  Instalador : $($file.FullName)"
Write-Host "  Tamanho    : $([math]::Round($file.Length / 1MB, 1)) MB"
Write-Host "  Modificado : $($file.LastWriteTime)"
Write-Host "=================================================" -ForegroundColor Green
