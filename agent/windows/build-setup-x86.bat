@echo off
setlocal
cd /d "%~dp0"
echo ==============================================================
echo   PRINT COLLECT - BUILD DO AGENTE x86 (32 BITS UNIVERSAL)
echo      (Roda em QUALQUER Windows: 32 bits, 64 bits, ARM!)
echo ==============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-setup-x86.ps1"
if errorlevel 1 (
    echo.
    echo [ERRO!] Build falhou. Veja mensagens ACIMA.
    echo.
    pause
    exit /b 1
)
echo.
pause
