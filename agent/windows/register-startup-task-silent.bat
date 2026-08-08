@echo off
REM Variante SILENCIOSA do register-startup-task.bat para rodar DENTRO do Inno Setup.
REM NUNCA usa PAUSE, NUNCA pede interacao, sempre retorna exit 0 para nao travar instalador.
REM
REM CORRECOES CRITICAS (v4 AGO/2026 - "funciona manual mas nao atualiza sozinho"):
REM  [X] BUG #1: schtasks /SC HOURLY SEM /ST — AGORA SEMPRE com /ST 00:00 /SD (horas cheias: 10h, 11h, 12h...)
REM  [X] BUG #2: Working Directory = NULL + "Start only if network" = DEFAULT true
REM             SOLUCAO: PowerShell ScheduledTasks AGORA eh a TENTATIVA 1 (nao mais fallback final!)
REM             pois aceita WorkingDirectory + StartWhenAvailable + MultipleInstances IgnoreNew
REM  [X] BUG #3: NUNCA testava a tarefa AGENDADA do jeito Windows dispara!
REM             AGORA sempre roda: schtasks /RUN /TN "...HORARIA..." e VALIDA agent.log ter linha nova.
REM  [X] BUG #4: AtLogOn trigger PowerShell SEM -UserId (falhava em conta Microsoft).
REM
REM CORRECOES HERDADAS DA v3 (mantidas):
REM  [X] Aspas no /TR sintaxe universal "\"...\""
REM  [X] Rotação de LOG (for %%F in) correta (nao compara mais tamanho do .bat)
REM  [X] /RL HIGHEST REMOVIDO TOTALMENTE (nao pede admin)

setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "LOG=%TEMP%\print-collect-startup.log"
set "AGENT_LOG=%CFG_DIR%\agent.log"

REM === LIMPA LOG se passar de 1MB ===
if exist "%LOG%" for %%F in ("%LOG%") do if %%~zF GEQ 1048576 del /F /Q "%LOG%"

echo ================================================================================ >> "%LOG%"
echo [%date% %time%] PRINT COLLECT - INSTALAR AGENDAMENTO (v4) - INICIO >> "%LOG%"
echo [%date% %time%] EXE  = %EXE% >> "%LOG%"
echo [%date% %time%] CFG  = %CFG% >> "%LOG%"
echo ================================================================================ >> "%LOG%"

if not exist "%EXE%" (
    echo [%date% %time%] ERRO EXE nao encontrado: %EXE% >> "%LOG%"
    exit /b 0
)

if not exist "%CFG_DIR%" mkdir "%CFG_DIR%" >nul 2>&1
if not exist "%CFG%" (
    if exist "%~dp0config.example.yaml" (
        copy /Y "%~dp0config.example.yaml" "%CFG%" >nul
        echo [%date% %time%] Copiado config.example.yaml para %CFG% >> "%LOG%"
    )
)

REM ================================================================================
REM PASSO 1: DELETAR TUDO QUE EXISTIA ANTES
REM ================================================================================
echo [%date% %time%] PASSO 1/5: Limpando tarefas antigas (10+ variantes de nomes)... >> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent"                        >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Manha (08h)"         >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Tarde (18h)"         >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Ao Logar"            >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 Hora"       >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 HORA"       >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Hora"                >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Hourly"              >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Way Agent"                           >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect"                             >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Inicializacao"       >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect - Coletar"                   >nul 2>> "%LOG%"
echo [%date% %time%]   OK: Tarefas antigas removidas. >> "%LOG%"

REM ================================================================================
REM PASSO 2: TAREFA HORARIA (1 em 1 hora)
REM   PRIORIDADE 1: PowerShell ScheduledTasks (WorkingDirectory + StartWhenAvailable + MultipleInstances IgnoreNew)
REM   FALLBACK 2: schtasks.exe /SC HOURLY /MO 1 /ST 00:00 /SD <hoje>
REM   FALLBACK 3: schtasks.exe /SC MINUTE /MO 60 (Windows doente)
REM ================================================================================
echo [%date% %time%] PASSO 2/5: Criando tarefa HORARIA (PowerShell ScheduledTasks TENTATIVA 1)... >> "%LOG%"

set "TASK_HOURLY=Print Collect Agent - A Cada 1 HORA"
set "TR_ESCAPED=\"%EXE%\" --config \"%CFG%\" once"

