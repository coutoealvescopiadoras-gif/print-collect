@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
set "CFG=%~dp0config.yaml"

echo ==============================================
echo   PRINT COLLECT AGENT - INSTALAR
echo ==============================================
echo.

if not exist "%EXE%" (
    echo [ERRO] Executavel nao encontrado: %EXE%
    pause
    exit /b 1
)

if not exist "%CFG%" (
    echo [AVISO] config.yaml nao encontrado. Copiando exemplo...
    copy /Y "%~dp0config.example.yaml" "%CFG%" >nul
)

echo [1/2] Registrando tarefa de inicializacao automatica (no login do usuario)...
schtasks /Create /F /TN "Print Collect Agent" ^
    /SC ONLOGON ^
    /TR "\"%EXE%\" --config \"%CFG%\"" ^
    /RL HIGHEST
if errorlevel 1 (
    echo [ERRO] Falha ao criar tarefa agendada.
    pause
    exit /b 1
)

echo [2/2] Iniciando tarefa imediatamente...
schtasks /Run /TN "Print Collect Agent" >nul 2>&1

echo.
echo [OK] Agente instalado e iniciado.
echo   - Local: %EXE%
echo   - Config: %CFG%
echo   - Tarefa: Agendada no login do usuario (Sistema/Tarefas Agendadas).
echo.
pause
exit /b 0
