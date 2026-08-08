# Build do instalador Windows x86 (32 BITS) do Print Collect Agent
# =============================================================================
# ESTE SCRIPT GERA UM EXE COMPATIVEL COM QUALQUER WINDOWS!
#   - Roda em Windows 10/11 32 BITS (x86)
#   - Roda em Windows 10/11 64 BITS (x64) - via WOW64 (padrao, funciona sempre)
#   - Roda em Windows ARM (via emulacao x86)
#
# REQUISITO OBRIGATORIO ANTES DE RODAR ESTE SCRIPT:
#   1) Baixe e INSTALE o Python 3.12 para 32 BITS (x86):
#      Link direto: https://www.python.org/ftp/python/3.12.0/python-3.12.0.exe
#      DURANTE A INSTALACAO:
#        [X] Marque "Add python.exe to PATH"
#        [X] Clique em "Customize installation" -> "Next"
#        [X] Marque "Install for all users" (instala em: C:\Program Files (x86)\Python312-32)
#
#   2) Depois de instalar Python 32 bits, E SO DAR DUPLA CLIQUE NO ARQUIVO
#      build-setup-x86.bat (ao lado deste script) ou executar no PowerShell:
#        cd agent\windows
#        .\build-setup-x86.ps1
#
#   3) No final, o instalador estara em:
#        agent\dist\windows\PrintCollectSetup.exe (pronto para enviar!)
# =============================================================================

$ErrorActionPreference = "Stop"

# =============================================================================
# CAMINHOS CORRETOS (ajuste duro para nao depender de Split-Path -Parent errado):
#   - Este script esta em: <RAIZ DO PROJETO>\agent\windows\build-setup-x86.ps1
#   - Portanto: ProjectRoot = ..\.. (sobe 2 niveis a partir daqui)
#   -         AgentDir   = ..    (sobe 1 nivel: agent\)
# =============================================================================
$WindowsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentDir   = Split-Path -Parent $WindowsDir          # = agent\
$ProjectRoot = Split-Path -Parent $AgentDir            # = RAIZ do projeto (print-collect\)

$VenvDir = Join-Path $AgentDir ".venv-x86"
$SpecFile = Join-Path $WindowsDir "PrintCollectAgent.spec"
$IssFile = Join-Path $WindowsDir "PrintCollectSetup.iss"
$DistDir = Join-Path $AgentDir "dist"
$BuildDir = Join-Path $AgentDir "build"
$ExeAgent = Join-Path $DistDir "PrintCollectAgent.exe"
$RuntimeDir = Join-Path $WindowsDir "runtime"
$OutputSetupExe = Join-Path $DistDir "windows\PrintCollectSetup.exe"

function Write-Step { param($n, $m) Write-Host ""; Write-Host "[$n] $m" -ForegroundColor Cyan }
function Write-OK { param($m) Write-Host "  OK  $m" -ForegroundColor Green }
function Write-Fail { param($m) Write-Host "  FAIL $m" -ForegroundColor Red }
function Write-Warn { param($m) Write-Host "  WARN $m" -ForegroundColor Yellow }

# =============================================================================
# PASSO 0: Forcar TARGET_ARCH = x86 E garantir que estamos com PYTHON x86
# =============================================================================
Write-Host "============================================================" -ForegroundColor Magenta
Write-Host " PRINT COLLECT - BUILD DO AGENTE x86 (32 BITS - UNIVERSAL!)" -ForegroundColor Magenta
Write-Host "    Este exe roda em QUALQUER Windows!" -ForegroundColor Magenta
Write-Host "============================================================" -ForegroundColor Magenta

$env:TARGET_ARCH = "x86"
Write-Host ""
Write-Warn "Variavel TARGET_ARCH definida como: $env:TARGET_ARCH"

function Find-PythonX86 {
    $candidates = @(
        "C:\Program Files (x86)\Python312-32\python.exe",
        "C:\Program Files (x86)\Python311-32\python.exe",
        "C:\Program Files (x86)\Python310-32\python.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    $cmd = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        try {
            $test = & $cmd.Source -3.12-32 -c "import sys; sys.stdout.write(str(sys.maxsize > 2**32))" 2>$null
            if ($LASTEXITCODE -eq 0 -and $test -eq "False") { return $cmd.Source }
        } catch {}
        try {
            $test = & $cmd.Source -3-32 -c "import sys; sys.stdout.write(str(sys.maxsize > 2**32))" 2>$null
            if ($LASTEXITCODE -eq 0 -and $test -eq "False") { return $cmd.Source }
        } catch {}
    }
    return $null
}

