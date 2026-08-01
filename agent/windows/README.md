# Build do instalador Windows

Este diretorio contem os arquivos para gerar o instalador standalone do agente Windows.

## O que sai no final

- `agent/dist/windows/PrintCollectAgent.exe`: executavel standalone gerado pelo `PyInstaller`
- `agent/dist/windows/PrintCollectSetup.exe`: instalador final gerado pelo `Inno Setup`

## Requisitos da maquina de build

- Windows 10/11
- Python 3.10+
- Inno Setup 6

## Gerar sem usar o PC do cliente

Se voce nao quer instalar Python nem Inno Setup no computador do cliente, use o workflow do GitHub Actions:

1. Envie o projeto para um repositorio no GitHub
2. Abra a aba `Actions`
3. Execute o workflow `Build Windows Agent Installer`
4. Baixe o artefato `print-collect-windows-agent-<versao>`
5. Extraia o artefato e copie `PrintCollectSetup.exe` para `agent/dist/windows/` no projeto que roda o backend
6. Reinicie o backend
7. Baixe novamente o pacote do agente no painel

Esse fluxo gera o instalador real sem depender do computador do cliente para build.

## Como gerar

Abra um PowerShell no diretorio do projeto e execute:

```powershell
cd agent\windows
.\build-setup.ps1
```

Se no seu Windows o arquivo `.ps1` abrir no Bloco de Notas em vez de executar, use o iniciador:

```bat
build-setup.bat
```

Se o Inno Setup estiver instalado em um caminho fora do padrao, defina:

```powershell
$env:INNO_SETUP_COMPILER = "C:\Caminho\Para\ISCC.exe"
.\build-setup.ps1
```

## Como distribuir para o cliente

1. Gere `PrintCollectSetup.exe` localmente ou via GitHub Actions
2. Se o build foi feito em outro computador Windows, copie o arquivo gerado para a pasta `agent/dist/windows/` do projeto principal
3. No backend, aponte `PRINT_COLLECT_WINDOWS_SETUP_PATH` para esse arquivo ou deixe o backend usar o caminho padrao `agent/dist/windows/PrintCollectSetup.exe`
4. Reinicie o backend
5. No painel, baixe o pacote do agente
6. Entregue ao cliente o ZIP contendo:
   - `PrintCollectSetup.exe`
   - `config.yaml` preenchido com URL e token

## Fluxo no cliente

1. Extrair o ZIP
2. Executar `PrintCollectSetup.exe`
3. Clicar em `Proximo` ate concluir
4. O instalador copia automaticamente o `config.yaml` do ZIP para `C:\Program Files\PrintCollect\config.yaml`
5. O agente inicia sozinho ao concluir e tenta descobrir a sub-rede local quando `snmp.subnets` estiver vazio
6. Editar `C:\Program Files\PrintCollect\config.yaml` apenas se quiser forcar IPs, sub-redes ou outra community SNMP

O instalador cria uma tarefa agendada do Windows para iniciar o agente automaticamente ao ligar o computador.
