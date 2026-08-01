# Build do instalador Windows

Este diretorio contem os arquivos para gerar o instalador standalone do agente Windows.

## O que sai no final

- `agent/dist/windows/PrintCollectAgent.exe`: executavel standalone gerado pelo `PyInstaller`
- `agent/dist/windows/PrintCollectSetup.exe`: instalador final gerado pelo `Inno Setup`

## Requisitos da maquina de build

- Windows 10/11
- Python 3.10+
- Inno Setup 6

## ⚠️ ARQUITETURA: 32 BITS (x86) OU 64 BITS (x64)? QUAL USAR?

| Tipo build | Roda em Windows 32 bits? | Roda em Windows 64 bits? | Roda em Windows ARM? | Quando usar |
|---|---|---|---|---|
| ✅ **x86 (32 bits) RECOMENDADO** | ✅ SIM | ✅ SIM (via WOW64 — padrão!) | ✅ SIM (emulação) | **Sempre use esse para enviar para os clientes!** O instalador gerado roda em **QUALQUER WINDOWS**, sem erro "arquivo válido mas para outro tipo de computador". |
| ❌ x64 (64 bits) | ❌ NÃO (erro!) | ✅ SIM | ❌ Não em ARM nativo | Apenas para teste interno em sua máquina. |

## 🚀 PASSO A PASSO OFICIAL PARA GERAR O INSTALADOR QUE RODA EM QUALQUER WINDOWS:

### 1) Instale Python 3.10+ para **32 BITS (x86)**

Acesse: https://www.python.org/downloads/release/python-3120/  
Na página, clique em: **Windows installer (32-bit)** — **CUIDADO** para não baixar a versão 64-bit sem querer!

Durante a instalação, marque SEMPRE:
- ✅ **Add python.exe to PATH**
- ✅ Clique em **Customize installation** → Next → ✅ **Install for all users**  
  (será instalado no padrão: `C:\Program Files (x86)\Python312-32\`)

### 2) Depois, é só dar **DUPLA CLIQUE** no arquivo abaixo (na pasta agent\windows\):

```
build-setup-x86.bat
```

Ou, se preferir PowerShell:
```powershell
cd agent\windows
.\build-setup-x86.ps1
```

Pronto! O instalador `PrintCollectSetup.exe` aparecerá em `agent\dist\windows\` no final.

### 3) Subir a versão nova no site oficial (printcollect.com.br)

Depois que terminar, copie o novo `PrintCollectSetup.exe` para a pasta pública do frontend, commit e push:

```powershell
# No terminal, na raiz do projeto
Copy-Item "agent\dist\windows\PrintCollectSetup.exe" "web\public\PrintCollectSetup.exe" -Force
git add web\public\PrintCollectSetup.exe
git commit -m "release(instalador): rebuild agente em x86 32 bits (roda em QUALQUER Windows - 32/64 bits)"
git push origin main
```

Depois de ~2 minutos (deploy da Vercel), todos os seus clientes baixarão a versão nova direto do site oficial: https://www.printcollect.com.br/PrintCollectSetup.exe

---

## Gerar build de 64 bits (teste interno, não usar para clientes)

**Apenas se você quiser uma versão 64 bits para testar internamente** (não use em clientes):

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

1. Gere `PrintCollectSetup.exe` usando `build-setup-x86.bat` (o de 32 bits, que roda em qualquer Windows!)
2. O build já está disponível automaticamente no site oficial em https://www.printcollect.com.br/PrintCollectSetup.exe
3. No painel, navegue até a aba **📦 Instalador** para baixar diretamente, copiar o link oficial, ou copiar o modelo de mensagem WhatsApp pronta para enviar ao cliente.
4. Entregue ao cliente:
   - Link oficial do instalador
   - 🎫 Código do Cliente (8 dígitos, permanente, não expira) do cliente na aba Clientes
   - Se quiser, use o modelo WhatsApp pronto da aba 📦 Instalador — só falta trocar o `<CODIGO DO CLIENTE>` pelo código real dele.

## Fluxo no cliente

1. Baixar `PrintCollectSetup.exe` (do link oficial)
2. **Desbloquear o arquivo** (Windows SmartScreen costuma bloquear .exe da internet):
   - Clique com **botão direito** no `PrintCollectSetup.exe` → **Propriedades** → no rodapé marque **✅ Desbloquear** → **Aplicar → OK**.
3. Executar `PrintCollectSetup.exe` como Administrador
4. Clicar em `Proximo` ate concluir
5. O instalador copia automaticamente o `config.yaml` de exemplo para `C:\Program Files\PrintCollect\config.yaml`
6. Ao concluir, abre automaticamente o Wizard de Vínculo (pede URL do servidor + CÓDIGO DO CLIENTE 🎫 **ou** CÓDIGO DE PAREAMENTO 🔗).
7. Editar `C:\Program Files\PrintCollect\config.yaml` apenas se quiser forcar IPs, sub-redes ou outra community SNMP

O instalador cria uma tarefa agendada do Windows para iniciar o agente automaticamente ao ligar o computador.
