@echo off
setlocal
cd /d "%~dp0"

schtasks /Delete /F /TN "Print Collect Agent"
exit /b 0
