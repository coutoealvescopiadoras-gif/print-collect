@echo off
chcp 65001 >nul 2>&1
title PRINT COLLECT - DESINSTALACAO FORCADA v6.9.3 CORRIGIDA

setlocal enabledelayedexpansion

set "INSTALL_DIR=C:\Program Files (x86)\PrintCollect"
set "PROGRAMDATA_DIR=C:\ProgramData\PrintCollect"
set "TASK_NAME=PrintCollectAgent"
set "UNINSTALL_EXE=%INSTALL_DIR%\unins000.exe"

echo ================================================================================
echo   PRINT COLLECT - DESINSTALACAO FORCADA v6.9.3 (CORRIGIDA! SEM LINHAS SOLTAS!)
echo ================================================================================
echo   ESTE SCRIPT VAI:
echo     1. Desativar e remover Tarefa Agendada (para nao reabrir agente!)
echo     2. MATAR TODOS os processos 5 VEZES (agente tray, wizard, search)
echo     3. RODAR UNINSTALLER OFICIAL Inno COM START /WAIT (ESPERA TERMINAR!)
echo     4. APAGAR PASTAS com takeown + icacls (UAC permissao)
echo     5. Limpar atalhos menu iniciar e desktop
echo     6. Limpar entrada Registro Uninstall Display
echo ================================================================================
echo.

echo VERIFICANDO SE ESTOU COMO ADMINISTRADOR...
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERRO] VOCE NAO EXECUTOU COMO ADMINISTRADOR!
    echo  COMO FAZER: Clique BOTAO DIREITO neste .bat ^> "Executar como administrador"
    echo.
    pause
    exit /b 2
)
echo  [OK] Rodando como Administrador! Prosseguindo...
echo.

echo ------------------------------------------------------------------------------
echo   PASSO 1/7 - DESATIVAR + REMOVER TAREFA AGENDADA (impede reabrir!)
echo ------------------------------------------------------------------------------
echo.
echo [PASSO 1/7] Desativando e removendo Tarefa Agendada %TASK_NAME%...
schtasks /Change /TN "%TASK_NAME%" /DISABLE >nul 2>&1
timeout /t 1 /nobreak >nul
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
echo  OK tarefa desativada/removida.

echo.
echo ------------------------------------------------------------------------------
echo   PASSO 2/7 - MATAR TODOS OS PROCESSOS (5 TENTATIVAS COM ESPERA!)
echo ------------------------------------------------------------------------------
echo.
echo [PASSO 2/7] Fechando processos PrintCollect... (5 tentativas!)
set "tentativas=5"
set "kill_ok=0"
for /L %%i in (1,1,%tentativas%) do (
    echo    Tentativa %%i de %tentativas%...
    taskkill /F /IM PrintCollectAgent.exe /T >nul 2>&1
    taskkill /F /IM WizardPareamento.exe /T >nul 2>&1
    taskkill /F /IM SearchPrinters.exe /T >nul 2>&1
    taskkill /F /IM unins000.exe /T >nul 2>&1
    timeout /t 1 /nobreak >nul

    set "restam=0"
    tasklist /FI "IMAGENAME eq PrintCollectAgent.exe" /NH 2>nul | find /I "PrintCollectAgent.exe" >nul && set "restam=1"
    tasklist /FI "IMAGENAME eq WizardPareamento.exe" /NH 2>nul | find /I "WizardPareamento.exe" >nul && set "restam=1"
    tasklist /FI "IMAGENAME eq SearchPrinters.exe" /NH 2>nul | find /I "SearchPrinters.exe" >nul && set "restam=1"
    if "!restam!"=="0" (
        set "kill_ok=1"
        echo    Todos processos encerrados na tentativa %%i!
        goto :passo2_sair
    )
    echo    Ainda tem processos abertos. Esperando 2s e tentando de novo...
    timeout /t 2 /nobreak >nul
)
:passo2_sair
if "%kill_ok%"=="1" (
    echo  [OK] Processos 100%% fechados.
) else (
    echo  [AVISO] Algum processo ainda vivo? Vou tentar handle Inno CloseApplications e seguir.
)

