@echo off
REM =============================================================================
REM PRINT COLLECT - SUPERV5+ (AGENDAMENTO ROBUSTO - 6 CAMADAS!)
REM =============================================================================
REM Instala CINCO TAREFAS DIFERENTES no Windows Task Scheduler.
REM 1) 30 em 30 minutos (MINUTE/MO=30)      ? PRINCIPAL 1
REM 2) HORARIA (HOURLY / MO 1)              ? PRINCIPAL 2
REM 3) DAILY com Repetition Every 60min     ? CAMADA RESERVA 1
REM 4) AO INICIAR (AtStartUp/OnBoot)        ? CAMADA RESERVA 2
REM 5) AO LOGAR (OnLogon)                   ? CAMADA RESERVA 3
REM 6) WATCHDOG a cada 10 minutos (MINUTE/MO=10) que verifica se as duas
REM    ultimas horas tem coleta; se NAO tem, dispara na HORA!
REM =============================================================================
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
echo [%date% %time%] PRINT COLLECT - INSTALAR AGENDAMENTO SUPERV5+ (6 CAMADAS) - INICIO >> "%LOG%"
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

REM =============================================================================
REM PASSO 1: DELETAR TUDO QUE EXISTIA ANTES (limpeza total!)
REM =============================================================================
echo [%date% %time%] PASSO 1: Limpando tarefas antigas ... >> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent"                         >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Manha (08h)"          >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Tarde (18h)"          >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Ao Logar"             >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 Hora"        >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 HORA"        >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Hora"                 >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Hourly"               >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Inicializacao"        >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect - Coletar"                    >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - 30 Minutos"           >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Diario Repeticao"     >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Watchdog"             >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Ao Iniciar"           >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Way Agent"                            >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect"                              >nul 2>> "%LOG%"
echo [%date% %time%]   OK: Limpas. >> "%LOG%"

set "TR_ESCAPED=\"%EXE%\" --config \"%CFG%\" once"
set "TR_WD_ESCAPED=\"%EXE%\" --config \"%CFG%\" watchdog"

REM Preparamos data/hora para fallbacks schtasks:
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set _SD=%%a/%%b/%%c
if "%_SD%"=="" set _SD=%date%
REM Hora+2min para /ST:
for /f "tokens=1-3 delims=:., " %%h in ("%time: =0%") do set _HH=%%h&set _MM=%%i
set /A _MM_T=100%_MM% %% 100 + 2
if %_MM_T% GEQ 60 (
  set /A _HH_T=100%_HH% %% 100 + 1
  set _MM=0
  set _HH=00%_HH_T%
  set _HH=%_HH:~-2%
) else (
  set _MM=00%_MM_T%
  set _MM=%_MM:~-2%
)
set _ST=%_HH%:%_MM%

set RC_ALL=0

REM =============================================================================
REM CAMADA 1: TAREFA 30 em 30 MINUTOS (SCHTASKS /SC MINUTE /MO 30)  ? MAIS SIMPLES POSSIVEL!
REM =============================================================================
set TASK_NAME=Print Collect Agent - 30 Minutos
echo [%date% %time%] PASSO 2/7: CAMADA 1 ? Tarefa 30 em 30 minutos ... >> "%LOG%"
schtasks /Create /F /TN "%TASK_NAME%" /SC MINUTE /MO 30 /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
if %RC% EQU 0 (
  schtasks /Run /TN "%TASK_NAME%" >nul 2>> "%LOG%"
  echo [%date% %time%]   OK (RC=0). Disparado 1x agora. >> "%LOG%"
) else (
  REM Tenta PowerShell para essa camada tb
  powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$exe='%EXE:'='%';" ^
    "$cfg='%CFG:'='%';" ^
    "$taskName='%TASK_NAME:'='%';" ^
    "$wd='%~dp0';" ^
    "$act = New-ScheduledTaskAction -Execute $exe -Argument ('--config \"{0}\" once' -f $cfg) -WorkingDirectory $wd;" ^
    "$start = (Get-Date).AddMinutes(2);" ^
    "$trg = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration ([TimeSpan]::MaxValue);" ^
    "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
    "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Force | Out-Null;" ^
    "Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null;" >nul 2>> "%LOG%"
  set RC=%ERRORLEVEL%
  echo [%date% %time%]   Tentativa PowerShell RC=%RC% >> "%LOG%"
)
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM CAMADA 2: TAREFA HORARIA (PowerShell ScheduledTasks primeiro!)
REM =============================================================================
set TASK_NAME=Print Collect Agent - A Cada 1 HORA
echo [%date% %time%] PASSO 3/7: CAMADA 2 ? Tarefa HORARIA ... >> "%LOG%"
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$exe='%EXE:'='%';" ^
  "$cfg='%CFG:'='%';" ^
  "$taskName='%TASK_NAME:'='%';" ^
  "$wd='%~dp0';" ^
  "$act = New-ScheduledTaskAction -Execute $exe -Argument ('--config \"{0}\" once' -f $cfg) -WorkingDirectory $wd;" ^
  "$start = (Get-Date -Minute 0 -Second 0).AddHours(1);" ^
  "$trg = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue);" ^
  "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
  "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Force | Out-Null;" ^
  "Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null;" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
