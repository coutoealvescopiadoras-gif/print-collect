import ssl
import pg8000.native
from datetime import datetime, timedelta

now = datetime.now()

ctx = ssl.create_default_context()
conn = pg8000.native.Connection(
    "neondb_owner",
    password="npg_U9JHqTsc3LPu",
    host="ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech",
    database="neondb",
    ssl_context=ctx,
    port=5432,
)

print("=" * 100)
print("DIAGNÓSTICO BUG #1: POR QUE IMPRESSORA CEA (id=1) PAROU EM 14:09?")
print("Agora BSB:", now.strftime("%d/%m/%Y %H:%M:%S"))
print("=" * 100)

print("\n[1] TODOS OS AGENTES QUE RODARAM HOJE NO PC 'pc01' (loja CEA):")
pacs = conn.run(
    "SELECT id,client_id,hostname,name,agent_version,last_heartbeat,created_at "
    "FROM agents WHERE hostname LIKE '%%pc01%%' OR hostname LIKE '%%DESKTOP-E02OP26%%' OR id IN (11,18,10) "
    "ORDER BY last_heartbeat DESC NULLS LAST"
)
for r in pacs:
    a_id, c_id, host, name, ver, hb_utc, created = r
    hb_bsb_str = "NENHUM ainda"
    mins_ago = -1
    if hb_utc:
        hb_bsb = hb_utc - timedelta(hours=3)
        hb_bsb_str = hb_bsb.strftime("%d/%m %H:%M:%S")
        mins_ago = int((datetime.utcnow() - hb_utc).total_seconds() / 60)
    print(f"   ag_id={a_id:>2} | cliente_id={c_id:>3} | host={host} | {name}")
    print(f"          v{ver} criado:{created.strftime('%d/%m %H:%M')}")
    print(f"          ultimo_heartbeat_BR = {hb_bsb_str}  (há {mins_ago if mins_ago>=0 else 'n/a'} min)")
    if a_id == 11 and mins_ago > 30:
        print(f"          🚨 >>> AGENTE 11 (CEA ORIGINAL) PAROU DE ENVIAR HB! <<<")
    if a_id == 18 and mins_ago < 30:
        print(f"          🟢 >>> AGENTE 18 (cleinte teste id=226) É O QUE ESTÁ RODANDO AGORA! <<<")

print("\n[2] READINGS DOS ÚLTIMOS 30 MINUTOS (pra ver se alguém está atualizando):")
r30 = conn.run(
    "SELECT r.id,r.printer_id,p.client_id,r.collected_at,r.pages_total,p.model,p.ip_address "
    "FROM readings r JOIN printers p ON r.printer_id=p.id "
    "WHERE r.collected_at > NOW() - INTERVAL '60 minutes' "
    "ORDER BY r.id DESC LIMIT 10"
)
if not r30:
    print("   NENHUMA reading nova nos últimos 60 minutos! BUG 2 + BUG1 SOMADOS.")
else:
    for r in r30:
        r_id, p_id, c_id, col_utc, pt, model, ip = r
        col_bsb = col_utc - timedelta(hours=3)
        print(f"   reading={r_id} pr={p_id} cli={c_id} col={col_bsb.strftime('%H:%M:%S')} pag={pt} m={model} ip={ip}")

print("\n[3] CLIENTES: id=1 (CEA teste) vs id=226 (cleinte teste CEA criado hoje):")
clis = conn.run("SELECT id,partner_id,name,client_code,created_at FROM clients WHERE id IN (1,226)")
for c in clis:
    c_id, p_id, name, code, created = c
    print(f"   cliente_id={c_id} parceiro={p_id} nome={name} codigo={code} criado={created.strftime('%d/%m %H:%M')}")

conn.close()
print("\n" + "=" * 100)
print("CONCLUSÃO PROVÁVEL:")
print("   👉 Você rodou o Wizard com o código 5HD692FL (cliente id=226 cleinte teste)")
print("      no MESMO PC da loja CEA (pc01), que já tinha o agente 11 configurado")
print("      para o cliente id=1 (CEA teste). O WIZARD SOBRESCREVEU o config.yaml!")
print("   👉 Por isso as tarefas agendadas que existiam no PC agora usam o TOKEN")
print("      do AGENTE 18 (cliente 226), não mais do agente 11 (CEA teste id=1).")
print("   👉 Resultado: impressora id=1 (CEA) para de receber coletas em 14:09 ❌")
print("   👉 + BUG #2 do backend: a coleta do agente 18 retorna HTTP200 mas não")
print("      grava nada no banco, então a impressora do cliente 226 também não aparece ❌")
print("   👉 2 bugs hoje, por isso tudo parecia parado! 😤")
print("=" * 100)
