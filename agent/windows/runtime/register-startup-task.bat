@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "TR_ONCE="\"%EXE%\" --config \"%CFG%\" once""

echo ==============================================
echo   PRINT COLLECT AGENT - INSTALAR (1 EM 1 HORA)
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

REM --- Remove tarefas antigas (legado 08h e 18h) se existirem ---
echo.
echo [0/4] Limpando tarefas antigas (legado 08h/18h)...
schtasks /Delete /F /TN "Print Collect Agent - Manha (08h)" >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Tarde (18h)" >nul 2>&1

echo.
echo [1/4] Tarefa: DE 1 EM 1 HORA (repetindo INDEFINIDAMENTE)
schtasks /Create /F /TN "Print Collect Agent - A Cada 1 Hora" ^
    /SC DAILY /ST 00:00 ^
    /REPETITION /INTERVAL:PT1H /DURATION:INFINITO /ET:00:00 ^
    /TR %TR_ONCE%
if errorlevel 1 (
    echo [AVISO] Tentando com parametros alternativos (compatibilidade Win7/10 antigo)...
    schtasks /Create /F /TN "Print Collect Agent - A Cada 1 Hora" ^
        /SC HOURLY /MO 1 ^
        /TR %TR_ONCE% >nul 2>&1
)
if errorlevel 1 (
    echo [FALLBACK] Tentando modo DAILY com REPEAT interval:PT1H duration:INDEFINIDO...
    schtasks /Create /F /TN "Print Collect Agent - A Cada 1 Hora" /SC DAILY /ST 00:00 /TR %TR_ONCE% /REPEAT /INTERVAL PT1H /DURATION INDEFINIDO >nul 2>&1
)

echo.
echo [2/4] Tarefa: SEMPRE AO LOGAR (coleta no login)
schtasks /Create /F /TN "Print Collect Agent - Ao Logar" ^
    /SC ONLOGON ^
    /TR %TR_ONCE%
if errorlevel 1 (
    echo [AVISO] Falhou ONLOGON. Tentando sem /RL HIGHEST...
    schtasks /Create /F /TN "Print Collect Agent - Ao Logar" /SC ONLOGON /TR %TR_ONCE% >nul
)

echo.
echo [3/4] Rodando COLETA AGORA para testar...
"%EXE%" --config "%CFG%" once

echo.
echo [4/4] Tarefas instaladas com SUCESSO!
echo   - Coleta automatica: DE 1 EM 1 HORA, TODAS as horas, INDEFINIDAMENTE.
echo   - Coleta no login: SIM (sempre que ligar o PC / entrar no usuario).
echo   - Coleta manual: Menu Iniciar > Print Collect > Executar coleta unica.
echo   - Para ver tarefas: Agendador de Tarefas do Windows.
echo.
pause
exit /b 0
