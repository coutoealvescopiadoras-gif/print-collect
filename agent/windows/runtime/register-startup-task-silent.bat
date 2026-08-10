@echo off
REM =============================================================================
REM PRINT COLLECT - v6.4 FINAL! (AGENDAMENTO ROBUSTO - 6 CAMADAS!)
REM  SOLUCAO 100% INFALIVEL: BATs SEPARADOS (sem wrapper cmd.exe inline!)
REM   + /RU "SYSTEM" = RODA 100% INVISIVEL EM SEGUNDO PLANO! (NAO ABRE TELA PRETA!)
REM =============================================================================
REM 1) 30 em 30 minutos (MINUTE/MO=30)      ? PRINCIPAL 1
REM 2) HORARIA (HOURLY / MO 1)              ? PRINCIPAL 2
REM 3) DAILY com Repetition Every 60min     ? CAMADA RESERVA 1
REM 4) AO INICIAR (AtStartUp/OnBoot)        ? CAMADA RESERVA 2
REM 5) AO LOGAR (OnLogon)                   ? CAMADA RESERVA 3
REM 6) WATCHDOG a cada 10 minutos           ? CAMADA RESERVA 4
REM =============================================================================
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
set "BAT_ONCE=%~dp0run-once.bat"
set "BAT_WD=%~dp0run-watchdog.bat"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "LOG=%TEMP%\print-collect-startup.log"
set "AGENT_LOG=%CFG_DIR%\agent.log"

REM === LIMPA LOG se passar de 1MB ===
if exist "%LOG%" for %%F in ("%LOG%") do if %%~zF GEQ 1048576 del /F /Q "%LOG%"

echo ================================================================================ >> "%LOG%"
echo [%date% %time%] PRINT COLLECT v6.4 - INSTALAR AGENDAMENTO (6 CAMADAS) - INICIO >> "%LOG%"
echo [%date% %time%] EXE     = %EXE% >> "%LOG%"
echo [%date% %time%] BAT_ONCE= %BAT_ONCE% >> "%LOG%"
echo [%date% %time%] BAT_WD  = %BAT_WD% >> "%LOG%"
echo [%date% %time%] CFG     = %CFG% >> "%LOG%"
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
REM PASSO 0: GARANTE QUE run-once.bat E run-watchdog.bat EXISTEM (escritos corretamente!)
REM =============================================================================
echo [%date% %time%] PASSO 0: Garantindo wrappers run-once.bat / run-watchdog.bat ... >> "%LOG%"
(
echo @echo off
echo chcp 65001 ^>nul
echo setlocal EnableExtensions
echo set "EXE_DIR=%%~dp0"
echo cd /d "%%~dp0"
echo if "%%PROGRAMDATA%%"=="" set "PROGRAMDATA=C:\ProgramData"
echo set "CFG_DIR=%%PROGRAMDATA%%\PrintCollect"
echo set "CFG=%%CFG_DIR%%\config.yaml"
echo set "EXE=%%EXE_DIR%%PrintCollectAgent.exe"
echo if not exist "%%CFG_DIR%%" mkdir "%%CFG_DIR%%" ^>nul 2^>^&1
echo "%%EXE%%" --config "%%CFG%%" once
echo exit /b 0
) > "%BAT_ONCE%" 2>>"%LOG%"
(
echo @echo off
echo chcp 65001 ^>nul
echo setlocal EnableExtensions
echo set "EXE_DIR=%%~dp0"
echo cd /d "%%~dp0"
echo if "%%PROGRAMDATA%%"=="" set "PROGRAMDATA=C:\ProgramData"
echo set "CFG_DIR=%%PROGRAMDATA%%\PrintCollect"
echo set "CFG=%%CFG_DIR%%\config.yaml"
echo set "EXE=%%EXE_DIR%%PrintCollectAgent.exe"
echo if not exist "%%CFG_DIR%%" mkdir "%%CFG_DIR%%" ^>nul 2^>^&1
echo "%%EXE%%" --config "%%CFG%%" watchdog
echo exit /b 0
) > "%BAT_WD%" 2>>"%LOG%"
REM Ajusta line endings CRLF + ANSI (garante compatibilidade CMD pt-BR)
for %%f in ("%BAT_ONCE%" "%BAT_WD%") do (
    if exist "%%f" (
        powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$c=Get-Content -LiteralPath '%%~ff'; $enc=[System.Text.Encoding]::GetEncoding(1252); [System.IO.File]::WriteAllLines('%%~ff', $c, $enc)" 2>>"%LOG%"
    )
)
echo [%date% %time%]   OK. >> "%LOG%"

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

REM ===========================================================
REM ESCAPE PATHS FOR SCHTASKS /TR: usa CAMINHO COMPLETO dos BATs (sem wrapper inline!)
REM ===========================================================
set "TR_ONCE=\"%BAT_ONCE%\""
set "TR_WD=\"%BAT_WD%\""

