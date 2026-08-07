@echo off
REM Variante SILENCIOSA do register-startup-task.bat para rodar DENTRO do Inno Setup.
REM NUNCA usa PAUSE, NUNCA pede interacao, sempre retorna exit 0 para nao travar instalador.
REM
REM CORRECOES CRITICAS (v3 AGO/2026):
REM  [X] BUG de aspas no TR_ONCE — Sintaxe inline + caminhos totalmente escapados para schtasks
REM  [X] BUG %~z0 (comparava tamanho do BATCH, nao do LOG)
REM  [X] REMOVIDO /RL HIGHEST — pedia admin e tarefa nunca rodava em usuario normal
REM  [X] Tarefa horaria HOURLY /MO 1 (100% Win7+) + fallback MINUTE /MO 60
REM  [X] Delecao FORCADA de TODAS as tarefas antigas ANTES de criar novas

setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "LOG=%TEMP%\print-collect-startup.log"

REM === LIMPA LOG se passar de 1MB (nao usa %~z0, usa %~z_LOG% de verdade) ===
if exist "%LOG%" for %%F in ("%LOG%") do if %%~zF GEQ 1048576 del /F /Q "%LOG%"

echo ================================================================================ >> "%LOG%"
echo [%date% %time%] PRINT COLLECT - INSTALAR AGENDAMENTO (v3) - INICIO >> "%LOG%"
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
REM PASSO 1: DELETAR TUDO QUE EXISTIA ANTES (TODAS AS TAREFA ANTIGAS, NOMES DIFERENTES)
REM ================================================================================
echo [%date% %time%] PASSO 1/4: Limpando tarefas antigas... >> "%LOG%"
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

REM ================================================================================
REM PASSO 2: TAREFA HORARIA (1 em 1 hora)
REM NOTA sobre ASPAS com SCHTASKS /TR em caminhos C:\Program Files (x86)\... (com espacos):
REM   A sintaxe CORRETA e UNIVERSALMENTE compativel eh passar o /TR assim:
REM     /TR "\"C:\caminho\com espaco\exe\" --config \"C:\cfg\config.yaml\" once"
REM   Ou seja, ASPAS DUPLAS FORA + ASPAS DUPLAS escapadas internamente.
REM ================================================================================
echo [%date% %time%] PASSO 2/4: Criando tarefa HORARIA (1/1h)... >> "%LOG%"

set "TASK_HOURLY=Print Collect Agent - A Cada 1 HORA"
REM Montar o argumento do /TR com todas as aspas CORRETAS (o jeito mais seguro no schtasks):
REM    Variavel TR_ESCAPED = "\"C:\Program Files (x86)\...exe\" --config \"C:\ProgramData\...config.yaml\" once"
set "TR_ESCAPED=\"%EXE%\" --config \"%CFG%\" once"

schtasks /Create /F /TN "%TASK_HOURLY%" /SC HOURLY /MO 1 /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
set RC1=%ERRORLEVEL%
echo [%date% %time%]   Tentativa 1 HOURLY/MO=1 -> RC=%RC1% >> "%LOG%"

if %RC1% NEQ 0 (
    REM FALLBACK: MINUTE /MO 60 (funciona em Windows doente)
    schtasks /Create /F /TN "%TASK_HOURLY%" /SC MINUTE /MO 60 /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
    set RC1=%ERRORLEVEL%
    echo [%date% %time%]   Tentativa 2 MINUTE/MO=60 -> RC=%RC1% >> "%LOG%"
)
if %RC1% EQU 0 (
    echo [%date% %time%]   [OK] Tarefa horaria CRIADA com sucesso. >> "%LOG%"
) else (
    REM TENTATIVA FINAL (PowerShell ScheduledTasks): mais robusto em Win10+
    echo [%date% %time%]   Tentando PowerShell ScheduledTasks fallback... >> "%LOG%"
    powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
      "$ErrorActionPreference='SilentlyContinue';" ^
      "$action = New-ScheduledTaskAction -Execute '%EXE:'='%' -Argument '--config \"%CFG:'='%\" once';" ^
      "$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue);" ^
      "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable;" ^
      "Register-ScheduledTask -TaskName '%TASK_HOURLY:'='%' -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null;" ^
      "exit [int](-not $?)" >nul 2>> "%LOG%"
    set RC1=%ERRORLEVEL%
    echo [%date% %time%]   Tentativa 3 PowerShell -> RC=%RC1% >> "%LOG%"
)

REM ================================================================================
REM PASSO 3: CRIAR TAREFA AO LOGAR (SEM /RL HIGHEST, pois pede Admin!)
REM ================================================================================
echo [%date% %time%] PASSO 3/4: Criando tarefa AO LOGAR... >> "%LOG%"

set "TASK_LOGON=Print Collect Agent - Ao Logar"
schtasks /Create /F /TN "%TASK_LOGON%" /SC ONLOGON /TR "%TR_ESCAPED%" >nul 2>> "%LOG%"
set RC2=%ERRORLEVEL%
echo [%date% %time%]   ONLOGON (schtasks) -> RC=%RC2% >> "%LOG%"

if %RC2% NEQ 0 (
    REM PowerShell fallback para ONLOGON:
    powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
      "$ErrorActionPreference='SilentlyContinue';" ^
      "$action = New-ScheduledTaskAction -Execute '%EXE:'='%' -Argument '--config \"%CFG:'='%\" once';" ^
      "$trigger = New-ScheduledTaskTrigger -AtLogOn;" ^
      "$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable;" ^
      "Register-ScheduledTask -TaskName '%TASK_LOGON:'='%' -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null;" ^
      "exit [int](-not $?)" >nul 2>> "%LOG%"
    set RC2=%ERRORLEVEL%
    echo [%date% %time%]   ONLOGON (PowerShell fallback) -> RC=%RC2% >> "%LOG%"
)

REM ================================================================================
REM PASSO 4: RODAR UMA COLETA AGORA (TESTE)
REM ================================================================================
echo [%date% %time%] PASSO 4/4: Rodando COLETA AGORA (once)... >> "%LOG%"
"%EXE%" --config "%CFG%" once >> "%LOG%" 2>&1
set RC3=%ERRORLEVEL%
echo [%date% %time%]   Coleta once RC=%RC3% >> "%LOG%"

echo ================================================================================ >> "%LOG%"
echo [%date% %time%] RESUMO: >> "%LOG%"
echo [%date% %time%]   - Tarefa HORARIA (1/1h) criada? RC=%RC1% >> "%LOG%"
echo [%date% %time%]   - Tarefa AO LOGAR criada?       RC=%RC2% >> "%LOG%"
echo [%date% %time%]   - Coleta teste executou?         RC=%RC3% >> "%LOG%"
echo [%date% %time%] PRINT COLLECT - INSTALAR AGENDAMENTO (v3) - FIM >> "%LOG%"
echo ================================================================================ >> "%LOG%"

REM Sempre sai 0 (mesmo com falha) para nao travar Inno Setup ou Wizard
exit /b 0
