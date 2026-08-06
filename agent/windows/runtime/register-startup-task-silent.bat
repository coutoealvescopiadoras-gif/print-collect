@echo off
REM Variante SILENCIOSA do register-startup-task.bat para rodar DENTRO do Inno Setup.
REM NUNCA usa PAUSE, NUNCA pede interacao, sempre retorna exit 0 para nao travar instalador.
REM
REM CORRECOES CRITICAS (v2 AGO/2026):
REM  [X] BUG de aspas no TR_ONCE — montado inline via %TR_ONCE% (nao usa set /a com escapadas)
REM  [X] REMOVIDO /RL HIGHEST — pedia admin e a tarefa NUNCA rodava no usuario normal (cliente)
REM  [X] Tarefa horaria: HOURLY /MO 1 (100% compativel Win7+) ao inves de DAILY+PT1H+INFINITO (instavel)
REM  [X] DELETE FORCADO de TODAS as tarefas antigas ANTES de criar novas (08h/18h/Ao Logar/nome antigo)

setlocal EnableExtensions
cd /d "%~dp0"

set "EXE=%~dp0PrintCollectAgent.exe"
if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "LOG=%TEMP%\print-collect-startup.log"

REM === LIMPA PASTA LOG (evita log gigante) ===
if exist "%LOG%" if %~z0 GEQ 1048576 del /F /Q "%LOG%"

echo ================================================================================ >> "%LOG%"
echo [%date% %time%] PRINT COLLECT - INSTALAR AGENDAMENTO (v2) - INICIO >> "%LOG%"
echo [%date% %time%] EXE  = %EXE% >> "%LOG%"
echo [%date% %time%] CFG  = %CFG% >> "%LOG%"
echo ================================================================================ >> "%LOG%"

if not exist "%EXE%" (
    echo [%date% %time%] ERRO EXE nao encontrado: %EXE% >> "%LOG%"
    exit /b 0
)

if not exist "%CFG_DIR%" mkdir "%CFG_DIR%" >nul 2>&1
if not exist "%CFG%" (
    if exist "%~dp0config.example.yaml" (
        copy /Y "%~dp0config.example.yaml" "%CFG%" >nul
        echo [%date% %time%] Copiado config.example.yaml para %CFG% >> "%LOG%"
    )
)

REM ================================================================================
REM PASSO 1: DELETAR TUDO QUE EXISTIA ANTES (TODAS AS TAREFA ANTIGAS, NOMES DIFERENTES)
REM ================================================================================
echo [%date% %time%] PASSO 1/4: Limpando tarefas antigas... >> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent"                        >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Manha (08h)"         >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Tarde (18h)"         >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Ao Logar"            >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 Hora"       >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - A Cada 1 HORA"       >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Hora"                >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect Agent - Hourly"              >nul 2>> "%LOG%"
REM Tambem tenta apagar tarefas antigas do Print Way / variantes de nome
schtasks /Delete /F /TN "Print Way Agent"                           >nul 2>> "%LOG%"
schtasks /Delete /F /TN "Print Collect"                             >nul 2>> "%LOG%"

REM ================================================================================
REM PASSO 2: CRIAR TAREFA HORARIA (1 EM 1 HORA, MODO MAIS COMPATIVEL POSSIVEL)
REM TENTATIVA 1: /SC HOURLY /MO 1 (Win7+, Win8, Win10, Win11 — SUPORTADO POR TODOS)
REM TENTATIVA 2: /SC MINUTE /MO 60 (fallback anti-sistema-doente)
REM ================================================================================
echo [%date% %time%] PASSO 2/4: Criando tarefa HORARIA (1/1h)... >> "%LOG%"

set "TASK_HOURLY=Print Collect Agent - A Cada 1 HORA"
set "TR_ONCE="%EXE%" --config "%CFG%" once"

schtasks /Create /F /TN "%TASK_HOURLY%" ^
    /SC HOURLY /MO 1 ^
    /TR "%TR_ONCE%" >nul 2>> "%LOG%"
set RC1=%ERRORLEVEL%
echo [%date% %time%]   Tentativa 1 HOURLY/MO=1 -> RC=%RC1% >> "%LOG%"

if %RC1% NEQ 0 (
    REM TENTATIVA 2: fallback MINUTE /MO 60 (raro mas funciona em qualquer Windows)
    schtasks /Create /F /TN "%TASK_HOURLY%" ^
        /SC MINUTE /MO 60 ^
        /TR "%TR_ONCE%" >nul 2>> "%LOG%"
    set RC1=%ERRORLEVEL%
    echo [%date% %time%]   Tentativa 2 MINUTE/MO=60 -> RC=%RC1% >> "%LOG%"
)

REM ====================================================== ==========================
REM PASSO 3: CRIAR TAREFA AO LOGAR (SEMPRE QUE O USUARIO ABRIR O WINDOWS)
REM NOTA: SEM /RL HIGHEST — roda como usuario comum (funciona SEMPRE!)
REM ================================================================================
echo [%date% %time%] PASSO 3/4: Criando tarefa AO LOGAR... >> "%LOG%"

set "TASK_LOGON=Print Collect Agent - Ao Logar"
schtasks /Create /F /TN "%TASK_LOGON%" ^
    /SC ONLOGON ^
    /TR "%TR_ONCE%" >nul 2>> "%LOG%"
set RC2=%ERRORLEVEL%
echo [%date% %time%]   ONLOGON -> RC=%RC2% >> "%LOG%"

REM ================================================================================
REM PASSO 4: RODAR UMA COLETA AGORA (TESTE) — + LOG DO AGENTE
REM ================================================================================
echo [%date% %time%] PASSO 4/4: Rodando COLETA AGORA... >> "%LOG%"
"%EXE%" --config "%CFG%" once >> "%LOG%" 2>&1
set RC3=%ERRORLEVEL%
echo [%date% %time%]   Coleta once RC=%RC3% >> "%LOG%"

echo ================================================================================ >> "%LOG%"
echo [%date% %time%] RESUMO: >> "%LOG%"
echo [%date% %time%]   - Tarefa HORARIA (1/1h) criada? %RC1% >> "%LOG%"
echo [%date% %time%]   - Tarefa AO LOGAR criada?       %RC2% >> "%LOG%"
echo [%date% %time%]   - Coleta teste executou?         %RC3% >> "%LOG%"
echo [%date% %time%] PRINT COLLECT - INSTALAR AGENDAMENTO (v2) - FIM >> "%LOG%"
echo ================================================================================ >> "%LOG%"
REM Sempre sai 0 (mesmo com falha) para nao travar Inno Setup ou Wizard
exit /b 0
