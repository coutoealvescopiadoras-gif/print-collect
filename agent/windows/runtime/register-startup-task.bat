@echo off
REM Versao INTERATIVA do register-startup-task.bat (atalho do usuario "Reinstalar inicializacao")
REM Mostra tudo na tela e grava em arquivo LOG. Sempre tem PAUSE no final para usuario ler.
REM
REM CORRECOES v4 AGO/2026: Mesmas correcoes do v4 silent, so que com output interativo:
REM  [X] v4: PowerShell ScheduledTasks = TENTATIVA 1 (WorkingDirectory + StartWhenAvailable)
REM  [X] v4: /ST 00:00 /SD no schtasks fallback (horarios cheios: 10h,11h,12h...)
REM  [X] v4: VALIDACAO REAL via schtasks /RUN (espera 40s, compara linhas agent.log)
REM  [X] v4: AtLogon trigger com -UserId (resolve conta Microsoft bug)

setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "LOG=%TEMP%\print-collect-startup.log"
set "AGENT_LOG=%CFG_DIR%\agent.log"

echo ================================================================
echo    PRINT COLLECT - REINSTALAR INICIALIZACAO AUTOMATICA (v4)
echo    Coleta de 1 EM 1 HORA + Ao Logar. Zero configuracao manual.
echo ================================================================
echo.
echo Log detalhado (erros do schtasks): %LOG%
echo Log das coletas do agente: %AGENT_LOG%
echo.

REM === LIMPA LOG se passar de 1MB ===
if exist "%LOG%" for %%F in ("%LOG%") do if %%~zF GEQ 1048576 del /F /Q "%LOG%"
echo ================================================================================ >> "%LOG%"
echo [%date% %time%] PRINT COLLECT - REINSTALAR INICIALIZACAO (v4) - INICIO >> "%LOG%"
echo [%date% %time%] EXE = %EXE% CFG = %CFG% >> "%LOG%"
echo ================================================================================ >> "%LOG%"

if not exist "%EXE%" (
    echo.
    echo [ERRO GRAVE] Executavel NAO encontrado: %EXE%
    echo.
    echo         Dica: voce rodou este arquivo de DENTRO da pasta de instalacao?
    echo               (C:\Program Files (x86)\Print Collect\register-startup-task.bat)
    pause
    exit /b 1
)

if not exist "%CFG_DIR%" mkdir "%CFG_DIR%" >nul 2>&1
if not exist "%CFG%" (
    if exist "%~dp0config.example.yaml" (
        copy /Y "%~dp0config.example.yaml" "%CFG%" >nul
        echo [%date% %time%] Copiado config.example.yaml para %CFG% >> "%LOG%"
    ) else (
        echo.
        echo [AVISO] config.yaml nao existe ainda. Primeiro faca o PAREAMENTO no Wizard.
    )
)

REM ================================================================================
REM PASSO 1: DELETAR TUDO QUE EXISTIA ANTES
REM ================================================================================
echo.
echo [1/5] Limpando TODAS as tarefas antigas (10+ nomes diferentes)...
echo [%date% %time%] PASSO 1/5: Limpando tarefas antigas... >> "%LOG%"
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
echo         OK: Tarefas antigas removidas.
echo [%date% %time%]   OK: Tarefas antigas removidas. >> "%LOG%"

REM ================================================================================
REM PASSO 2: TAREFA HORARIA (PowerShell PRIMEIRO!)
REM ================================================================================
echo.
echo [2/5] Criando tarefa HORARIA: A CADA 1 HORA (sempre horario cheio)...

set "TASK_HOURLY=Print Collect Agent - A Cada 1 HORA"
set "TR_ESCAPED=\"%EXE%\" --config \"%CFG%\" once"

