@echo off
REM Variante SILENCIOSA do register-startup-task.bat para rodar DENTRO do Inno Setup.
REM NUNCA usa PAUSE, NUNCA pede interacao, sempre retorna exit 0 para nao travar instalador.

setlocal EnableExtensions
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "LOG=%TEMP%\print-collect-startup.log"
set "TR_ONCE="\"%EXE%\" --config \"%CFG%\" once""

echo [%date% %time%] Inicio install startup task (NOVA ESTRATEGIA: 1 HORA + Ao Logar) >> "%LOG%"

if not exist "%EXE%" (
    echo [%date% %time%] ERRO EXE nao encontrado: %EXE% >> "%LOG%"
    exit /b 0
)

if not exist "%CFG_DIR%" mkdir "%CFG_DIR%" >nul 2>&1
if not exist "%CFG%" (
    if exist "%~dp0config.example.yaml" (
        copy /Y "%~dp0config.example.yaml" "%CFG%" >nul
    )
)

REM --- Remove tarefas antigas (legado 08h e 18h) se existirem ---
schtasks /Delete /F /TN "Print Collect Agent - Manha (08h)" >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Tarde (18h)" >nul 2>&1

REM --- Tarefa 1: CADA 1 HORA, INDEFINIDAMENTE ---
REM    Tentativa 1: modo DAILY + REPETITION Interval PT1H Duration INFINITO (Win10+)
schtasks /Create /F /TN "Print Collect Agent - A Cada 1 Hora" ^
    /SC DAILY /ST 00:00 ^
    /REPETITION /INTERVAL:PT1H /DURATION:INFINITO /ET:00:00 ^
    /TR %TR_ONCE% /RL HIGHEST >nul 2>> "%LOG%"
if errorlevel 1 (
    REM    Tentativa 2: modo HOURLY MO=1 (Win7/Server compativel)
    schtasks /Create /F /TN "Print Collect Agent - A Cada 1 Hora" ^
        /SC HOURLY /MO 1 /TR %TR_ONCE% /RL HIGHEST >nul 2>> "%LOG%"
)
if errorlevel 1 (
    REM    Tentativa 3: fallback /REPEAT (sem :) para Windows mais antigo
    schtasks /Create /F /TN "Print Collect Agent - A Cada 1 Hora" ^
        /SC DAILY /ST 00:00 /TR %TR_ONCE% ^
        /REPEAT /INTERVAL PT1H /DURATION INDEFINIDO >nul 2>> "%LOG%"
)
echo [%date% %time%] Tarefa HORARIA instalada (RC=%ERRORLEVEL%) >> "%LOG%"

REM --- Tarefa 2: AO LOGAR ---
schtasks /Create /F /TN "Print Collect Agent - Ao Logar" /SC ONLOGON /TR %TR_ONCE% /RL HIGHEST >nul 2>> "%LOG%"
if errorlevel 1 (
    schtasks /Create /F /TN "Print Collect Agent - Ao Logar" /SC ONLOGON /TR %TR_ONCE% >nul 2>> "%LOG%"
)
echo [%date% %time%] Tarefa ONLOGON instalada (RC=%ERRORLEVEL%) >> "%LOG%"

REM De qualquer forma tenta rodar ONCE agora (ignora erro silenciosamente)
"%EXE%" --config "%CFG%" once >nul 2>> "%LOG%"

echo [%date% %time%] Fim install startup task >> "%LOG%"
exit /b 0