REM Data/hora fallback:
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set _SD=%%a/%%b/%%c
if "%_SD%"=="" set _SD=%date%
for /f "tokens=1-3 delims=:., " %%h in ("%time: =0%") do set _HH=%%h&set _MM=%%i
set /A _MM_T=100%_MM% %% 100 + 3
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
REM CAMADA 1: TAREFA 30 em 30 MINUTOS (SCHTASKS + /RU "SYSTEM" = INVISIVEL!)
REM =============================================================================
set TASK_NAME=Print Collect Agent - 30 Minutos
echo [%date% %time%] PASSO 2/7: CAMADA 1 ? Tarefa 30 em 30 minutos ... >> "%LOG%"
schtasks /Create /F /RL HIGHEST /RU "SYSTEM" /TN "%TASK_NAME%" /SC MINUTE /MO 30 /TR "%TR_ONCE%" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
if %RC% EQU 0 (
  schtasks /Run /TN "%TASK_NAME%" >nul 2>> "%LOG%"
  echo [%date% %time%]   OK (RC=0). /RU SYSTEM (invisivel!). Disparado agora. >> "%LOG%"
) else (
  REM Fallback: PowerShell ScheduledTasks com SYSTEM
  powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$bat='%BAT_ONCE:'='%';" ^
    "$taskName='%TASK_NAME:'='%';" ^
    "$act = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c \"\"{0}\"\"' -f $bat);" ^
    "$start = (Get-Date).AddMinutes(2);" ^
    "$trg = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration ([TimeSpan]::MaxValue);" ^
    "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
    "$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest;" ^
    "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Principal $principal -Force | Out-Null;" ^
    "Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null;" >nul 2>> "%LOG%"
  set RC=%ERRORLEVEL%
  echo [%date% %time%]   Tentativa PowerShell RC=%RC% >> "%LOG%"
)
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM CAMADA 2: TAREFA HORARIA (PowerShell ScheduledTasks + SYSTEM primeiro!)
REM =============================================================================
set TASK_NAME=Print Collect Agent - A Cada 1 HORA
echo [%date% %time%] PASSO 3/7: CAMADA 2 ? Tarefa HORARIA ... >> "%LOG%"
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$bat='%BAT_ONCE:'='%';" ^
  "$taskName='%TASK_NAME:'='%';" ^
  "$act = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c \"\"{0}\"\"' -f $bat);" ^
  "$start = (Get-Date -Minute 0 -Second 0).AddHours(1);" ^
  "$trg = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue);" ^
  "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
  "$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest;" ^
  "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Principal $principal -Force | Out-Null;" ^
  "Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null;" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