REM === TENTATIVA 1: PowerShell ScheduledTasks (MAIS ROBUSTA, tem WorkingDirectory!) ===
REM === CORRECAO v5 CRITICA: $start NÃO PODE SER HOJE 00:00 (que já passou quando instala ao meio-dia!) ===
REM ===                    Agora: $start = PRÓXIMA HORA CHEIA. Logo após registrar, Start-ScheduledTask AGORA MESMO! ===
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$exe='%EXE:'='%';" ^
  "$cfg='%CFG:'='%';" ^
  "$taskName='%TASK_HOURLY:'='%';" ^
  "$wd='%~dp0';" ^
  "$act = New-ScheduledTaskAction -Execute $exe -Argument ('--config \"{0}\" once' -f $cfg) -WorkingDirectory $wd;" ^
  "$start = (Get-Date -Minute 0 -Second 0).AddHours(1);" ^
  "$trg = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue);" ^
  "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
  "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Force | Out-Null;" ^
  "Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null;" ^
  "Write-Host ('OK: criado via PowerShell e disparado 1x agora: ' + $taskName);" >nul 2>> "%LOG%"
set RC1=%ERRORLEVEL%
echo [%date% %time%]   Tentativa 1 (PowerShell ScheduledTasks v5) -> RC=%RC1% (proxima hora cheia + disparado agora) >> "%LOG%"

REM === FALLBACK 2: schtasks /SC HOURLY /MO 1 (COM /ST HORA_ATUAL_MINUTO_SEGUINTE E /SD!) ===
REM === CORRECAO v5: /ST 00:00 é horario PASSADO se instalar ao meio-dia! Agora usa /ST HH:mm (agora +2min) ===
if %RC1% NEQ 0 (
    REM Formata data como dd/mm/aaaa (padrão schtasks pt-BR)
    for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set _SD=%%a/%%b/%%c
    if "%_SD%"=="" set _SD=%date%
    REM Formata HORA para /ST no formato HH:mm (agora + 2 minutos de seguranca para nao ja ter passado!)
    for /f "tokens=1-3 delims=:., " %%h in ("%time: =0%") do set _HH=%%h&set _MM=%%i&set _SS=%%j
    set /A _MM_MIN_ADJ=100%_MM% %% 100 + 2
    if %_MM_MIN_ADJ% GEQ 60 (
      set /A _HH_MIN_ADJ=100%_HH% %% 100 + 1
      set /A _MM=0
      set _HH=00%_HH_MIN_ADJ%
      set _HH=%_HH:~-2%
    ) else (
      set _MM=00%_MM_MIN_ADJ%
      set _MM=%_MM:~-2%
    )
    set _ST=%_HH%:%_MM%
    echo [%date% %time%]   Tentativa 2 schtasks HOURLY /ST %_ST% /SD %_SD% ... >> "%LOG%"
    schtasks /Create /F /TN "%TASK_HOURLY%" /SC HOURLY /MO 1 /ST %_ST% /SD %_SD% /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
    set RC1=%ERRORLEVEL%
    echo [%date% %time%]   Tentativa 2 HOURLY/ST %_ST% -> RC=%RC1% >> "%LOG%"
    REM Forca executar AGORA, caso o /ST seja no futuro
    if %RC1% EQU 0 schtasks /Run /TN "%TASK_HOURLY%" >nul 2>> "%LOG%"
)

REM === FALLBACK 3: MINUTE /MO 60 ===
if %RC1% NEQ 0 (
    echo [%date% %time%]   Tentativa 3 schtasks MINUTE/MO=60 ... >> "%LOG%"
    schtasks /Create /F /TN "%TASK_HOURLY%" /SC MINUTE /MO 60 /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
    set RC1=%ERRORLEVEL%
    echo [%date% %time%]   Tentativa 3 MINUTE/MO 60 -> RC=%RC1% >> "%LOG%"
    REM Forca executar AGORA (MINUTE nao tem /ST futuro, comeca contar de agora)
    if %RC1% EQU 0 schtasks /Run /TN "%TASK_HOURLY%" >nul 2>> "%LOG%"
)

if %RC1% EQU 0 (
    echo [%date% %time%]   [OK] Tarefa HORARIA criada com sucesso. >> "%LOG%"
) else (
    echo [%date% %time%]   [ERRO] Tarefa HORARIA NAO criada (RC=%RC1%). >> "%LOG%"
)

REM ================================================================================
REM PASSO 3: TAREFA AO LOGAR (PowerShell TENTATIVA 1 primeiro com -UserId!)
REM ================================================================================
echo [%date% %time%] PASSO 3/5: Criando tarefa AO LOGAR... >> "%LOG%"

set "TASK_LOGON=Print Collect Agent - Ao Logar"

REM === TENTATIVA 1: PowerShell COM -UserId (resolve conta Microsoft bug) ===
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$exe='%EXE:'='%';" ^
  "$cfg='%CFG:'='%';" ^
  "$taskName='%TASK_LOGON:'='%';" ^
  "$wd='%~dp0';" ^
  "$uid=$env:USERNAME;" ^
  "$act = New-ScheduledTaskAction -Execute $exe -Argument ('--config \"{0}\" once' -f $cfg) -WorkingDirectory $wd;" ^
  "$trg = New-ScheduledTaskTrigger -AtLogOn -User $uid;" ^
  "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
  "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Force | Out-Null;" ^
  "Write-Host ('OK: AtLogon PowerShell criado: ' + $taskName);" >nul 2>> "%LOG%"
