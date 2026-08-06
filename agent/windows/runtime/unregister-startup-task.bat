@echo off
setlocal
cd /d "%~dp0"

REM Apaga TUDO: nomes antigos, 08h/18h, versao horaria nova, Ao Logar, e variantes de nome.
echo PRINT COLLECT - REMOVENDO TODAS AS TAREFAS AGENDADAS...
echo.

schtasks /Delete /F /TN "Print Collect Agent"                        >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Manha (08h)"         >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Tarde (18h)"         >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Ao Logar"            >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 Hora"       >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 HORA"       >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Hora"                >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Hourly"              >nul 2>&1
schtasks /Delete /F /TN "Print Way Agent"                           >nul 2>&1
schtasks /Delete /F /TN "Print Collect"                             >nul 2>&1

echo.
echo [OK] Todas as tarefas do Print Collect foram removidas do Agendador.
echo (Se houver falha em algumas, significa que elas ja nao existiam.)
echo.
pause
exit /b 0
