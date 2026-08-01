@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if not exist "%EXE%" (
    echo [ERRO] Executavel nao encontrado: %EXE%
    echo Verifique se voce compilou o agente antes (build-setup.bat).
    pause
    exit /b 1
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
"%EXE%" list --community "%COMMUNITY%"
echo.
pause
