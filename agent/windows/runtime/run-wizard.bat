@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"

if not exist "%EXE%" (
    echo [ERRO] Executavel nao encontrado: %EXE%
    echo Verifique se voce compilou o agente antes (build-setup.bat).
    pause
    exit /b 1
)

if not exist "%CFG_DIR%" mkdir "%CFG_DIR%" >nul 2>&1
if not exist "%CFG%" (
    if exist "%~dp0config.example.yaml" (
        copy /Y "%~dp0config.example.yaml" "%CFG%" >nul
    )
)

echo ==============================================================
echo   PRINT COLLECT AGENT - WIZARD DE PAREAMENTO E INSTALACAO
echo ==============================================================
echo.
echo Este script vai abrir o wizard para:
echo   1) Conectar no servidor oficial
echo   2) Inserir CODIGO DO CLIENTE ou CODIGO DE PAREAMENTO
echo   3) Instalar a inicializacao automatica (Tarefa Agendada)
echo.
"%EXE%" wizard --config "%CFG%"
echo.
pause
