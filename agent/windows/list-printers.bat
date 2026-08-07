@echo off
setlocal EnableExtensions
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

echo ==============================================
echo   PRINT COLLECT AGENT - LISTAR IMPRESSORAS
echo ==============================================
echo.
echo Este script varre a rede e mostra as impressoras encontradas.
echo Nada sera enviado ao servidor central.
echo.
set /p COMMUNITY="Informe a comunidade SNMP [public]: "
if "%COMMUNITY%"=="" set "COMMUNITY=public"

echo.
"%EXE%" --config "%CFG%" list --community "%COMMUNITY%"
echo.
pause
