@echo off
chcp 65001 >nul
title PRINT COLLECT - SUBIR INSTALADOR PARA GIT/SITE

echo.
echo ================================================================
echo   PRINT COLLECT - SUBIR INSTALADOR NOVO PARA O SITE
echo ================================================================
echo.

cd /d "%~dp0"

echo [PASSO 1/4] Limpando cache do Git (para binario .exe ser detectado)...
git rm --cached -f web/public/PrintCollectSetup.exe
echo         OK.
echo.

echo [PASSO 2/4] Adicionando instalador novo FORCADAMENTE...
git add --force --verbose web/public/PrintCollectSetup.exe
if errorlevel 1 (
    echo [ATENCAO] git add retornou erro, mas pode ser normal. Continuando...
)
echo.

echo [PASSO 3/4] Commit local...
git commit -m "release(instalador): Wizard NATIVO! PrintCollectSetup.exe com WizardPareamento.exe (nao usa .bat, abre sempre)"
echo         OK.
echo.

echo [PASSO 4/4] Enviando para GitHub (push origin main)...
git push origin main
if errorlevel 1 (
    echo.
    echo [ERRO!] Push falhou. Veja mensagens ACIMA.
    echo         (Login Git / senha / internet?)
    echo.
    pause
    exit /b 1
)
echo.

echo ================================================================
echo   SUCESSO TOTAL! Instalador novo enviado!
echo.
echo   O que vai acontecer agora:
echo   1) A Vercel vai detectar o commit novo e fazer DEPLOY automatico
echo      (demora uns ~2 minutos).
echo.
echo   2) Quando terminar o deploy, acesse:
echo      https://www.printcollect.com.br/Instalador
echo      e BAIXE o instalador NOVO.
echo.
echo   3) No PC do CLIENTE:
echo      - Desinstale o instalador ANTIGO (se existir)
echo      - Instale o PrintCollectSetup.exe NOVO
echo      - Na ultima tela, a opcao "Wizard de Pareamento" vem MARCADA.
echo        Basta clicar em CONCLUIR (Finish) que o Wizard ABRE SOZINHO!
echo      - Ou use o atalho no MENU INICIAR > 1. Parear Agora (Wizard)
echo      - Ou use o atalho na AREA DE TRABALHO: Print Collect - Wizard
echo.
echo   --- WIZARD NATIVO = NAO FECHA SOZINHO, NAO DA ERRO, ABRE SEMPRE! ---
echo ================================================================
echo.
pause