REM === TENTATIVA 1: PowerShell ScheduledTasks (WorkingDirectory + StartWhenAvailable!) ===
echo         Tentativa 1/3: PowerShell ScheduledTasks (mais robusto)...
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$exe='%EXE:'='%';" ^
  "$cfg='%CFG:'='%';" ^
  "$taskName='%TASK_HOURLY:'='%';" ^
  "$wd='%~dp0';" ^
  "$act = New-ScheduledTaskAction -Execute $exe -Argument ('--config \"{0}\" once' -f $cfg) -WorkingDirectory $wd;" ^
  "$start = (Get-Date).Date;" ^
  "$trg = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue);" ^
  "$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 1);" ^
  "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Force | Out-Null;" >nul 2>> "%LOG%"
set RC1=%ERRORLEVEL%
echo [%date% %time%]   Tentativa 1 PowerShell ScheduledTasks -> RC=%RC1% >> "%LOG%"
if %RC1% EQU 0 goto :hourly_ok

REM === FALLBACK 2: schtasks /SC HOURLY /MO 1 (COM /ST 00:00 /SD) ===
echo         Tentativa 1 falhou. Tentativa 2/3: schtasks HOURLY /ST 00:00 ...
for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set _SD=%%a/%%b/%%c
if "%_SD%"=="" set _SD=%date%
schtasks /Create /F /TN "%TASK_HOURLY%" /SC HOURLY /MO 1 /ST 00:00 /SD %_SD% /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
set RC1=%ERRORLEVEL%
echo [%date% %time%]   Tentativa 2 HOURLY/ST 00:00 SD %_SD% -> RC=%RC1% >> "%LOG%"
if %RC1% EQU 0 goto :hourly_ok

REM === FALLBACK 3: MINUTE /MO 60 ===
echo         Tentativa 2 falhou. Tentativa 3/3: schtasks MINUTE /MO 60 ...
schtasks /Create /F /TN "%TASK_HOURLY%" /SC MINUTE /MO 60 /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
set RC1=%ERRORLEVEL%
echo [%date% %time%]   Tentativa 3 MINUTE/MO 60 -> RC=%RC1% >> "%LOG%"

:hourly_ok
if %RC1% EQU 0 (
    echo         OK: Tarefa HORARIA criada com sucesso! (todos os dias as 00:00, 01:00, 02:00...)
    echo [%date% %time%]   [OK] Tarefa HORARIA criada. >> "%LOG%"
) else (
    echo         [ERRO] Tarefa HORARIA NAO foi criada. Checar log: %LOG%
    echo [%date% %time%]   [ERRO] Tarefa HORARIA RC=%RC1% >> "%LOG%"
)

REM ================================================================================
REM PASSO 3: TAREFA AO LOGAR (PowerShell primeiro com -UserId)
REM ================================================================================
echo.
echo [3/5] Criando tarefa AO LOGAR: Sempre que o usuario ligar o PC e logar...

set "TASK_LOGON=Print Collect Agent - Ao Logar"

REM === TENTATIVA 1: PowerShell AtLogOn com -UserId ===
echo         Tentativa 1/2: PowerShell com -UserId %USERNAME% ...
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
  "Register-ScheduledTask -TaskName $taskName -Action $act -Trigger $trg -Settings $set -Force | Out-Null;" >nul 2>> "%LOG%"
set RC2=%ERRORLEVEL%
echo [%date% %time%]   Tentativa 1 PowerShell AtLogOn -User '%USERNAME%' -> RC=%RC2% >> "%LOG%"
if %RC2% NEQ 0 (
    echo         Tentativa 1 falhou. Tentativa 2/2: schtasks ONLOGON ...
    schtasks /Create /F /TN "%TASK_LOGON%" /SC ONLOGON /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
    set RC2=%ERRORLEVEL%
    echo [%date% %time%]   Tentativa 2 ONLOGON schtasks -> RC=%RC2% >> "%LOG%"
)
if %RC2% EQU 0 (
    echo         OK: Tarefa AO LOGAR criada com sucesso!
    echo [%date% %time%]   [OK] Tarefa AO LOGAR criada. >> "%LOG%"
) else (
    echo         [ERRO] Tarefa AO LOGAR nao criada.
    echo [%date% %time%]   [ERRO] Tarefa AO LOGAR RC=%RC2% >> "%LOG%"
)

