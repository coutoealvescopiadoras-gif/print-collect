@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "TR_ONCE="\"%EXE%\" --config \"%CFG%\" once""

echo ==============================================
echo   PRINT COLLECT AGENT - INSTALAR (1 EM 1 HORA!)
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
echo [1/3] Tarefa: A CADA 1 HORA (60 minutos), TODOS OS DIAS, INFINITAMENTE
schtasks /Create /F /TN "Print Collect Agent - A Cada 1 Hora" ^
    /SC MINUTE /MO 60 /ST 00:00 ^
    /TR %TR_ONCE%
if errorlevel 1 (
    echo [AVISO] Falhou criar tarefa 1h. Tentando novamente...
    schtasks /Create /F /TN "Print Collect Agent - A Cada 1 Hora" /SC MINUTE /MO 60 /ST 00:00 /TR %TR_ONCE% >nul
)

echo.
echo [2/3] Tarefa: SEMPRE AO LOGAR (coleta no login, nao espera a hora!)
schtasks /Create /F /TN "Print Collect Agent - Ao Logar" ^
    /SC ONLOGON ^
    /TR %TR_ONCE%
if errorlevel 1 (
    echo [AVISO] Falhou ONLOGON. Tentando novamente...
    schtasks /Create /F /TN "Print Collect Agent - Ao Logar" /SC ONLOGON /TR %TR_ONCE% >nul
)

echo.
echo [3/3] Rodando COLETA AGORA para testar...
"%EXE%" --config "%CFG%" once

echo.
echo [OK] Instalado com SUCESSO!
echo   - Coleta automatica: A CADA 1 HORA (60 min), todos os dias, INFINITO.
echo   - Coleta no login: SIM (sempre que ligar o PC, roda imediatamente!).
echo   - Contadores: Sempre sobrescreve o ULTIMO valor (sem historico).
echo   - Horario coleta: Horario de Brasilia (America/Sao_Paulo) correto!
echo   - Para ver tarefas: Agendador de Tarefas do Windows.
echo.
pause
exit /b 0