echo.
echo ------------------------------------------------------------------------------
echo   PASSO 3/7 - RODAR UNINS000.EXE OFICIAL COM START /WAIT!!!
echo ------------------------------------------------------------------------------
echo.
echo [PASSO 3/7] Executando desinstalador oficial Inno Setup...
if exist "%UNINSTALL_EXE%" (
    echo  Encontrado unins000.exe. Vai rodar COM START /WAIT (nao pula! Espera terminar!)
    START "" /WAIT "%UNINSTALL_EXE%" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
    echo  unins000.exe terminou. rc = !errorlevel!
    timeout /t 3 /nobreak >nul
) else (
    echo  [INFO] unins000.exe nao encontrado (ja foi removido antes?). Pular para remocao manual pastas.
)

echo.
echo ------------------------------------------------------------------------------
echo   PASSO 4/7 - REMOVER PASTA PROGRAM FILES (COM TAKEOWN + ICACLS!)
echo ------------------------------------------------------------------------------
echo.
echo [PASSO 4/7] Removendo "%INSTALL_DIR%"...
if exist "%INSTALL_DIR%" (
    echo  [PERMISSAO FIX] takeown ownership + icacls full control Administradores...
    takeown /F "%INSTALL_DIR%" /R /D S >nul 2>&1
    icacls "%INSTALL_DIR%" /grant Administradores:F /T /C /Q >nul 2>&1
    timeout /t 1 /nobreak >nul

    set "rm_ok=0"
    for /L %%j in (1,1,3) do (
        echo    Tentativa %%j: rmdir /S /Q "%INSTALL_DIR%"
        rmdir /S /Q "%INSTALL_DIR%" >nul 2>&1
        timeout /t 2 /nobreak >nul
        if not exist "%INSTALL_DIR%" (
            set rm_ok=1
            goto :rmdir_sair
        )
        echo    Ainda existe. Esperando +2s (talvez antivirus ou handle lock)...
    )
    :rmdir_sair
    if "!rm_ok!"=="1" (
        echo  [OK] Pasta Program Files removida!
    ) else (
        echo  [AVISO] Nao consegui remover Program Files ainda? Tente no PASSO 7 REBOOT no final do script!
    )
) else (
    echo  [OK] Pasta Program Files ja nao existia.
)

echo.
echo ------------------------------------------------------------------------------
echo   PASSO 5/7 - REMOVER PASTA PROGRAMDATA (CONFIGURACAO!)
echo ------------------------------------------------------------------------------
echo.
echo [PASSO 5/7] Removendo "%PROGRAMDATA_DIR%" (configs/logs)...
if exist "%PROGRAMDATA_DIR%" (
    takeown /F "%PROGRAMDATA_DIR%" /R /D S >nul 2>&1
    icacls "%PROGRAMDATA_DIR%" /grant Administradores:F /T /C /Q >nul 2>&1
    rmdir /S /Q "%PROGRAMDATA_DIR%" >nul 2>&1
    timeout /t 1 /nobreak >nul
    if exist "%PROGRAMDATA_DIR%" (
        echo  [AVISO] ProgramData ainda existe. Vamos tentar MOVE / DEL individualmente.
        pushd "%PROGRAMDATA_DIR%"
        del /F /S /Q *.* >nul 2>&1
        popd
        rmdir /S /Q "%PROGRAMDATA_DIR%" >nul 2>&1
    )
    if exist "%PROGRAMDATA_DIR%" (echo  [ATENCAO] ProgramData nao removeu. Deletar manualmente depois se precisar limpar config) else (echo  [OK] Pasta ProgramData removida.)
) else (
    echo  [OK] ProgramData ja nao existia.
)

