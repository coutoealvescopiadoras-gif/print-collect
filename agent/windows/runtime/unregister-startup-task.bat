@echo off
setlocal
cd /d "%~dp0"

REM Apaga TUDO: nomes antigos (antes 08h/18h) e nomes NOVOS (1h + logon):
schtasks /Delete /F /TN "Print Collect Agent"                        >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Manha (08h)"         >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Tarde (18h)"         >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Ao Logar"            >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 Hora"       >nul 2>&1

echo [OK] Todas as tarefas do Print Collect foram removidas.
pause
exit /b 0