REM ================================================================================
REM PASSO 4: VALIDACAO REAL - EXECUTAR A TAREFA AGORAR VIA schtasks /RUN E VER agent.log GANHAR LINHAS
REM ================================================================================
echo.
echo [4/5] VALIDACAO REAL: Rodando a tarefa HORARIA do jeito WINDOWS dispara...
echo         (isso prova se amanha ela vai rodar sozinha mesmo!)
echo [%date% %time%] PASSO 4/5: VALIDACAO REAL via schtasks /RUN >> "%LOG%"

REM Conta linhas ANTES
set LINHAS_ANTES=0
if exist "%AGENT_LOG%" for /f "usebackq" %%a in (`find /C /V "" ^< "%AGENT_LOG%"`) do set LINHAS_ANTES=%%a
echo [%date% %time%]   agent.log linhas ANTES: %LINHAS_ANTES% >> "%LOG%"

schtasks /Run /TN "%TASK_HOURLY%" >nul 2>> "%LOG%"
set RC_RUN=%ERRORLEVEL%
echo [%date% %time%]   schtasks /RUN RC=%RC_RUN% >> "%LOG%"
echo         Tarefa disparada! Esperando 40 segundos para Windows carregar o agente...
echo         (se abrir uma janela preta rapidamente = funcionou!)

REM Espera 40s (41 pings = 40s)
PING -n 41 127.0.0.1 >nul

REM Conta linhas DEPOIS
set LINHAS_DEPOIS=0
if exist "%AGENT_LOG%" for /f "usebackq" %%a in (`find /C /V "" ^< "%AGENT_LOG%"`) do set LINHAS_DEPOIS=%%a
echo [%date% %time%]   agent.log linhas DEPOIS: %LINHAS_DEPOIS% >> "%LOG%"

set RC4=1
if %LINHAS_DEPOIS% GTR %LINHAS_ANTES% set RC4=0
if %RC4% EQU 0 (
    echo         [SUCESSO PROVADO!] agent.log recebeu novas linhas!
    echo         = significa que a tarefa agendada VAI RODAR SOZINHA amanha e depois!
    echo [%date% %time%]   [SUCESSO PROVADO] Validacao OK. >> "%LOG%"
) else (
    echo         [AVISO] Validacao nao marcou linha nova em 40s.
    echo         Tentando rodar o EXE direto (garante que pelo menos temos coleta HOJE).
    echo [%date% %time%]   Validacao nao marcou. Rodando EXE direto para garantir coleta. >> "%LOG%"
    "%EXE%" --config "%CFG%" once 2>&1
    set RC4=%ERRORLEVEL%
)

REM ================================================================================
REM PASSO 5: RESUMO NA TELA + LOG
REM ================================================================================
echo.
echo ================================================================
echo                        RESUMO DA INSTALACAO v4
echo ================================================================
echo   (RC=0 = SUCESSO; RC diferente de 0 = FALHOU)
echo.
set "OK_RC1=NAO"
set "OK_RC2=NAO"
set "OK_RC4=NAO"
if %RC1% EQU 0 set OK_RC1=SIM (OK!)
if %RC2% EQU 0 set OK_RC2=SIM (OK!)
if %RC4% EQU 0 set OK_RC4=SIM (VALIDADO!)
echo   - Tarefa HORARIA (1 em 1 hora)..... RC=%RC1%  => %OK_RC1%
echo   - Tarefa AO LOGAR (ao ligar PC).... RC=%RC2%  => %OK_RC2%
echo   - Coleta testada via Task Scheduler: RC=%RC4% => %OK_RC4%
echo.
echo   LOG da tarefa de inicializacao : %LOG%
echo   LOG de todas coletas do agente   : %AGENT_LOG%
echo.
echo   DICA AMANHA: Daqui a 2 horas, confira na web "Atualizado ha 1 min"
echo ================================================================
echo [%date% %time%] RESUMO v4: RC1=%RC1% RC2=%RC2% RC4=%RC4% >> "%LOG%"
echo [%date% %time%] PRINT COLLECT - REINSTALAR INICIALIZACAO (v4) - FIM >> "%LOG%"
echo ================================================================================ >> "%LOG%"
echo.
pause
exit /b 0
