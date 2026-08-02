@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "EXE_DIR=%~dp0"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "EXE=%EXE_DIR%PrintCollectAgent.exe"

if not exist "%CFG_DIR%" mkdir "%CFG_DIR%" >nul 2>&1
if not exist "%CFG%" (
    if exist "%EXE_DIR%config.example.yaml" (
        copy /Y "%EXE_DIR%config.example.yaml" "%CFG%" >nul
    )
)
"%EXE%" --config "%CFG%" test
echo.
pause
