# Configurar Envio de E-mails com Gmail

Este guia explica como configurar o Print Collect para enviar alertas por e-mail usando uma conta do Gmail.

## Passo 1: Habilitar 2FA na sua conta Google

1. Acesse https://myaccount.google.com/security
2. Na seção "Como fazer login no Google", clique em "Verificação em duas etapas"
3. Siga as instruções para habilitar a verificação em duas etapas

## Passo 2: Criar uma App Password

1. Acesse https://myaccount.google.com/apppasswords
   - (Você precisa ter a verificação em duas etapas habilitada para ver esta página)
2. Selecione:
   - **Selecione o app**: Outro (nome personalizado)
   - **Nome**: Print Collect
3. Clique em "Gerar"
4. Copie a senha de 16 caracteres que aparece (será algo como `abcd efgh ijkl mnop`)
5. Guarde essa senha em local seguro - você precisará dela no arquivo `.env`

## Passo 3: Configurar o arquivo .env

Edite o arquivo `server/.env` e adicione as seguintes linhas no final:

```env
# Email configuration (Gmail)
MAIL_USERNAME=seu-email@gmail.com
MAIL_PASSWORD=sua-app-password-aqui
MAIL_FROM=seu-email@gmail.com
MAIL_PORT=587
MAIL_SERVER=smtp.gmail.com
MAIL_STARTTLS=true
MAIL_SSL_TLS=false
MAIL_USE_CREDENTIALS=true
MAIL_VALIDATE_CERTS=true

# Email notifications (comma-separated list)
ALERT_EMAIL_RECIPIENTS=email1@dominio.com,email2@dominio.com
```

Substitua:
- `seu-email@gmail.com` pelo seu e-mail do Gmail
- `sua-app-password-aqui` pela App Password que você gerou
- `email1@dominio.com,email2@dominio.com` pelos e-mails que receberão os alertas

## Passo 4: Reiniciar o servidor

Reinicie o servidor FastAPI para aplicar as configurações:
```bash
# Se estiver usando o servidor local
# (No terminal) Ctrl+C para parar, depois execute novamente:
cd server
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

## Pronto!

Agora o sistema enviará e-mails de alerta automaticamente quando:
- Toner de uma impressora ficar baixo
- Uma impressora ficar offline
- Outros alertas configurados

---

## Outros provedores de e-mail

Se você não quiser usar o Gmail, pode configurar outros provedores:

### Outlook/Hotmail
```env
MAIL_SERVER=smtp.office365.com
MAIL_PORT=587
MAIL_STARTTLS=true
```

### Yahoo
```env
MAIL_SERVER=smtp.mail.yahoo.com
MAIL_PORT=587
MAIL_STARTTLS=true
```

### Provedor próprio (SMTP)
Basta ajustar as configurações de `MAIL_SERVER` e `MAIL_PORT` de acordo com o seu provedor.