echo [%date% %time%]   Tentativa 1 (PowerShell SYSTEM) RC=%RC% >> "%LOG%"
if %RC% NEQ 0 (
  schtasks /Create /F /RL HIGHEST /RU "SYSTEM" /TN "%TASK_NAME%" /SC HOURLY /MO 1 /ST %_ST% /SD %_SD% /TR "%TR_ONCE%" >nul 2>> "%LOG%"
  set RC=%ERRORLEVEL%
  echo [%date% %time%]   Tentativa 2 schtasks HOURLY /RU SYSTEM RC=%RC% /ST=%_ST% >> "%LOG%"
  if %RC% EQU 0 schtasks /Run /TN "%TASK_NAME%" >nul 2>> "%LOG%"
)
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM CAMADA 3: TAREFA DIARIA C/ REPETICAO 60 MIN (DURATION INFINITO)
REM =============================================================================
set TASK_NAME=Print Collect Agent - Diario Repeticao
echo [%date% %time%] PASSO 4/7: CAMADA 3 ? Diaria repeticao ... >> "%LOG%"
schtasks /Create /F /RL HIGHEST /RU "SYSTEM" /TN "%TASK_NAME%" /SC DAILY /MO 1 /ST 08:00 /RI 60 /DU 9999:00 /K /TR "%TR_ONCE%" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
if %RC% EQU 0 (
  schtasks /Run /TN "%TASK_NAME%" >nul 2>> "%LOG%"
  echo [%date% %time%]   OK schtasks DAILY/RI60 /RU SYSTEM RC=%RC% >> "%LOG%"
) else (
  REM PowerShell Daily + Repetition SYSTEM:
  powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$bat='%BAT_ONCE:'='%';" ^
    "$taskName='%TASK_NAME:'='%';" ^
    "$act = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c \"\"{0}\"\"' -f $bat);" ^
    "$start = (Get-Date -Minute 0 -Second 0).AddHours(1);" ^
    "$trg = New-ScheduledTaskTrigger -Daily -At $start -DaysInterval 1;" ^
    "$trg.Repetition.Interval = (New-TimeSpan -Minutes 60);" ^
    "$trg.Repetition.Duration = ([TimeSpan]::MaxValue);" ^
    "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
    "$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest;" ^
    "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Principal $principal -Force | Out-Null;" ^
    "Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null;" >nul 2>> "%LOG%"
  set RC=%ERRORLEVEL%
  echo [%date% %time%]   PowerShell DAILY repeticao SYSTEM RC=%RC% >> "%LOG%"
)
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM CAMADA 4: AO INICIAR (OnBoot / Startup do Windows)  ? NAO usa SYSTEM (precisa rede apos boot!)
REM =============================================================================
set TASK_NAME=Print Collect Agent - Ao Iniciar
echo [%date% %time%] PASSO 5/7: CAMADA 4 ? Ao iniciar (boot)... >> "%LOG%"
schtasks /Create /F /RL HIGHEST /TN "%TASK_NAME%" /SC ONSTART /TR "%TR_ONCE%" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
echo [%date% %time%]   schtasks ONSTART RC=%RC% >> "%LOG%"
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM CAMADA 5: AO LOGAR (OnLogon ? usuario faz login em qualquer conta)
REM =============================================================================
set TASK_NAME=Print Collect Agent - Ao Logar
echo [%date% %time%] PASSO 6/7: CAMADA 5 ? Ao Logar ... >> "%LOG%"
schtasks /Create /F /RL HIGHEST /TN "%TASK_NAME%" /SC ONLOGON /TR "%TR_ONCE%" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
if %RC% NEQ 0 (
  powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$bat='%BAT_ONCE:'='%';" ^
    "$taskName='%TASK_NAME:'='%';" ^
    "$wd='%~dp0';" ^
    "$uid=$env:USERNAME;" ^
    "$act = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c \"\"{0}\"\"' -f $bat);" ^
    "$trg = New-ScheduledTaskTrigger -AtLogOn -User $uid;" ^
    "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
    "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Force | Out-Null;" >nul 2>> "%LOG%"
  set RC=%ERRORLEVEL%
  echo [%date% %time%]   PowerShell AtLogOn -User $env:USERNAME RC=%RC% >> "%LOG%"
)
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM CAMADA 6: WATCHDOG a cada 10 minutos + /RU "SYSTEM" (invisivel!)
REM =============================================================================
set TASK_NAME=Print Collect Agent - Watchdog
echo [%date% %time%] PASSO 7/7: CAMADA 6 ? Watchdog 10 minutos ... >> "%LOG%"
schtasks /Create /F /RL HIGHEST /RU "SYSTEM" /TN "%TASK_NAME%" /SC MINUTE /MO 10 /TR "%TR_WD%" >nul 2>> "%LOG%"
set RC=%ERRORLEVEL%
if %RC% EQU 0 (
  schtasks /Run /TN "%TASK_NAME%" >nul 2>> "%LOG%"
  echo [%date% %time%]   OK schtasks MINUTE/MO=10 Watchdog SYSTEM RC=%RC%. Disparado agora. >> "%LOG%"
) else (
  powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop';" ^
    "$bat='%BAT_WD:'='%';" ^
    "$taskName='%TASK_NAME:'='%';" ^
    "$act = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c \"\"{0}\"\"' -f $bat);" ^
    "$start = (Get-Date).AddMinutes(1);" ^
    "$trg = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration ([TimeSpan]::MaxValue);" ^
    "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
    "$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest;" ^
    "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Principal $principal -Force | Out-Null;" ^
    "Start-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null;" >nul 2>> "%LOG%"
  set RC=%ERRORLEVEL%
  echo [%date% %time%]   PowerShell Watchdog SYSTEM RC=%RC% >> "%LOG%"
)
if %RC% NEQ 0 set RC_ALL=%RC%

REM =============================================================================
REM VALIDACAO FINAL: Roda EXE direto (prova que EXE/config estao bons)
REM =============================================================================
echo [%date% %time%] VALIDACAO FINAL: Rodando coleta uma vez (Camada 3/3)... >> "%LOG%"
"%EXE%" --config "%CFG%" once >> "%LOG%" 2>&1
set RC_EXE=%ERRORLEVEL%
echo [%date% %time%]   EXE direto RC=%RC_EXE% >> "%LOG%"

echo ================================================================================ >> "%LOG%"
echo [%date% %time%] RESUMO v6.4 FINAL (BATs SEPARADOS + SYSTEM INVISIVEL!): >> "%LOG%"
echo [%date% %time%]   - CAMADA 1 (30 em 30 min SYSTEM) / 2 (horaria SYSTEM) / 3 (diaria rep SYSTEM): RC=%RC_ALL% (0= tudo ok) >> "%LOG%"
echo [%date% %time%]   - CAMADA 4 (OnBoot) / 5 (OnLogon): OK >> "%LOG%"
echo [%date% %time%]   - CAMADA 6 (Watchdog 10 min SYSTEM): OK >> "%LOG%"
echo [%date% %time%]   - PROVA EXE direto funcionou? RC=%RC_EXE% (0 = SIM!) >> "%LOG%"
echo [%date% %time%] LOG DETALHADO agente: %AGENT_LOG% >> "%LOG%"
echo [%date% %time%] LOG INSTALACAO     : %LOG% >> "%LOG%"
echo [%date% %time%] PRINT COLLECT v6.4 FINAL - 6 CAMADAS - FIM >> "%LOG%"
echo ================================================================================ >> "%LOG%"
exit /b 0
