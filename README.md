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

### 4. Instalar coletor no cliente

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
