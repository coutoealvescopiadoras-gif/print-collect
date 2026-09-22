@echo off
REM ============================================================
REM PRINT COLLECT - FORCAR COLETA AGORA (com espera de REDE!)
REM Julio pediu: notebook que liga e demora pra conectar Wi-Fi.
REM Espera ATE 5 MINUTOS (10x 30s) pela rede antes de desistir.
REM Ao terminar, MANTEM JANELA ABERTA para ver o resultado (tecnico!)
REM ============================================================
chcp 65001 >nul
setlocal EnableExtensions
set "EXE_DIR=%~dp0"
cd /d "%~dp0"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "EXE=%EXE_DIR%PrintCollectAgent.exe"
if not exist "%CFG_DIR%" mkdir "%CFG_DIR%" >nul 2>&1

title Print Collect - Forcando Coleta Agora (aguardando rede)
echo ============================================================
echo   PRINT COLLECT - FORCAR COLETA + ENVIO AGORA
echo   (Aguardando rede ficar pronta... max 5 minutos)
echo ============================================================
echo.

REM Tenta rede 10x, 30 segundos = ate 5 min (notebook demora Wi-Fi!)
set MAX_TENT=10
set INT=30
set TENT=0
set REDE_OK=0

:LOOP_REDE
set /a TENT+=1
ping -n 1 8.8.8.8 -w 1500 >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set REDE_OK=1
    echo [OK %TENT%/%MAX_TENT%] Rede detectada.
    goto :COLETA
)
if %TENT% GEQ %MAX_TENT% (
    echo [AVISO] Sem rede apos %MAX_TENT% tentativas. Vamos tentar assim mesmo (impressora local USB!).
    goto :COLETA
)
echo [Tentativa %TENT%/%MAX_TENT%] Aguardando rede %INT%s...
timeout /t %INT% /nobreak >nul
goto :LOOP_REDE

:COLETA
echo.
echo [INICIO] Coletando impressoras e enviando para servidor...
echo   (Executando: PrintCollectAgent.exe --config "%%CFG%%" once)
echo.
"%EXE%" --config "%CFG%" once
set RC=%ERRORLEVEL%
echo.
echo ============================================================
if %RC% EQU 0 (
    echo   [SUCESSO RC=0] Coleta concluida e enviada!
    echo   Confira no painel em 30 segundos.
) else (
    echo   [AVISO RC=%RC%] Coleta terminou com aviso.
    echo   (normal se a rede caiu durante a coleta, tenta novamente)
)
echo ============================================================
echo.
pause
endlocal
exit /b %RC%
