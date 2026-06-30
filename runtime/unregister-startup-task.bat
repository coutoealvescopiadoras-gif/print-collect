@echo off
schtasks /Delete /F /TN "PrintCollectAgent" >nul 2>&1
exit /b 0
