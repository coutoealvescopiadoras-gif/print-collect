@echo off
REM Variante SILENCIOSA do register-startup-task.bat para rodar DENTRO do Inno Setup.
REM NUNCA usa PAUSE, NUNCA pede interacao, sempre retorna exit 0 para nao travar instalador.

setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "LOG=%TEMP%\print-collect-startup.log"

echo [%date% %time%] Inicio install startup task >> "%LOG%"

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

REM --- TENTATIVA 1: /RL HIGHEST (precisa de admin, pode falhar silenciosamente sem admin)
schtasks /Create /F /TN "Print Collect Agent" /SC ONLOGON /TR "\"%EXE%\" daemon --config \"%CFG%\"" /RL HIGHEST >nul 2>> "%LOG%"
if errorlevel 1 (
    REM --- TENTATIVA 2: sem /RL HIGHEST — funciona para usuarios sem admin (nao precisa UAC)
    schtasks /Create /F /TN "Print Collect Agent" /SC ONLOGON /TR "\"%EXE%\" daemon --config \"%CFG%\"" >nul 2>> "%LOG%"
)

REM De qualquer forma tenta startar imediatamente (tambem ignora erro)
schtasks /Run /TN "Print Collect Agent" >nul 2>> "%LOG%"

echo [%date% %time%] Fim install startup task >> "%LOG%"
exit /b 0
