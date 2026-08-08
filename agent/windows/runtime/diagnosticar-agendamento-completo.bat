@echo off
REM =============================================================================
REM PRINT COLLECT - DIAGNOSTICO COMPLETO DO AGENDAMENTO WINDOWS
REM =============================================================================
REM Cria um LOG TUDO sobre: tarefas, hora do sistema, agent.log, arquivos de
REM configuracao. Julio roda esse BAT no cliente e nos MANDA o LOG gerado.
REM Assim sabemos EXATAMENTE o que esta quebrando.
REM =============================================================================
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

if "%PROGRAMDATA%"=="" set "PROGRAMDATA=C:\ProgramData"
set "CFG_DIR=%PROGRAMDATA%\PrintCollect"
set "CFG=%CFG_DIR%\config.yaml"
set "AGENT_LOG=%CFG_DIR%\agent.log"
set "EXE=%~dp0PrintCollectAgent.exe"
set "DIAG=%TEMP%\print-collect-diagnostico-agendamento.log"

REM ===== Limpa log anterior =====
if exist "%DIAG%" del /F /Q "%DIAG%" 1>nul 2>&1

echo ================================================================================
echo PRINT COLLECT - DIAGNOSTICO COMPLETO (v6)
echo Gerando relatorio completo...
echo ================================================================================

echo ================================================================================ >> "%DIAG%"
echo PRINT COLLECT - DIAGNOSTICO COMPLETO AGENDAMENTO WINDOWS v6  >> "%DIAG%"
echo Data/Hora do relatorio: %date% %time% >> "%DIAG%"
echo Computador: %COMPUTERNAME% Usuario: %USERNAME% >> "%DIAG%"
echo ================================================================================ >> "%DIAG%"

echo. >> "%DIAG%"
echo [SECAO 1] DADOS DO SISTEMA E HORARIO >> "%DIAG%"
echo ----------------------------------- >> "%DIAG%"
echo Data do sistema..........: %date% >> "%DIAG%"
echo Hora do sistema..........: %time% >> "%DIAG%"
systeminfo | findstr /B /C:"Nome do sistema operacional" /C:"Versao do sistema operacional" /C:"Tipo de sistema" >> "%DIAG%" 2>&1

echo. >> "%DIAG%"
echo [SECAO 2] ARQUIVOS DO PRINT COLLECT EXISTEM? >> "%DIAG%"
echo ----------------------------------------- >> "%DIAG%"
if exist "%EXE%" (
  echo EXE do agente...........: EXISTE = "%EXE%" >> "%DIAG%"
  dir /-C "%EXE%" | findstr /R /C:"PrintCollectAgent.exe" >> "%DIAG%" 2>&1
) else (
  echo EXE do agente...........: [ERRO GRAVE] NAO EXISTIU "%EXE%" >> "%DIAG%"
)
if exist "%CFG_DIR%" (
  echo Pasta Config............: EXISTE "%CFG_DIR%" >> "%DIAG%"
  dir /B "%CFG_DIR%" >> "%DIAG%" 2>&1
) else (
  echo Pasta Config............: [AVISO] NAO EXISTIU "%CFG_DIR%" >> "%DIAG%"
)
if exist "%CFG%" (
  echo config.yaml.............: EXISTE >> "%DIAG%"
  type "%CFG%" >> "%DIAG%" 2>&1
) else (
  echo config.yaml.............: [ERRO GRAVE] NAO EXISTIU >> "%DIAG%"
)
if exist "%AGENT_LOG%" (
  echo agent.log...............: EXISTE (ultimas 80 linhas abaixo) >> "%DIAG%"
  echo -------------------------------------------------------------------------------- >> "%DIAG%"
  powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^
    "$c=Get-Content '%AGENT_LOG%' -ErrorAction SilentlyContinue; if($c){ $c | Select-Object -Last 80 }" >> "%DIAG%" 2>&1
  echo -------------------------------------------------------------------------------- >> "%DIAG%"
) else (
  echo agent.log...............: [AVISO] NAO EXISTIU (agente NUNCA executou?) >> "%DIAG%"
)

echo. >> "%DIAG%"
echo [SECAO 3] TAREFAS AGENDADAS EXISTENTES (10+ nomes!) >> "%DIAG%"
echo -------------------------------------------------- >> "%DIAG%"
echo Lista completa de tarefas Print Collect existentes no Windows Task Scheduler: >> "%DIAG%"
schtasks /Query /FO LIST /V 2>>&1 | findstr /I /C:"Print Collect" /C:"Print Way" /C:"print-collect" /C:"TaskName" /C:"Proxima Execucao" /C:"Ultima Execucao" /C:"Status" /C:"Executando" /C:"Erro" /C:"Ultimo Resultado" /C:"Autor da Tarefa" >> "%DIAG%" 2>&1

