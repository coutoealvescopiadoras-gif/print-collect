@echo off
setlocal
cd /d "%~dp0"
schtasks /Create /F /TN "Print Collect Agent" /SC ONSTART /RU SYSTEM /RL HIGHEST /TR "\"%~dp0PrintCollectAgent.exe\" --config \"%~dp0config.yaml\""