echo.
echo ------------------------------------------------------------------------------
echo   PASSO 6/7 - ATALHOS START MENU + DESKTOP
echo ------------------------------------------------------------------------------
echo.
echo [PASSO 6/7] Limpando atalhos Menu Iniciar e Desktop...
set "STARTMENU=%ProgramData%\Microsoft\Windows\Start Menu\Programs\Print Collect Agent"
if exist "%STARTMENU%" ( rmdir /S /Q "%STARTMENU%" >nul 2>&1 & echo  [OK] Atalhos Start Menu removidos ) else ( echo  [OK] Start menu ja limpo )

set "PUBLICDESK=%PUBLIC%\Desktop\Print Collect - Wizard.lnk"
set "USERDESK=%USERPROFILE%\Desktop\Print Collect - Wizard.lnk"
if exist "%PUBLICDESK%" ( del /F /Q "%PUBLICDESK%" >nul 2>&1 )
if exist "%USERDESK%" ( del /F /Q "%USERDESK%" >nul 2>&1 )
echo  [OK] Atalhos desktop verificados.

echo.
echo ------------------------------------------------------------------------------
echo   PASSO 7/7 - ENTRADA REGISTRO UNINSTALL
echo ------------------------------------------------------------------------------
echo.
echo [PASSO 7/7] Limpando entrada Registro Uninstall DisplayName...
set "UNREG1=HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PrintCollect_is1"
set "UNREG2=HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\PrintCollect_is1"
reg delete "%UNREG1%" /f >nul 2>&1
reg delete "%UNREG2%" /f >nul 2>&1
echo  [OK] Registro limpo.

echo.
echo ================================================================================
echo   STATUS FINAL (JULIO CONFERIR NO CLIENTE!)
echo ================================================================================
set "FINAL_OK=1"
echo ------------------------------------------------------------------------------
tasklist /FI "IMAGENAME eq PrintCollectAgent.exe" /NH 2>nul | find /I "PrintCollectAgent.exe" >nul && (echo  [!] PRINTCOLLECTAGENT.EXE AINDA RODANDO! && set FINAL_OK=0)
tasklist /FI "IMAGENAME eq WizardPareamento.exe" /NH 2>nul | find /I "WizardPareamento.exe" >nul && (echo  [!] WIZARDPAREAMENTO.EXE AINDA RODANDO! && set FINAL_OK=0)
echo ------------------------------------------------------------------------------
if exist "%INSTALL_DIR%" ( echo  [PENDENTE] PASTA Program Files ainda existe: "%INSTALL_DIR%" && set FINAL_OK=2 ) else ( echo  [OK] Pasta Program Files apagada. )
if exist "%PROGRAMDATA_DIR%" ( echo  [PENDENTE] PASTA ProgramData ainda existe: "%PROGRAMDATA_DIR%" && set FINAL_OK=2 ) else ( echo  [OK] Pasta ProgramData apagada. )
echo ------------------------------------------------------------------------------

if "!FINAL_OK!"=="1" (
    color 2F
    echo.
    echo  [SUCESSO 100%%] DESINSTALACAO FORCADA CONCLUIDA!
    echo  Agora pode RODAR o setup NOVO de 41.3 MB baixado do site!
)
if "!FINAL_OK!"=="2" (
    color 6F
    echo.
    echo  [QUASE LA] Tudo encerrado mas alguma pasta ficou (antivirus/handle lock).
    echo  Reinicie o PC e DELETE manualmente as pastas acima se elas permanecerem.
    echo  DEPOIS instale o setup novo.
)
if "!FINAL_OK!"=="0" (
    color 4F
    echo.
    echo  [FALHOU ENCERRAR PROCESSOS!] Tente REINICIAR o Windows e RODAR ESTE SCRIPT NOVAMENTE como ADMINISTRADOR.
    echo  Alternativa: Abrir Gerenciador de Tarefas - Details - Finalizar PrintCollectAgent.exe manualmente.
)
echo.
set "INSTALL_DIR="
set "PROGRAMDATA_DIR="
set "TASK_NAME="
set "UNINSTALL_EXE="
endlocal
echo FIM DA DESINSTALACAO FORCADA CORRIGIDA.
pause
exit /b 0
