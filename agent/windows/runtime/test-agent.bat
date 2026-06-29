@echo off
setlocal
cd /d "%~dp0"
"%~dp0PrintCollectAgent.exe" --config "%~dp0config.yaml" --test
echo.
pause