$pythonX86 = Find-PythonX86
if (-not $pythonX86) {
    Write-Host ""
    Write-Fail "PYTHON 32 BITS (x86) NAO ENCONTRADO!"
    Write-Host ""
    Write-Host "  Voce precisa instalar Python 3.10+ para 32 BITS primeiro:"
    Write-Host ""
    Write-Host "  LINK DIREITO (32 bits): https://www.python.org/ftp/python/3.12.0/python-3.12.0.exe"
    Write-Host ""
    Write-Host "  Durante a instalacao, MARQUE:"
    Write-Host "       - [X] Add python.exe to PATH"
    Write-Host "       - [X] Install for all users"
    Write-Host "  4) Depois de instalar, rode NOVAMENTE este script."
    Write-Host ""
    throw "Python 32 bits nao encontrado"
}
Write-OK "Python 32 bits encontrado em: $pythonX86"
$archCheck = & $pythonX86 -c "import struct; print(struct.calcsize('P') * 8)"
if ($archCheck -ne "32") {
    throw "O Python encontrado NAO e 32 bits! (reportou arquitetura de $archCheck bits). Voce rodou o instalador de 64 bits sem querer."
}
Write-OK "Python verificado: 32 bits (x86)! Perfeito."

# =============================================================================
# PASSO 1: CRIAR .venv-x86 SEPARADO (sem tocar na .venv 64 bits)
# =============================================================================
Write-Step 1 "Verificando ambiente virtual x86 do agente em: $VenvDir"
if (-not (Test-Path $VenvDir)) {
    Write-Host "  Criando venv-x86 com: $pythonX86"
    & $pythonX86 -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "Falha ao criar venv-x86" }
    Write-OK ".venv-x86 criado"
} else {
    Write-OK ".venv-x86 ja existe"
}

$PythonVenv = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $PythonVenv)) { throw "Python do venv-x86 nao encontrado: $PythonVenv" }
$PipVenv = Join-Path $VenvDir "Scripts\pip.exe"
$PyInstaller = Join-Path $VenvDir "Scripts\pyinstaller.exe"

# =============================================================================
# PASSO 2: Instalar dependencias do agente
# OBS: agent\requirements.txt tem "-e ." na linha 1 = instala projeto local.
# Portanto o pip install TEM QUE RODAR com CWD = $AgentDir (pasta agent\) para
# o "." de "-e ." apontar para agent\ (onde tem pyproject.toml).
# =============================================================================
Write-Step 2 "Instalando dependencias do agente no .venv-x86"
Push-Location $AgentDir
try {
    & $PipVenv install --disable-pip-version-check -r (Join-Path $AgentDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar requirements.txt (x86)" }
} finally {
    Pop-Location
}

# =============================================================================
# PASSO 3: Instalar PyInstaller
# =============================================================================
Write-Step 3 "Verificando PyInstaller no .venv-x86"
if (-not (Test-Path $PyInstaller)) {
    Write-Host "  Instalando PyInstaller..."
    Push-Location $AgentDir
    try {
        & $PipVenv install --disable-pip-version-check "pyinstaller>=6.0"
        if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar PyInstaller (x86)" }
    } finally {
        Pop-Location
    }
}
Write-OK "PyInstaller x86 pronto em: $PyInstaller"

# =============================================================================
# PASSO 4: Build PrintCollectAgent.exe x86
# =============================================================================
Write-Step 4 "Buildando PrintCollectAgent.exe x86 32 bits (isso pode levar varios minutos)"
if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force -ErrorAction SilentlyContinue }

if (-not (Test-Path $SpecFile)) { throw "Spec file nao encontrado: $SpecFile" }

Push-Location $AgentDir
try {
    & $PyInstaller --noconfirm --clean (Resolve-Path $SpecFile)
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller (x86) retornou erro $LASTEXITCODE" }
} finally {
    Pop-Location
}

if (-not (Test-Path $ExeAgent)) { throw "PrintCollectAgent.exe x86 nao gerado em $ExeAgent" }
Write-OK "Agente x86 buildado: $ExeAgent"

# =============================================================================
# PASSO 4.5: Build WizardPareamento.exe x86 (EXECUTAVEL NATIVO! nao usa .bat!)
# (PyInstaller --onefile --console — mesma arquitetura x86 32 bits)
# =============================================================================
Write-Step "4.5" "Buildando WizardPareamento.exe x86 32 bits (novo! nativo, sem .bat)"
$WizardPy = Join-Path $AgentDir "WizardPareamento.py"
$ExeWizard = Join-Path $DistDir "WizardPareamento.exe"
if (-not (Test-Path $WizardPy)) { throw "WizardPareamento.py nao encontrado em: $WizardPy" }

Push-Location $AgentDir
try {
    & $PyInstaller --noconfirm --clean --onefile --console --name "WizardPareamento" $WizardPy
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller WizardPareamento (x86) retornou erro $LASTEXITCODE" }
} finally {
    Pop-Location
}
if (-not (Test-Path $ExeWizard)) { throw "WizardPareamento.exe x86 nao gerado em $ExeWizard" }
Write-OK "WizardPareamento.exe x86 buildado: $ExeWizard"

# =============================================================================
# PASSO 4.6: Build SearchPrinters.exe x86 (EXECUTAVEL NATIVO! Busca impressoras, NAO FECHA SOZINHO!)
# (PyInstaller --onefile --console — mesma arquitetura x86 32 bits)
# =============================================================================
Write-Step "4.6" "Buildando SearchPrinters.exe x86 32 bits (novo! nativo, busca impressoras, nao fecha!)"
$SearchPy = Join-Path $AgentDir "SearchPrinters.py"
$ExeSearch = Join-Path $DistDir "SearchPrinters.exe"
if (-not (Test-Path $SearchPy)) { throw "SearchPrinters.py nao encontrado em: $SearchPy" }