echo. >> "%DIAG%"
echo [SECAO 4] TESTE 1 - RODAR TAREFA EXISTENTE VIA SCHTASKS /RUN >> "%DIAG%"
echo -------------------------------------------------------------- >> "%DIAG%"
set "TASK_OK="
for %%N in (
  "Print Collect Agent - A Cada 1 HORA"
  "Print Collect Agent - A Cada 1 Hora"
  "Print Collect Agent - Hora"
  "Print Collect Agent - Hourly"
  "Print Collect Agent"
  "Print Collect"
  "Print Way Agent"
) do (
  schtasks /Query /TN %%~N >nul 2>&1
  if %ERRORLEVEL% EQU 0 (
    echo Encontrada tarefa: %%~N >>> Vamos RODAR AGORA via schtasks /RUN... >> "%DIAG%"
    schtasks /Run /TN %%~N >> "%DIAG%" 2>&1
    echo Esperando 20 segundos para o agente terminar a execucao... >> "%DIAG%"
    PING -n 21 127.0.0.1 >nul
    schtasks /Query /TN %%~N /FO LIST /V 2>>&1 | findstr /I "Resultado Execucao Erro Status" >> "%DIAG%" 2>&1
    set "TASK_OK=OK"
  )
)
if not defined TASK_OK echo [ERRO GRAVE] NENHUMA tarefa do Print Collect foi encontrada no Task Scheduler! >> "%DIAG%"

echo. >> "%DIAG%"
echo [SECAO 5] TESTE 2 - EXECUTAR O EXE DO AGENTE DIRETO (once) >> "%DIAG%"
echo --------------------------------------------------------- >> "%DIAG%"
echo Contando linhas agent.log ANTES: >> "%DIAG%"
set LINHAS_ANTES=0
if exist "%AGENT_LOG%" for /f "usebackq" %%a in (`find /C /V "" ^< "%AGENT_LOG%"`) do set LINHAS_ANTES=%%a
echo Linhas agent.log ANTES = %LINHAS_ANTES% >> "%DIAG%"

if exist "%EXE%" (
  echo. >> "%DIAG%"
  echo Executando: "%EXE%" --config "%CFG%" once >> "%DIAG%"
  echo Inicio do EXE direto: %date% %time% >> "%DIAG%"
  "%EXE%" --config "%CFG%" once >> "%DIAG%" 2>&1
  echo EXE direto TERMINOU. Exit code = %ERRORLEVEL% >> "%DIAG%"
  echo Termino do EXE direto: %date% %time% >> "%DIAG%"
  echo. >> "%DIAG%"
  echo Esperando +10 seg para log ser escrito em disco... >> "%DIAG%"
  PING -n 11 127.0.0.1 >nul
  set LINHAS_DEPOIS=0
  if exist "%AGENT_LOG%" for /f "usebackq" %%a in (`find /C /V "" ^< "%AGENT_LOG%"`) do set LINHAS_DEPOIS=%%a
  echo Linhas agent.log DEPOIS = %LINHAS_DEPOIS% >> "%DIAG%"
  if %LINHAS_DEPOIS% GTR %LINHAS_ANTES% (
    echo [SUCESSO!] agent.log GANHOU linhas! EXE direto FUNCIONA. Logo se tarefa nao roda o BUG EH DO WINDOWS TASK SCHEDULER, nao do agente! >> "%DIAG%"
  ) else (
    echo [ERRO GRAVE] EXE direto NAO gerou linha nova em agent.log! Verificar token, conexao com servidor, config.yaml correto, etc. >> "%DIAG%"
  )
) else (
  echo [NAO RODOU TESTE 2] EXE nao estava disponivel. >> "%DIAG%"
)

echo. >> "%DIAG%"
echo ================================================================================ >> "%DIAG%"
echo                        FIM DO DIAGNOSTICO COMPLETO v6
echo                        Mande o arquivo LOG abaixo para o Julio/Equipe
echo ================================================================================ >> "%DIAG%"
echo Log completo do diagnostico SALVO EM: >> "%DIAG%"
echo     %DIAG% >> "%DIAG%"
echo ================================================================================ >> "%DIAG%"

echo.
echo ============================================================================
echo DIAGNOSTICO FINALIZADO! Envie este arquivo para o Julio:
echo.
echo %DIAG%
echo ============================================================================
echo.
pause
exit /b 0
