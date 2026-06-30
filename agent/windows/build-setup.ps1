$ErrorActionPreference = "Stop"

if ([System.Environment]::OSVersion.Platform -ne [System.PlatformID]::Win32NT) {
    throw "Este script deve ser executado no Windows."
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentRoot = Split-Path -Parent $ScriptDir
$BuildRoot = Join-Path $AgentRoot "build\windows"
$DistRoot = Join-Path $AgentRoot "dist\windows"
$WorkRoot = Join-Path $BuildRoot "pyinstaller"
$SpecPath = Join-Path $ScriptDir "PrintCollectAgent.spec"
$IssPath = Join-Path $ScriptDir "PrintCollectSetup.iss"
$VenvPath = Join-Path $BuildRoot ".venv"

New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
New-Item -ItemType Directory -Force -Path $DistRoot | Out-Null
New-Item -ItemType Directory -Force -Path $WorkRoot | Out-Null

if (-not (Test-Path $VenvPath)) {
    $PythonBootstrap = @(
        (Get-Command py -ErrorAction SilentlyContinue),
        (Get-Command python -ErrorAction SilentlyContinue)
    ) | Where-Object { $_ } | Select-Object -First 1

    if (-not $PythonBootstrap) {
        throw "Python 3 nao encontrado. Instale Python 3.10+ e tente novamente."
    }

    if ($PythonBootstrap.Name -eq "py") {
        & py -3 -m venv $VenvPath
    }
    else {
        & python -m venv $VenvPath
    }
}

$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "Nao foi possivel localizar o Python da venv de build."
}

& $PythonExe -m pip install --upgrade pip setuptools wheel
& $PythonExe -m pip install -r (Join-Path $AgentRoot "requirements.txt")
& $PythonExe -m pip install pyinstaller

$PyprojectPath = Join-Path $AgentRoot "pyproject.toml"
$PyprojectText = Get-Content $PyprojectPath -Raw
$VersionMatch = [regex]::Match($PyprojectText, 'version\s*=\s*"([^"]+)"')

if (-not $VersionMatch.Success) {
    throw "Nao foi possivel determinar a versao do agente."
}

$Version = $VersionMatch.Groups[1].Value.Trim()

Write-Host "Gerando executavel PyInstaller v$Version..." -ForegroundColor Cyan
& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $DistRoot `
    --workpath $WorkRoot `
    $SpecPath

$AgentExePath = Join-Path $DistRoot "PrintCollectAgent.exe"
if (-not (Test-Path $AgentExePath)) {
    throw "O executavel do agente nao foi gerado em $AgentExePath."
}

$InnoCompiler = @(
    $env:INNO_SETUP_COMPILER,
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

if (-not $InnoCompiler) {
    throw "ISCC.exe nao encontrado. Instale o Inno Setup 6 ou defina INNO_SETUP_COMPILER."
}

Write-Host "Gerando instalador Inno Setup..." -ForegroundColor Cyan
& $InnoCompiler "/DMyAppVersion=$Version" $IssPath

$SetupPath = Join-Path $DistRoot "PrintCollectSetup.exe"
if (-not (Test-Path $SetupPath)) {
    throw "O instalador nao foi gerado em $SetupPath."
}

Write-Host ""
Write-Host "Build concluido com sucesso." -ForegroundColor Green
Write-Host "Executavel: $AgentExePath"
Write-Host "Instalador:  $SetupPath"