Push-Location $AgentDir
try {
    & $PyInstaller --noconfirm --clean --onefile --console --name "SearchPrinters" $SearchPy
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller SearchPrinters (x86) retornou erro $LASTEXITCODE" }
} finally {
    Pop-Location
}
if (-not (Test-Path $ExeSearch)) { throw "SearchPrinters.exe x86 nao gerado em $ExeSearch" }
Write-OK "SearchPrinters.exe x86 buildado: $ExeSearch"

# =============================================================================
# PASSO 5: Copiar runtime + exe para windows/dist
# =============================================================================
Write-Step 5 "Preparando arquivos do instalador (runtime + exe + wizard nativo + search nativo)"
$RuntimeFiles = @(
    (Join-Path $RuntimeDir "run-once.bat"),
    (Join-Path $RuntimeDir "test-agent.bat"),
    (Join-Path $RuntimeDir "open-config.bat"),
    (Join-Path $RuntimeDir "list-printers.bat"),
    (Join-Path $RuntimeDir "register-startup-task.bat"),
    (Join-Path $RuntimeDir "register-startup-task-silent.bat"),
    (Join-Path $RuntimeDir "unregister-startup-task.bat"),
    (Join-Path $RuntimeDir "run-wizard.bat")
)
foreach ($file in $RuntimeFiles) {
    if (-not (Test-Path $file)) { throw "Arquivo runtime faltando: $file" }
    Copy-Item $file $DistDir -Force
}
# Copia os 3 executaveis principais (agente + wizard nativo + search nativo)
# CORRECAO BUG SELF-COPY: Se $ExeAgent ja ESTA em $DistDir (Join-Path mesmo) Copy-Item daria
# erro "Nao pode substituir item por ele mesmo". Pulamos se SourcePath == DestinationPath.
$copyExeAgentDest = Join-Path $DistDir (Split-Path -Leaf $ExeAgent)
if ([string]$ExeAgent -ne [string]$copyExeAgentDest) { Copy-Item $ExeAgent $DistDir -Force }
$copyExeWizardDest = Join-Path $DistDir (Split-Path -Leaf $ExeWizard)
if ([string]$ExeWizard -ne [string]$copyExeWizardDest) { Copy-Item $ExeWizard $DistDir -Force }
$copyExeSearchDest = Join-Path $DistDir (Split-Path -Leaf $ExeSearch)
if ([string]$ExeSearch -ne [string]$copyExeSearchDest) { Copy-Item $ExeSearch $DistDir -Force }
# Tambem copia para agent\windows\ (para testes locais rapidos) - esses SAO pastas diferentes, sempre OK!
Copy-Item $ExeAgent $WindowsDir -Force
Copy-Item $ExeWizard $WindowsDir -Force
Copy-Item $ExeSearch $WindowsDir -Force
foreach ($file in $RuntimeFiles) {
    Copy-Item $file $WindowsDir -Force
}
Write-OK "Arquivos copiados para $DistDir e $WindowsDir"

# =============================================================================
# PASSO 6: Inno Setup
# =============================================================================
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

# =============================================================================
# PASSO 7: Gerar setup.exe
# =============================================================================
Write-Step 7 "Compilando instalador: $IssFile"
if (-not (Test-Path $IssFile)) { throw "ISS nao encontrado: $IssFile" }

& $iscc $IssFile
if ($LASTEXITCODE -ne 0) { throw "ISCC retornou erro $LASTEXITCODE" }

if (-not (Test-Path $OutputSetupExe)) {
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
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  BUILD x86 (32 BITS) CONCLUIDO COM SUCESSO!" -ForegroundColor Green
Write-Host "     -> RODA EM QUALQUER WINDOWS (32/64 bits, ARM!)" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
$file = Get-Item $OutputSetupExe
Write-Host "  Instalador : $($file.FullName)"
Write-Host "  Tamanho    : $([math]::Round($file.Length / 1MB, 1)) MB"
Write-Host "  Modificado : $($file.LastWriteTime)"
Write-Host ""
Write-Host "   PROXIMO PASSO (Julio):"
Write-Host "   1) Copiar esse arquivo para a pasta web\public\ para subir no site oficial:"
$dest = Join-Path $ProjectRoot "web\public\PrintCollectSetup.exe"
Write-Host "      Copy-Item '$($file.FullName)' '$dest' -Force"
Write-Host "   2) Depois, na pasta raiz do projeto, rodar:"
Write-Host "      git add web/public/PrintCollectSetup.exe"
Write-Host "      git commit -m 'release(instalador): rebuild x86 32 bits' "
Write-Host "      git push origin main"
Write-Host "   3) Apos ~2 min deploy Vercel, todos os clientes baixarao a versao nova."
Write-Host "============================================================" -ForegroundColor Green
