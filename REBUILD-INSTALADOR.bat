@echo off
title PRINT COLLECT - REBUILD INSTALADOR (WIZARD NATIVO!)

echo.
echo ================================================================
echo   PRINT COLLECT - GERAR INSTALADOR NOVO (WIZARD NATIVO!)
echo   (WizardPareamento.exe - NAO USA MAIS .bat, ABRE SEMPRE!)
echo ================================================================
echo.

cd /d "%~dp0"
echo [PASSO 1/4] Apagando ambiente antigo (.venv-x86) para build limpo...
if exist "agent\.venv-x86" (
    rmdir /s /q "agent\.venv-x86"
    echo         OK: Pasta .venv-x86 apagada.
) else (
    echo         OK: Nao existia .venv-x86 (tudo limpo).
)
echo.

echo [PASSO 2/4] Buildando instalador x86 (PrintCollectAgent + WizardPareamento.exe)...
echo         (Vai demorar uns 3-5 minutos. Pode tomar um cafe!)
echo.
cd agent\windows
call build-setup-x86.bat
if errorlevel 1 (
    echo.
    echo [ERRO!] Build falhou. Veja mensagens ACIMA.
    echo.
    pause
    exit /b 1
)
cd /d "%~dp0"
echo.

echo [PASSO 3/4] Copiando instalador novo para web\public\...
set SETUP_SRC=agent\dist\windows\PrintCollectSetup.exe
set SETUP_DST=web\public\PrintCollectSetup.exe
if not exist "%SETUP_SRC%" (
    echo [ERRO GRAVE!] Nao encontrei %SETUP_SRC%
    echo         (Build nao gerou o arquivo?)
    pause
    exit /b 1
)
copy /y "%SETUP_SRC%" "%SETUP_DST%"
if errorlevel 1 (
    echo [ERRO!] Falha ao copiar.
    pause
    exit /b 1
)
echo         OK: Copiado para %SETUP_DST%
echo.

echo [PASSO 4/4] Verificando copia (hash)...
echo         (Se aparecerem 2 hashes IGUAIS = copia perfeita!)
echo.
certutil -hashfile "%SETUP_SRC%" SHA256
certutil -hashfile "%SETUP_DST%" SHA256
echo.

echo ================================================================
echo   SUCESSO! Instalador novo gerado!
echo   (Contem WizardPareamento.exe NATIVO - ABRE SEMPRE!)
echo.
echo   PROXIMO PASSO: Duplo clique em  GIT-SUBIR.bat
echo   (para enviar o instalador novo para o site oficial)
echo ================================================================
echo.
pause
