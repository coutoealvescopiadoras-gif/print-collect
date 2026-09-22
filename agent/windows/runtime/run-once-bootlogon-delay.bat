@echo off
REM ============================================================
REM PRINT COLLECT - TAREFA AO LOGAR / AO INICIAR (INVISIVEL!)
REM   - Espera 60s para o Windows abrir tudo + Wi-Fi conectar
REM   - Depois tenta 5x 30s esperando REDE
REM   - Roda COLETA + ENVIO 1 vez
REM   - MANTIDO INVISIVEL via schtasks /RU SYSTEM (usuário não vê)
REM ============================================================
chcp 65001 >nul
setlocal EnableExtensions
set "EXE_DIR=%~dp0"
cd /d "%~dp0"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "EXE=%EXE_DIR%PrintCollectAgent.exe"
set "LOG=%TEMP%\print-collect-boot-coleta.log"
if not exist "%CFG_DIR%" mkdir "%CFG_DIR%" >nul 2>&1

REM Log pequeno pra debug no cliente (max 512KB)
if exist "%LOG%" for %%F in ("%LOG%") do if %%~zF GEQ 524288 del /F /Q "%LOG%"
echo [%date% %time%] BOOT/LOGON: Iniciando rotina de coleta (60s delay + 5x 30s rede) >> "%LOG%"

REM --- DELAY INICIAL 60s (login do usuario abrir tudo + Wi-Fi!) ---
REM Nao usa timeout /t 60 pois schtasks SYSTEM nao tem janela. Usa ping localhost.
ping -n 61 127.0.0.1 >nul 2>&1

REM --- ESPERA REDE: max 5x 30s = 150s extra ---
set MAX_TENT=5
set TENT=0
set REDE_OK=0
:LOOP_REDE
set /a TENT+=1
ping -n 1 8.8.8.8 -w 1500 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set REDE_OK=1
    echo [%date% %time%]   rede OK tentativa %TENT% >> "%LOG%"
    goto :COLETA
)
if %TENT% GEQ %MAX_TENT% (
    echo [%date% %time%]   SEM REDE apos %MAX_TENT% tentativas, tenta USB anyway >> "%LOG%"
    goto :COLETA
)
echo [%date% %time%]   aguardando rede %TENT%/%MAX_TENT% (30s...) >> "%LOG%"
ping -n 31 127.0.0.1 >nul 2>&1
goto :LOOP_REDE

:COLETA
"%EXE%" --config "%CFG%" once >nul 2>&1
set RC=%ERRORLEVEL%
echo [%date% %time%]   coleta terminou RC=%RC% >> "%LOG%"
exit /b %RC%
