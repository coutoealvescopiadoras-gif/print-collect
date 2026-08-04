@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "TR_ONCE="\"%EXE%\" --config \"%CFG%\" once""

echo ==============================================
echo   PRINT COLLECT AGENT - INSTALAR (2x POR DIA!)
echo ==============================================
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

echo.
echo [1/4] Tarefa: TODOS OS DIAS as 08:00 (manha)
schtasks /Create /F /TN "Print Collect Agent - Manha (08h)" ^
    /SC DAILY /ST 08:00 ^
    /TR %TR_ONCE%
if errorlevel 1 (
    echo [AVISO] Falhou 08:00. Tentando sem /RL HIGHEST (nao admin)...
    schtasks /Create /F /TN "Print Collect Agent - Manha (08h)" /SC DAILY /ST 08:00 /TR %TR_ONCE% >nul
)

echo.
echo [2/4] Tarefa: TODOS OS DIAS as 18:00 (tarde)
schtasks /Create /F /TN "Print Collect Agent - Tarde (18h)" ^
    /SC DAILY /ST 18:00 ^
    /TR %TR_ONCE%
if errorlevel 1 (
    echo [AVISO] Falhou 18:00. Tentando sem /RL HIGHEST (nao admin)...
    schtasks /Create /F /TN "Print Collect Agent - Tarde (18h)" /SC DAILY /ST 18:00 /TR %TR_ONCE% >nul
)

echo.
echo [3/4] Tarefa: SEMPRE AO LOGAR (coleta no login)
schtasks /Create /F /TN "Print Collect Agent - Ao Logar" ^
    /SC ONLOGON ^
    /TR %TR_ONCE%
if errorlevel 1 (
    echo [AVISO] Falhou ONLOGON. Tentando sem /RL HIGHEST...
    schtasks /Create /F /TN "Print Collect Agent - Ao Logar" /SC ONLOGON /TR %TR_ONCE% >nul
)

echo.
echo [4/4] Rodando COLETA AGORA para testar...
"%EXE%" --config "%CFG%" once

echo.
echo [OK] Instalado com SUCESSO!
echo   - Coleta automatica: 08h e 18h todos os dias.
echo   - Coleta no login: SIM (sempre que ligar o PC).
echo   - Para ver tarefas: Agendador de Tarefas do Windows.
echo.
pause
exit /b 0
