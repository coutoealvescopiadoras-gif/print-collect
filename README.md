# Print Collect

Sistema de coleta e gestão de impressoras alugadas nos clientes.

**Banco de dados:** [Supabase](https://supabase.com) (PostgreSQL gratuito na nuvem)  
**Coletor:** Python instalado na rede de cada cliente

## Arquitetura

```
┌─────────────────┐     SNMP      ┌──────────────┐     HTTP      ┌──────────────┐
│  Impressoras    │ ◄──────────── │   Coletor    │ ────────────► │  API Server  │
│  (rede cliente) │               │   Python     │               │   FastAPI    │
└─────────────────┘               └──────────────┘               └──────┬───────┘
                                                                          │
                                                                          ▼
                                                                   ┌──────────────┐
                                                                   │   Supabase   │
                                                                   │  PostgreSQL  │
                                                                   └──────┬───────┘
                                                                          │
                                                                          ▼
                                                                   ┌──────────────┐
                                                                   │  Painel Web  │
                                                                   └──────────────┘
```

## Passo a passo

### 1. Criar conta Supabase (gratuita)

Siga o guia em **[supabase/SETUP.md](supabase/SETUP.md)**:

1. Crie conta em [supabase.com](https://supabase.com)
2. Crie projeto `print-collect`
3. Execute `supabase/schema.sql` no SQL Editor
4. Copie a connection string

### 2. Subir a API (servidor central)

```bash
cd server
cp .env.example .env
# Edite .env com DATABASE_URL do Supabase

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Subir o painel web

```bash
cd web
npm install
npm run dev
```

Acesse `http://localhost:5173`

### 3.1 Alternar entre API local e publica

Para apontar o frontend para a API local:

```bash
./scripts/use-local-api.sh
```

Para apontar o frontend para a API publica:

```bash
./scripts/use-public-api.sh
```

### 3.2 Subir tudo localmente com um comando

```bash
chmod +x ./scripts/*.sh
./scripts/start-local.sh
```

Esse script:

- inicia o backend em `http://localhost:8000`
- inicia o frontend em `http://localhost:5173`
- instala dependencias automaticamente se necessario

Se voce quer que continue funcionando mesmo se fechar o Terminal:

```bash
zsh ./scripts/start-local-detached.sh
```

Para parar depois:

```bash
zsh ./scripts/stop-local.sh
```

Para ver o status e os erros rapidamente:

```bash
zsh ./scripts/status-local.sh
```

Se estiver tudo quebrado (Python/Node após atualização do macOS), dá para resetar o ambiente local:

```bash
zsh ./scripts/reset-local.sh --yes
zsh ./scripts/start-local-detached.sh
```

### 3.3 Iniciar automaticamente ao ligar o Mac

Para ativar a inicializacao automatica no login do macOS:

```bash
zsh ./scripts/install-macos-autostart.sh
```

Para desativar depois:

```bash
zsh ./scripts/uninstall-macos-autostart.sh
```

Os arquivos do `LaunchAgent` sao instalados em `~/Library/LaunchAgents`.
Os logs locais ficam na pasta `logs/`.

### 4. Instalar coletor no cliente

**Fluxo recomendado para Windows (sem depender de Python no cliente):**

- Gere o `PrintCollectSetup.exe` em um Windows de preparação ou pelo GitHub Actions
- Copie esse arquivo para `agent/dist/windows/PrintCollectSetup.exe` no projeto que roda o backend
- Reinicie o backend
- No painel, acesse **Agentes**
- Baixe o pacote Windows do agente
- Extraia o ZIP
- Execute `1-CLIQUE-AQUI-PARA-INSTALAR.bat`
- Edite `config.yaml` para informar a sub-rede ou os IPs da rede do cliente
- Teste pelos atalhos instalados no menu Iniciar

Se ainda nao houver `PrintCollectSetup.exe` configurado no backend, o sistema entrega um fallback com `install.ps1`.

Para automatizar a geracao do instalador Windows sem usar o PC do cliente, veja:

- `agent/windows/README.md`
- `.github/workflows/build-windows-agent.yml`

**Fluxo manual / desenvolvimento:**

```bash
cd agent
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp config.example.yaml config.yaml
```

No painel: **Agentes > Novo agente** → copie o token para `config.yaml`

```bash
print-collect --test    # testa conexão
print-collect --once    # coleta única
print-collect           # roda continuamente
```

Detalhes em **[agent/README.md](agent/README.md)**

## Estrutura

```
print-collect/
├── supabase/        # Schema SQL + guia de setup
├── server/          # API FastAPI → Supabase
├── web/             # Painel React
└── agent/           # Coletor Python (instalar nos clientes)
```

## O que o coletor coleta

- Modelo, serial, IP, fabricante
- Contadores de páginas (PB e colorido)
- Nível de toner
- Alertas (toner baixo/crítico)
- Envia tudo para o Supabase via API

## Próximos passos

- Autenticação de login no painel
- Relatório de faturamento por contador
- Notificações por e-mail quando toner acabar
- Deploy da API (Railway, Fly.io, etc.)