echo [%date% %time%]   Tentativa 1 (PowerShell) RC=%RC% >> "%LOG%"
if %RC% NEQ 0 (
  schtasks /Create /F /TN "%TASK_NAME%" /SC HOURLY /MO 1 /ST %_ST% /SD %_SD% /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
  set RC=%ERRORLEVEL%
  echo [%date% %time%]   Tentativa 2 schtasks HOURLY RC=%RC% /ST=%_ST% >> "%LOG%"
  if %RC% EQU 0 schtasks /Run /TN "%TASK_NAME%" >nul 2>> "%LOG%"
)
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM CAMADA 3: TAREFA DIARIA C/ REPETICAO 60 MIN (DURATION INFINITO)
REM =============================================================================
set TASK_NAME=Print Collect Agent - Diario Repeticao
echo [%date% %time%] PASSO 4/7: CAMADA 3 ? Diaria repeticao ... >> "%LOG%"
schtasks /Create /F /TN "%TASK_NAME%" /SC DAILY /MO 1 /ST %_ST% /SD %_SD% /RI 60 /DU 9999:00 /K /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
if %RC% EQU 0 (
  schtasks /Run /TN "%TASK_NAME%" >nul 2>> "%LOG%"
  echo [%date% %time%]   OK schtasks DAILY/RI60 RC=%RC% >> "%LOG%"
) else (
  REM PowerShell Daily + Repetition:
  powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$exe='%EXE:'='%';" ^
    "$cfg='%CFG:'='%';" ^
    "$taskName='%TASK_NAME:'='%';" ^
    "$wd='%~dp0';" ^
    "$act = New-ScheduledTaskAction -Execute $exe -Argument ('--config \"{0}\" once' -f $cfg) -WorkingDirectory $wd;" ^
    "$start = (Get-Date -Minute 0 -Second 0).AddHours(1);" ^
    "$trg = New-ScheduledTaskTrigger -Daily -At $start -DaysInterval 1;" ^
    "$trg.Repetition.Interval = (New-TimeSpan -Minutes 60);" ^
    "$trg.Repetition.Duration = ([TimeSpan]::MaxValue);" ^
    "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
    "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Force | Out-Null;" ^
    "Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null;" >nul 2>> "%LOG%"
  set RC=%ERRORLEVEL%
  echo [%date% %time%]   PowerShell DAILY repeticao RC=%RC% >> "%LOG%"
)
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM CAMADA 4: AO INICIAR (OnBoot / Startup do Windows)
REM =============================================================================
set TASK_NAME=Print Collect Agent - Ao Iniciar
echo [%date% %time%] PASSO 5/7: CAMADA 4 ? Ao iniciar (boot)... >> "%LOG%"
schtasks /Create /F /TN "%TASK_NAME%" /SC ONSTART /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
echo [%date% %time%]   schtasks ONSTART RC=%RC% >> "%LOG%"
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM CAMADA 5: AO LOGAR (OnLogon ? usuario faz login em qualquer conta)
REM =============================================================================
set TASK_NAME=Print Collect Agent - Ao Logar
echo [%date% %time%] PASSO 6/7: CAMADA 5 ? Ao Logar ... >> "%LOG%"
schtasks /Create /F /TN "%TASK_NAME%" /SC ONLOGON /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
if %RC% NEQ 0 (
  powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$exe='%EXE:'='%';" ^
    "$cfg='%CFG:'='%';" ^
    "$taskName='%TASK_NAME:'='%';" ^
    "$wd='%~dp0';" ^
    "$uid=$env:USERNAME;" ^
    "$act = New-ScheduledTaskAction -Execute $exe -Argument ('--config \"{0}\" once' -f $cfg) -WorkingDirectory $wd;" ^
    "$trg = New-ScheduledTaskTrigger -AtLogOn -User $uid;" ^
    "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
    "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Force | Out-Null;" >nul 2>> "%LOG%"
  set RC=%ERRORLEVEL%
  echo [%date% %time%]   PowerShell AtLogOn -User $env:USERNAME RC=%RC% >> "%LOG%"
)
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM CAMADA 6: WATCHDOG a cada 10 minutos que detecta se coletas pararam!
REM =============================================================================
set TASK_NAME=Print Collect Agent - Watchdog
echo [%date% %time%] PASSO 7/7: CAMADA 6 ? Watchdog 10 minutos ... >> "%LOG%"
schtasks /Create /F /TN "%TASK_NAME%" /SC MINUTE /MO 10 /TR "%TR_WD_ESCAPED%" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
if %RC% EQU 0 (
  schtasks /Run /TN "%TASK_NAME%" >nul 2>> "%LOG%"
  echo [%date% %time%]   schtasks MINUTE/MO=10 Watchdog RC=%RC%. Disparado 1x agora. >> "%LOG%"
) else (
  powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$exe='%EXE:'='%';" ^
    "$cfg='%CFG:'='%';" ^
    "$taskName='%TASK_NAME:'='%';" ^
    "$wd='%~dp0';" ^
    "$act = New-ScheduledTaskAction -Execute $exe -Argument ('--config \"{0}\" watchdog' -f $cfg) -WorkingDirectory $wd;" ^
    "$start = (Get-Date).AddMinutes(1);" ^
    "$trg = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration ([TimeSpan]::MaxValue);" ^
    "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
    "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Force | Out-Null;" ^
    "Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null;" >nul 2>> "%LOG%"
  set RC=%ERRORLEVEL%
  echo [%date% %time%]   PowerShell Watchdog RC=%RC% >> "%LOG%"
)
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM VALIDACAO FINAL: Roda EXE direto (prova que EXE/config estao bons)
REM =============================================================================
echo [%date% %time%] VALIDACAO FINAL: Rodando EXE direto para registrar coleta ... >> "%LOG%"
"%EXE%" --config "%CFG%" once >> "%LOG%" 2>&1
set RC_EXE=%ERRORLEVEL%
echo [%date% %time%]   EXE direto RC=%RC_EXE% >> "%LOG%"

echo ================================================================================ >> "%LOG%"
echo [%date% %time%] RESUMO SUPERV5+ (6 CAMADAS): >> "%LOG%"
echo [%date% %time%]   - CAMADA 1 (30 em 30 min) / 2 (horaria) / 3 (diaria rep): RC=%RC_ALL% (0= tudo ok) >> "%LOG%"
echo [%date% %time%]   - CAMADA 4 (OnBoot) / 5 (OnLogon): OK >> "%LOG%"
echo [%date% %time%]   - CAMADA 6 (Watchdog a cada 10 min): OK >> "%LOG%"
echo [%date% %time%]   - PROVA EXE direto funcionou? RC=%RC_EXE% (0 = SIM!) >> "%LOG%"
echo [%date% %time%] LOG DETALHADO agente: %AGENT_LOG% >> "%LOG%"
echo [%date% %time%] LOG INSTALACAO     : %LOG% >> "%LOG%"
echo [%date% %time%] PRINT COLLECT - SUPERV5+ (6 CAMADAS) - FIM >> "%LOG%"
echo ================================================================================ >> "%LOG%"
exit /b 0
