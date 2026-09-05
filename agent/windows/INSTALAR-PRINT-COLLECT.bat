@echo off
chcp 65001 >nul
cls
title PRINT COLLECT - INSTALADOR AUTOMATICO 1 CLIQUE
echo.
echo  ============================================================
echo   PRINT COLLECT - INSTALACAO AUTOMATICA DO AGENTE
echo   Servidor Padrao (Render): https://print-collect.onrender.com
echo  ============================================================
echo.
echo   [PASSO 1/5] Verificando privilegios de ADMINISTRADOR...
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo   [ERRO] VOCE NAO ESTA COMO ADMINISTRADOR!
    echo   SOLUCAO: Clique com BOTAO DIREITO neste arquivo
    echo            e escolha "Executar como Administrador".
    echo.
    pause
    exit /b 1
)
echo             [OK] Modo Administrador confirmado.
echo.

set "INSTALL_DIR=C:\Program Files (x86)\PrintCollect"
set "CONFIG_DIR=C:\ProgramData\PrintCollect"
set "STARTMENU_DIR=%ProgramData%\Microsoft\Windows\Start Menu\Programs\Print Collect"

echo   [PASSO 2/5] Criando diretorios do sistema...
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if not exist "%CONFIG_DIR%" mkdir "%CONFIG_DIR%"
if not exist "%STARTMENU_DIR%" mkdir "%STARTMENU_DIR%"
echo             [OK] Diretorios OK.
echo.

echo   [PASSO 3/5] Copiando arquivos executaveis + configuracao...
set "DIST_DIR=%~dp0..\dist\"
if not exist "%DIST_DIR%PrintCollectAgent.exe" (
    REM Se nao tiver em ..\dist\, tenta na MESMA pasta do BAT (se usuario moveu tudo)
    set "DIST_DIR=%~dp0"
)
if not exist "%DIST_DIR%PrintCollectAgent.exe" (
    echo   [ERRO FATAL] PrintCollectAgent.exe NAO encontrado!
    echo.
    echo   Voce precisa:
    echo    1. Buildar os EXEs no seu Windows Virtual:
    echo       cd agent
    echo       pyinstaller --noconfirm PrintCollectAgent.spec
    echo       pyinstaller --noconfirm WizardPareamento.spec
    echo       pyinstaller --noconfirm SearchPrinters.spec
    echo    2. COPIAR este BAT e o config-default.yaml para a pasta agent\dist\
    echo       (junto com os 3 EXEs!)
    echo    3. Rodar o BAT NOVAMENTE (como Administrador!).
    echo.
    pause
    exit /b 2
)
copy /Y "%DIST_DIR%PrintCollectAgent.exe" "%INSTALL_DIR%\" >nul
copy /Y "%DIST_DIR%WizardPareamento.exe" "%INSTALL_DIR%\" >nul 2>&1
copy /Y "%DIST_DIR%SearchPrinters.exe" "%INSTALL_DIR%\" >nul 2>&1
set "CFG_SRC=%~dp0config-default.yaml"
if not exist "%CFG_SRC%" set "CFG_SRC=%~dp0..\config.example.yaml"
copy /Y "%CFG_SRC%" "%CONFIG_DIR%\config.yaml" >nul
echo             [OK] Arquivos copiados.
echo.

echo   [PASSO 4/5] Instalando Tarefas Agendadas (30/30 min + Login)...
schtasks /Create /TN "PrintCollect\RunAgentEvery30m" /TR "'%INSTALL_DIR%\PrintCollectAgent.exe' once" /SC MINUTE /MO 30 /RU SYSTEM /F >nul 2>&1
if %errorLevel% neq 0 (
    schtasks /Create /TN "PrintCollect_30min" /TR "\"%INSTALL_DIR%\PrintCollectAgent.exe\" once" /SC MINUTE /MO 30 /RL HIGHEST /F >nul
)
schtasks /Create /TN "PrintCollect\RunOnLogin" /TR "'%INSTALL_DIR%\PrintCollectAgent.exe' once" /SC ONLOGON /RU SYSTEM /F >nul 2>&1
echo             [OK] Tarefas agendadas instaladas.
echo.

echo   [PASSO 5/5] Criando atalhos no Menu Iniciar...
powershell -NoProfile -Command "$ws=(New-Object -ComObject WScript.Shell); $s=$ws.CreateShortcut('%STARTMENU_DIR%\Wizard de Pareamento.lnk'); $s.TargetPath='%INSTALL_DIR%\WizardPareamento.exe'; $s.WorkingDirectory='%INSTALL_DIR%'; $s.Save(); $s=$ws.CreateShortcut('%STARTMENU_DIR%\Agente Print Collect.lnk'); $s.TargetPath='%INSTALL_DIR%\PrintCollectAgent.exe'; $s.WorkingDirectory='%INSTALL_DIR%'; $s.Save()" >nul 2>&1
echo             [OK] Atalhos criados.
echo.
echo  ============================================================
echo   INSTALACAO CONCLUIDA COM SUCESSO!  PARABENS!
echo  ============================================================
echo.
echo   Proximo passo: abrir o Wizard de Pareamento e colar
echo   o CODIGO DO CLIENTE (8 caracteres) ou CODIGO DE PAREAMENTO.
echo.
timeout /t 3 /nobreak >nul
echo   Abrindo Wizard de Pareamento...
if exist "%INSTALL_DIR%\WizardPareamento.exe" (
    start "" "%INSTALL_DIR%\WizardPareamento.exe"
) else (
    start "" "%INSTALL_DIR%\PrintCollectAgent.exe" wizard
)
exit /b 0
