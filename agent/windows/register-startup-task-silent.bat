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

echo [%date% %time%] Inicio install startup task (NOVA ESTRATEGIA: 3 tarefas ONCE) >> "%LOG%"

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

REM --- Tarefa 1: DAILY 08:00 ---
schtasks /Create /F /TN "Print Collect Agent - Manha (08h)" /SC DAILY /ST 08:00 /TR %TR_ONCE% /RL HIGHEST >nul 2>> "%LOG%"
if errorlevel 1 (
    schtasks /Create /F /TN "Print Collect Agent - Manha (08h)" /SC DAILY /ST 08:00 /TR %TR_ONCE% >nul 2>> "%LOG%"
)

REM --- Tarefa 2: DAILY 18:00 ---
schtasks /Create /F /TN "Print Collect Agent - Tarde (18h)" /SC DAILY /ST 18:00 /TR %TR_ONCE% /RL HIGHEST >nul 2>> "%LOG%"
if errorlevel 1 (
    schtasks /Create /F /TN "Print Collect Agent - Tarde (18h)" /SC DAILY /ST 18:00 /TR %TR_ONCE% >nul 2>> "%LOG%"
)

REM --- Tarefa 3: ONLOGON ---
schtasks /Create /F /TN "Print Collect Agent - Ao Logar" /SC ONLOGON /TR %TR_ONCE% /RL HIGHEST >nul 2>> "%LOG%"
if errorlevel 1 (
    schtasks /Create /F /TN "Print Collect Agent - Ao Logar" /SC ONLOGON /TR %TR_ONCE% >nul 2>> "%LOG%"
)

REM De qualquer forma tenta rodar ONCE agora (ignora erro silenciosamente)
"%EXE%" --config "%CFG%" once >nul 2>> "%LOG%"

echo [%date% %time%] Fim install startup task >> "%LOG%"
exit /b 0
