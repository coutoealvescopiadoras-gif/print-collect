# Deploy do Print Collect (Vercel + Render)

Este guia explica como fazer deploy da API e do painel web na internet usando Vercel e Render (100% GRATUITO, sem cartão necessário!).

## Pré-requisitos
✅ Conta no GitHub (para hospedar o código)
✅ Conta no Render (gratuita para a API)
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

## Passo 2: Deploy da API no Render (Gratuito!)

1. Acesse https://render.com e faça login com o GitHub
2. Clique em **"New +"** > **"Web Service"**
3. Selecione o seu repositório do Print Collect
4. Configure o projeto:
   - **Name**: `print-collect-api`
   - **Region: `São Paulo` (ou mais próximo)
   - **Branch**: `main`
   - **Root Directory**: `server`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt
   - **Start Command**: `gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app`
   - **Plan**: **Free**
5. Vá para a seção **Environment** e adicione as variáveis do arquivo `server/.env` (uma por uma):
   - `DATABASE_URL`: sua URL do Supabase
   - `DIRECT_URL`: sua URL direta do Supabase
   - `SECRET_KEY`: gere uma usando `openssl rand -hex 32` (ou use uma chave segura)
   - `API_KEY`: uma chave para os agentes
   - `CORS_ORIGINS`: a URL do seu painel Vercel (depois que criar, volte aqui e atualize)
   - `AUTO_CREATE_TABLES`: `true`
6. Clique em **"Create Web Service"** e aguarde o deploy finalizar (~2 minutos
7. Copie a URL da API gerada pelo Render (ex: `https://print-collect-api.onrender.com`)

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
   - **Value**: a URL da sua API no Render (ex: `https://print-collect-api.onrender.com`)
6. Clique em **"Deploy"** e aguarde o deploy finalizar!

---

## Passo 4: Atualizar CORS no Render

1. No Render, clique no seu serviço (`print-collect-api`)
2. Vá para **Environment**
3. Edite a variável `CORS_ORIGINS` para a URL do seu painel Vercel:
   ```
   https://seu-projeto.vercel.app
   ```
4. Clique em **"Save Changes"** → aguarde o redeploy (~1 minuto)

---

## Pronto! 🎉

Agora você tem:
- **API**: rodando no Render (ex: `https://print-collect-api.onrender.com`)
- **Painel web**: rodando no Vercel (ex: `https://print-collect.vercel.app`)

Você pode acessar o painel, fazer login com `admin` / `admin123` e começar a usar o sistema!

---

## Instalar agente no cliente

Para cada cliente, siga as instruções no arquivo `agent/README.md`, mas use a URL da sua API no Render no arquivo `config.yaml` em vez de `http://localhost:8000`.

---

## Observação sobre o Render Gratuito

O plano gratuito do Render "dorme" após 15 minutos de inatividade. Quando um cliente acessar pela primeira vez, pode levar ~30 segundos para "acordar". Depois disso, funciona perfeitamente!
