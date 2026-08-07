@echo off
REM Versao INTERATIVA do register-startup-task.bat (atalho do usuario)
REM Correcoes v3: aspas TR corretas, sem /RL HIGHEST, HOURLY/MO1, limpa tudo, PowerShell fallback

setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "LOG=%TEMP%\print-collect-startup.log"

echo ==============================================
echo   PRINT COLLECT AGENT - INSTALAR (1 EM 1 HORA)
echo   v3 - AGOSTO 2026 - CORRIGIDO E ROBUSTO
echo ==============================================
echo.
echo Logs da instalacao: %LOG%
echo.

if not exist "%EXE%" (
    echo [ERRO] Executavel nao encontrado: %EXE%
    pause
    exit /b 1
)

if not exist "%CFG_DIR%" mkdir "%CFG_DIR%" >nul 2>&1
if not exist "%CFG%" (
    echo [AVISO] config.yaml nao encontrado em %CFG_DIR%. Copiando exemplo...
    if exist "%~dp0config.example.yaml" (
        copy /Y "%~dp0config.example.yaml" "%CFG%" >nul
    )
)

REM --- PASSO 0/4: Remove TUDO o que existia antes ---
echo.
echo [0/4] Limpando TODAS as tarefas antigas (08h/18h/nomes antigos/variantes)...
schtasks /Delete /F /TN "Print Collect Agent"                        >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Manha (08h)"         >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Tarde (18h)"         >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Ao Logar"            >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 Hora"       >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 HORA"       >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Hora"                >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Hourly"              >nul 2>&1
schtasks /Delete /F /TN "Print Way Agent"                           >nul 2>&1
schtasks /Delete /F /TN "Print Collect"                             >nul 2>&1
echo [OK] Tarefas antigas removidas.

REM --- PASSO 1/4: TAREFA HORARIA (1 em 1 hora) ---
echo.
echo [1/4] Tarefa: DE 1 EM 1 HORA (modo HOURLY /MO=1, universal)
set "TASK_HOURLY=Print Collect Agent - A Cada 1 HORA"
REM Sintaxe CORRETA de /TR com espacos: aspas fora + aspas internas escapadas com \
set "TR_ESCAPED=\"%EXE%\" --config \"%CFG%\" once"

schtasks /Create /F /TN "%TASK_HOURLY%" /SC HOURLY /MO 1 /TR "%TR_ESCAPED%"
set RC1=%ERRORLEVEL%

if %RC1% NEQ 0 (
    echo [AVISO] HOURLY/MO=1 falhou. Tentando fallback MINUTE/MO=60...
    schtasks /Create /F /TN "%TASK_HOURLY%" /SC MINUTE /MO 60 /TR "%TR_ESCAPED%"
    set RC1=%ERRORLEVEL%
)

if %RC1% NEQ 0 (
    echo [AVISO] Tentando PowerShell (ScheduledTasks)...
    powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
      "$ErrorActionPreference='SilentlyContinue';" ^
      "$action = New-ScheduledTaskAction -Execute '%EXE:'='%' -Argument '--config \"%CFG:'='%\" once';" ^
      "$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue);" ^
      "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable;" ^
      "Register-ScheduledTask -TaskName '%TASK_HOURLY:'='%' -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null;" ^
      "exit [int](-not $?)"
    set RC1=%ERRORLEVEL%
)

if %RC1% EQU 0 (
    echo [OK] Tarefa horaria instalada com sucesso.
) else (
    echo [ERRO] Falha ao instalar tarefa horaria. Veja log em: %LOG%
)

REM --- PASSO 2/4: TAREFA AO LOGAR ---
echo.
echo [2/4] Tarefa: SEMPRE AO LOGAR (coleta no login do Windows)
schtasks /Create /F /TN "Print Collect Agent - Ao Logar" /SC ONLOGON /TR "%TR_ESCAPED%"
set RC2=%ERRORLEVEL%

if %RC2% NEQ 0 (
    echo [AVISO] ONLOGAN schtasks falhou. Tentando PowerShell fallback...
    powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
      "$ErrorActionPreference='SilentlyContinue';" ^
      "$action = New-ScheduledTaskAction -Execute '%EXE:'='%' -Argument '--config \"%CFG:'='%\" once';" ^
      "$trigger = New-ScheduledTaskTrigger -AtLogOn;" ^
      "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable;" ^
      "Register-ScheduledTask -TaskName 'Print Collect Agent - Ao Logar' -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null;" ^
      "exit [int](-not $?)"
    set RC2=%ERRORLEVEL%
)

if %RC2% EQU 0 (
    echo [OK] Tarefa ao logar instalada com sucesso.
) else (
    echo [AVISO] Tarefa ao logar falhou (talvez precise de Admin, mas a HORARIA ja funciona).
)

REM --- PASSO 3/4: COLETA AGORA ---
echo.
echo [3/4] Rodando COLETA AGORA para testar (enviar impressoras ao servidor)...
"%EXE%" --config "%CFG%" once
set RC3=%ERRORLEVEL%

REM --- PASSO 4/4: SUCESSO ---
echo.
echo [4/4] Tarefas instaladas com SUCESSO!
echo.
echo ====================================================
echo   O QUE ACABA DE SER CONFIGURADO:
echo ====================================================
echo   Coleta automatica: DE 1 EM 1 HORA, TODAS as horas.
echo   Coleta no login: SIM (sempre que ligar o PC).
echo   Coleta manual: Menu Iniciar ^> Print Collect ^> Executar coleta unica.
echo   Para ver tarefas: Agendador de Tarefas do Windows.
echo.
echo   LOGS para diagnostico:
echo     - Instalacao: %LOG%
echo     - Agente a cada hora: %CFG_DIR%\agent.log
echo ====================================================
echo.
pause
exit /b 0
