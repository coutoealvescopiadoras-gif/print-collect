@echo off
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"
echo ==============================================================
echo   PRINT COLLECT - BUILD DO AGENTE x86 (32 BITS UNIVERSAL)
echo      (Roda em QUALQUER Windows: 32 bits, 64 bits, ARM!)
echo ==============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-setup-x86.ps1"
echo.
pause
