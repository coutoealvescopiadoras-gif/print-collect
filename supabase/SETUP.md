# Configurar Supabase (conta gratuita)

## 1. Criar conta

1. Acesse [https://supabase.com](https://supabase.com)
2. Clique em **Start your project**
3. Entre com GitHub ou e-mail
4. Crie uma **Organization** (pode usar seu nome ou da empresa)
5. Clique em **New project**
   - **Name:** `print-collect`
   - **Database Password:** anote em local seguro (você vai precisar)
   - **Region:** escolha a mais próxima (ex: South America — São Paulo)
6. Aguarde ~2 minutos até o projeto ficar pronto

## 2. Criar as tabelas

1. No painel do Supabase, vá em **SQL Editor**
2. Clique em **New query**
3. Copie todo o conteúdo de `supabase/schema.sql` deste projeto
4. Clique em **Run**
5. Confirme em **Table Editor** que apareceram: `clients`, `printers`, `agents`, etc.

## 3. Obter a connection string

1. Vá em **Project Settings** (ícone de engrenagem)
2. Clique em **Database**
3. Em **Connection string**, selecione **URI**
4. Copie a string **Session pooler** (porta 5432) ou **Transaction pooler** (porta 6543)
5. Substitua `[YOUR-PASSWORD]` pela senha do banco

Exemplo:
```
postgresql://postgres.xxxxx:SUASENHA@aws-0-sa-east-1.pooler.supabase.com:6543/postgres
```

## 4. Configurar a API

```bash
cd server
cp .env.example .env
```

Edite `server/.env`:
```env
DATABASE_URL=postgresql://postgres.xxxxx:SUASENHA@aws-0-sa-east-1.pooler.supabase.com:6543/postgres
```

## 5. Iniciar a API

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

A API passará a ler e gravar tudo no Supabase.

## Plano gratuito — limites

- 500 MB de banco de dados
- 2 projetos ativos
- Pausa projetos inativos após 1 semana (basta reativar no painel)

Para o Print Collect, o plano gratuito é suficiente para começar com dezenas de clientes e milhares de leituras.

## Segurança (produção)

- Nunca commite o `.env` com a senha
- Troque `agent-dev-key` por tokens únicos por agente (criados no painel)
- Em produção, desabilite os dados de demonstração no `schema.sql`
