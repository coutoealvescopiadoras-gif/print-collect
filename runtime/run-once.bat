@echo off
setlocal
cd /d "%~dp0"
"%~dp0PrintCollectAgent.exe" --once --config "%~dp0config.yaml"
pause
endlocal
