@echo off
setlocal
cd /d "%~dp0"

REM v6.9.11 FIX: NAO TEM MAIS PAUSE (evita travar runhidden Inno Setup!).
REM 16 variantes de tarefas = TUDO que ja existiu em todas as versoes.

echo PRINT COLLECT - REMOVENDO TODAS AS 16 VARIANTES DE TAREFAS AGENDADAS...
echo.

REM === NOMES ANTIGOS (ate v6.4) ===
schtasks /Delete /F /TN "Print Collect Agent"                          >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Manha (08h)"           >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Tarde (18h)"           >nul 2>&1
schtasks /Delete /F /TN "Print Way Agent"                             >nul 2>&1
schtasks /Delete /F /TN "Print Collect"                               >nul 2>&1

REM === NOMES NOVOS v6.5+ (6 camadas de agendamento) ===
schtasks /Delete /F /TN "Print Collect Agent - 30 Minutos"            >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Watchdog"              >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Diario Repeticao"      >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Ao Iniciar"            >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Ao Logar"              >nul 2>&1

REM === VARIANTES DE NOME (bugs de builds antigas, pode existir!) ===
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 Hora"         >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 HORA"         >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Hora"                  >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Hourly"                >nul 2>&1
schtasks /Delete /F /TN "Print Collect Agent - Inicializacao"         >nul 2>&1
schtasks /Delete /F /TN "Print Collect - Coletar"                     >nul 2>&1

echo.
echo [OK] Tentativa de remocao em 16 variantes concluida.
echo (Se algumas ja nao existiam: normal.)
echo.

REM IMPORTANTE: SEM PAUSE! Esse BAT e chamado pelo Inno Setup UninstallRun runhidden.
REM Se tiver pause aqui, desinstalacao TRAVA PRA SEMPRE esperando ENTER.
exit /b 0
