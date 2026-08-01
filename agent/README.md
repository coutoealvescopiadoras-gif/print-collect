# Coletor local — Print Collect

Programa Python que roda **no PC ou servidor do cliente**, na rede local onde estão as impressoras. Ele:

1. Varre a rede via **SNMP** (ou consulta IPs fixos)
2. Coleta modelo, serial, contadores e nível de toner
3. Envia os dados para a **API central**, que grava no **Supabase**

## Requisitos no cliente

### Fluxo recomendado

- Windows com permissão de administrador para executar `PrintCollectSetup.exe`
- Acesso de rede às impressoras (porta UDP 161 — SNMP)
- SNMP habilitado nas impressoras (community `public` na maioria dos casos)
- Saída HTTP/HTTPS para o servidor da API

### Fluxo alternativo

- Python 3.10+ somente quando usar o fallback `install.ps1`

## Instalação rápida

### Windows standalone

No painel, baixe o pacote do agente. O ZIP deve conter:

- `PrintCollectSetup.exe`
- `config.yaml`

Passos:

1. Extraia o ZIP em uma pasta local
2. Execute `PrintCollectSetup.exe` como administrador
3. Clique em `Proximo` ate concluir
4. O instalador copia automaticamente o `config.yaml` do ZIP com a URL e o token do agente
5. O agente inicia sozinho e tenta descobrir a sub-rede local quando `snmp.subnets` estiver vazio
6. Edite `C:\Program Files\PrintCollect\config.yaml` apenas se quiser forcar IPs, sub-redes ou outra community SNMP

O instalador cria uma tarefa agendada para iniciar o agente automaticamente quando o Windows ligar.

Detalhes do build em `agent/windows/README.md`.

### Desenvolvimento / fallback Python

```bash
cd agent
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
cp config.example.yaml config.yaml
```

Edite `config.yaml`:

```yaml
server_url: "https://sua-api.com"    # URL da API conectada ao Supabase
agent_token: "token-do-painel"       # Painel > Agentes > Novo agente
snmp:
  subnets:
    - "192.168.1.0/24"              # Rede local do cliente
```

## Comandos

```bash
# Testar conexão com o servidor
print-collect --test

# Uma coleta de teste
print-collect --once

# Rodar continuamente (a cada 15 min por padrão)
print-collect

# Usar config em outro caminho
print-collect -c /opt/print-collect/config.yaml
```

## Instalação como serviço

**Linux:**
```bash
sudo bash install.sh
sudo nano /opt/print-collect/config.yaml
sudo cp print-collect.service /etc/systemd/system/
sudo systemctl enable --now print-collect
sudo journalctl -u print-collect -f
```

**Windows:**
```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
# Fluxo alternativo que ainda exige Python 3.10+
```

## Fluxo de dados

```
Impressoras (rede local)
        │ SNMP
        ▼
  Coletor Python  ──HTTP──▶  API FastAPI  ──▶  Supabase (PostgreSQL)
  (este programa)              (servidor)         (banco na nuvem)
```

## Solução de problemas

| Problema | Solução |
|----------|---------|
| Nenhuma impressora encontrada | Verifique `snmp.subnets` e se SNMP está ativo na impressora |
| Servidor inacessível | Confirme `server_url` e firewall |
| Token inválido | Crie novo agente no painel e atualize `agent_token` |
| Varredura lenta | Use `snmp.ips` com IPs fixos em vez de /24 inteiro |

## Habilitar SNMP nas impressoras

- **HP:** Painel web da impressora > Networking > SNMP > Enable
- **Canon:** Configurações > Rede > SNMP > Ativo
- **Brother:** Admin > Network > Protocol > SNMP > v1/v2c Enable

Community padrão: `public` (pode ser alterada no `config.yaml`).
