# Deploy do Print Collect (Vercel + Railway)

Este guia explica como fazer deploy da API e do painel web na internet usando Vercel e Railway (gratuita!).

## Pré-requisitos
✅ Conta no GitHub (para hospedar o código)
✅ Conta no Railway (gratuita para a API)
✅ Conta no Vercel (gratuita para o painel)

---

## Passo 1: Hospedar o código no GitHub

1. Crie um repositório no GitHub (pode ser público ou privado)
2. Adicione o código do Print Collect:
   ```bash
   # (Se você já tiver o repositório, pode pular esse passo)
   git remote add origin https://github.com/seu-usuario/seu-repositorio.git
   git push -u origin main
   ```

---

## Passo 2: Deploy da API no Railway

1. Acesse https://railway.app e faça login com o GitHub
2. Clique em **"New Project"** > **"Deploy from repo"**
3. Selecione o seu repositório do Print Collect
4. Configure o projeto:
   - **Root directory**: `server`
5. Vá para **Settings > Variables** e adicione todas as variáveis do arquivo `server/.env`:
   - `DATABASE_URL`: sua URL do Supabase
   - `DIRECT_URL`: sua URL direta do Supabase
   - `SECRET_KEY`: uma chave secreta segura (gere uma usando `openssl rand -hex 32`)
   - `API_KEY`: uma chave para os agentes (pode ser a mesma que está no .env)
   - `CORS_ORIGINS`: a URL do seu painel Vercel (depois que criar, volte aqui e atualize)
   - `AUTO_CREATE_TABLES`: `true`
   - (E as configurações de e-mail, se quiser usar)
6. Clique em **"Deploy"** e aguarde o deploy finalizar
7. Copie a URL da API gerada pelo Railway (ex: `https://print-collect-api.up.railway.app`)

---

## Passo 3: Deploy do painel no Vercel

1. Acesse https://vercel.com e faça login com o GitHub
2. Clique em **"Add New"** > **"Project"**
3. Selecione o seu repositório do Print Collect
4. Configure o projeto:
   - **Framework Preset**: Vite
   - **Root Directory**: `web`
5. Vá para **Environment Variables** e adicione:
   - **Name**: `VITE_API_URL`
   - **Value**: a URL da sua API no Railway (ex: `https://print-collect-api.up.railway.app`)
6. Clique em **"Deploy"** e aguarde o deploy finalizar!

---

## Passo 4: Atualizar CORS no Railway

1. No Railway, volte para **Settings > Variables**
2. Edite a variável `CORS_ORIGINS` para a URL do seu painel Vercel:
   ```
   https://seu-projeto.vercel.app
   ```
3. O Railway fará um redeploy automaticamente — aguarde finalizar

---

## Pronto! 🎉

Agora você tem:
- **API**: rodando no Railway (ex: `https://print-collect-api.up.railway.app`)
- **Painel web**: rodando no Vercel (ex: `https://print-collect.vercel.app`)

Você pode acessar o painel, fazer login com `admin` / `admin123` e começar a usar o sistema!

---

## Instalar agente no cliente

Para cada cliente, siga as instruções no arquivo `agent/README.md`, mas use a URL da sua API no Railway no arquivo `config.yaml` em vez de `http://localhost:8000`.
