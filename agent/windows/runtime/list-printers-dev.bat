@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

rem Tenta usar o python do venv do backend se disponivel (desenvolvimento)
set "PY=c:\Users\Julio\Desktop\print-collect\server\.venv\Scripts\python.exe"
if exist "%PY%" goto :pyok

for %%P in (python python3) do (
    where %%P >nul 2>&1 && (set "PY=%%P" & goto :pyok)
)
echo [ERRO] Python nao encontrado no PATH.
pause
exit /b 1

:pyok
cd /d "%~dp0\..\.."
set "PYTHONDONTWRITEBYTECODE=1"
"%PY%" -m print_collect list %*
echo.
pause