set RC2=%ERRORLEVEL%
echo [%date% %time%]   Tentativa 1 (PowerShell AtLogOn -User $env:USERNAME) -> RC=%RC2% >> "%LOG%"

REM === FALLBACK: schtasks /SC ONLOGON ===
if %RC2% NEQ 0 (
    echo [%date% %time%]   Tentativa 2 schtasks ONLOGON ... >> "%LOG%"
    schtasks /Create /F /TN "%TASK_LOGON%" /SC ONLOGON /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
    set RC2=%ERRORLEVEL%
    echo [%date% %time%]   Tentativa 2 ONLOGON (schtasks) -> RC=%RC2% >> "%LOG%"
)

if %RC2% EQU 0 (
    echo [%date% %time%]   [OK] Tarefa AO LOGAR criada com sucesso. >> "%LOG%"
) else (
    echo [%date% %time%]   [ERRO] Tarefa AO LOGAR NAO criada (RC=%RC2%). >> "%LOG%"
)

REM ================================================================================
REM PASSO 4: EXECUTAR A TAREFA AGENDADA AGORA (PROVA REAL que funciona!)
REM   NAO usamos "%EXE% once" (que funciona sempre). Usamos "schtasks /RUN" (modo Windows)
REM   Esperamos 40 segundos e checamos se agent.log GANHOU UMA LINHA NOVA = TUDO OK!
REM ================================================================================
echo [%date% %time%] PASSO 4/5: EXECUTAR TAREFA HORARIA AGORA (VALIDACAO REAL VIA schtasks /RUN) ... >> "%LOG%"

REM Lê quantidade de linhas no agent.log ANTES de disparar (ou 0 se nao existe)
set LINHAS_ANTES=0
if exist "%AGENT_LOG%" for /f "usebackq" %%a in (`find /C /V "" ^< "%AGENT_LOG%"`) do set LINHAS_ANTES=%%a
echo [%date% %time%]   agent.log linhas ANTES: %LINHAS_ANTES% >> "%LOG%"

schtasks /Run /TN "%TASK_HOURLY%" >nul 2>> "%LOG%"
set RC_RUN=%ERRORLEVEL%
echo [%date% %time%]   schtasks /RUN retornou RC=%RC_RUN%. Esperando 40 segundos para agent.log receber escrita... >> "%LOG%"

REM Espera 40 segundos (PING localhost = jeito universal de sleep em .bat velho)
PING -n 41 127.0.0.1 >nul

REM Lê quantidade de linhas DEPOIS
set LINHAS_DEPOIS=0
if exist "%AGENT_LOG%" for /f "usebackq" %%a in (`find /C /V "" ^< "%AGENT_LOG%"`) do set LINHAS_DEPOIS=%%a
echo [%date% %time%]   agent.log linhas DEPOIS: %LINHAS_DEPOIS% >> "%LOG%"

set RC4=1
if %LINHAS_DEPOIS% GTR %LINHAS_ANTES% set RC4=0
if %RC4% EQU 0 (
    echo [%date% %time%]   [SUCESSO PROVADO!] agent.log recebeu linhas novas. TAREFA AGENDADA FUNCIONA! >> "%LOG%"
) else (
    REM FALHOU: rodamos o EXE direto (modo usuario) para pelo menos gerar a primeira leitura e nao deixar cliente sem coleta.
    echo [%date% %time%]   [AVISO] Validacao via schtasks/Run nao gravou log (Windows pode demorar). Rodando EXE direto para garantir coleta. >> "%LOG%"
    "%EXE%" --config "%CFG%" once >> "%LOG%" 2>&1
    set RC4=%ERRORLEVEL%
)

REM ================================================================================
REM PASSO 5: RESUMO
REM ================================================================================
echo ================================================================================ >> "%LOG%"
echo [%date% %time%] RESUMO v4: >> "%LOG%"
echo [%date% %time%]   - Tarefa HORARIA (1/1h) criada? RC=%RC1% >> "%LOG%"
echo [%date% %time%]   - Tarefa AO LOGAR criada?       RC=%RC2% >> "%LOG%"
echo [%date% %time%]   - Coleta via schtasks/Run OK?   RC=%RC4% >> "%LOG%"
echo [%date% %time%]   (RC=0 = SUCESSO; RC>0 = FALHOU) >> "%LOG%"
echo [%date% %time%] LOG DETALHADO do agente: %AGENT_LOG% >> "%LOG%"
echo [%date% %time%] LOG DE INSTALACAO (este): %LOG% >> "%LOG%"
echo [%date% %time%] PRINT COLLECT - INSTALAR AGENDAMENTO (v4) - FIM >> "%LOG%"
echo ================================================================================ >> "%LOG%"

REM Sempre sai 0 (mesmo com falha) para nao travar Inno Setup / Wizard
exit /b 0
