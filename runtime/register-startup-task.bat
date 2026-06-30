@echo off
setlocal

set "APP_DIR=%~dp0"
schtasks /Create /F /SC ONLOGON /RL HIGHEST /TN "PrintCollectAgent" /TR "\"%APP_DIR%PrintCollectAgent.exe\""

endlocal
exit /b 0
