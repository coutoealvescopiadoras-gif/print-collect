@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0config.yaml" copy /Y "%~dp0config.example.yaml" "%~dp0config.yaml"
notepad.exe "%~dp0config.yaml"
