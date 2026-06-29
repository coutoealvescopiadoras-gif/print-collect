# Deploy do Print Collect

Este guia explica como fazer deploy da API e do painel web na internet.

## Pré-requisitos
- Conta no GitHub (para hospedar o código)
- Conta no Railway (gratuita para a API)
- Conta no Vercel (gratuita para o painel)

---

## Passo 1: Hospedar o código no GitHub

1. Crie um repositório no GitHub
2. Adicione o código do Print Collect:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/seu-usuario/seu-repositorio.git
   git push -u origin main
   ```

---

## Passo 2: Deploy da API no Railway

1. Acesse https://railway.app e faça login com o GitHub
2. Clique em "New Project" > "Deploy from repo"
3. Selecione o seu repositório
4. Configure a pasta do servidor:
   - **Root directory**: `server`
5. Adicione as variáveis de ambiente no Railway (Settings > Variables):
   - `DATABASE_URL`: sua URL do Supabase
   - `DIRECT_URL`: sua URL direta do Supabase
   - `SECRET_KEY`: uma chave secreta segura (gere uma usando `openssl rand -hex 32`)
   - `API_KEY`: uma chave para os agentes (pode ser a mesma que está no .env)
   - `CORS_ORIGINS`: a URL do seu painel Vercel (ex: `https://print-collect.vercel.app`)
   - `AUTO_CREATE_TABLES`: `true`
6. Clique em "Deploy" e aguarde o deploy finalizar
7. Copie a URL da API gerada pelo Railway (ex: `https://print-collect-api.up.railway.app`)

---

## Passo 3: Deploy do painel no Vercel

1. Acesse https://vercel.com e faça login com o GitHub
2. Clique em "Add New" > "Project"
3. Selecione o seu repositório
4. Configure o projeto:
   - **Framework Preset**: Vite
   - **Root Directory**: `web`
5. Adicione a variável de ambiente:
   - `VITE_API_URL`: a URL da sua API no Railway (ex: `https://print-collect-api.up.railway.app`)
6. Clique em "Deploy" e aguarde o deploy finalizar

---

## Pronto!

Agora você tem:
- API rodando no Railway: `https://sua-api.railway.app`
- Painel web rodando no Vercel: `https://seu-painel.vercel.app`

Você pode acessar o painel, fazer login com `admin` / `admin123` e começar a usar o sistema!

---

## Instalar agente no cliente

Para cada cliente, siga as instruções no arquivo `agent/README.md`, mas use a URL da sua API no Railway no arquivo `config.yaml` em vez de `http://localhost:8000`.
