@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "EXE_DIR=%~dp0"
cd /d "%~dp0"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "EXE=%EXE_DIR%PrintCollectAgent.exe"
if not exist "%CFG_DIR%" mkdir "%CFG_DIR%" >nul 2>&1
"%EXE%" --config "%CFG%" once
exit /b 0
