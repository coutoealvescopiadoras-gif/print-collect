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
print("DIAGNÓSTICO BUG #1: POR QUE IMPRESSORA CEA PAROU EM 14:09?")
print("Agora BSB:", now.strftime("%d/%m/%Y %H:%M:%S"))
print("=" * 100)

print("\n[1] TODOS OS AGENTES RELEVANTES (id 11 = CEA antigo, id 18 = cleinte teste novo):")
pacs = conn.run(
    "SELECT id,client_id,hostname,name,last_heartbeat,created_at FROM agents WHERE id IN (10,11,18) ORDER BY last_heartbeat DESC NULLS LAST"
)
for r in pacs:
    a_id, c_id, host, name, hb_utc, created = r
    hb_bsb_str = "NENHUM ainda"
    mins_ago = -1
    if hb_utc:
        hb_bsb = hb_utc - timedelta(hours=3)
        hb_bsb_str = hb_bsb.strftime("%d/%m %H:%M:%S")
        mins_ago = int((datetime.utcnow() - hb_utc).total_seconds() / 60)
    print(f"   ag_id={a_id:>2} | cliente={c_id:>3} | host={host} | {name}")
    print(f"          criado em: {created.strftime('%d/%m %H:%M')}")
    print(f"          último HB BRASÍLIA = {hb_bsb_str}  (há {mins_ago if mins_ago>=0 else 'n/a'} minutos)")
    if a_id == 11 and mins_ago > 25:
        print(f"          🚨 >>> AGENTE 11 (CEA cliente 1) PAROU DE ATUALIZAR! NÃO É MAIS USADO NO PC!")
    if a_id == 18 and mins_ago < 25:
        print(f"          🟢 >>> AGENTE 18 (cliente 226 cleinte teste) É O AGENTE ATIVO NO PC AGORA!")

print("\n[2] ÚLTIMAS 8 READINGS:")
r8 = conn.run(
    "SELECT r.id, r.printer_id, p.client_id, r.collected_at, r.pages_total, p.model "
    "FROM readings r JOIN printers p ON r.printer_id=p.id "
    "ORDER BY r.id DESC LIMIT 8"
)
for r in r8:
    r_id, p_id, c_id, col_utc, pt, model = r
    col_bsb = col_utc - timedelta(hours=3)
    print(f"   reading={r_id} printer={p_id} cliente={c_id} coleta_BR={col_bsb.strftime('%d/%m %H:%M:%S')} pages={pt} m={model}")

print("\n[3] CLIENTE id=1 CEA teste vs id=226 cleinte teste:")
clis = conn.run("SELECT id,name,client_code FROM clients WHERE id IN (1,226)")
for c in clis:
    c_id, name, code = c
    print(f"   cliente {c_id}: '{name}'  código wizard = {code}")

print("\n[4] IMPRESSORAS CADASTRADAS NOS 2 CLIENTES:")
ips = conn.run("SELECT id,client_id,ip_address,model,created_at,last_seen FROM printers WHERE client_id IN (1,226) ORDER BY client_id,id")
for p in ips:
    p_id, c_id, ip, model, created, last_utc = p
    last_bsb = (last_utc - timedelta(hours=3)).strftime('%d/%m %H:%M') if last_utc else 'nunca'
    print(f"   impressora={p_id} cliente={c_id} ip={ip} {model} última_coleta_BR={last_bsb}")

conn.close()
print("\n" + "=" * 100)
print("HIPÓTESE CONFIRMADA SE ACIMA MOSTRAR AG11 PARADO E AG18 ATIVO:")
print("   * Wizard de hoje 14:30 usou código de cliente NOVO (5HD692FL = cliente 226)")
print("     no MESMO PC (pc01) que já tinha o agente 11 (cliente CEA id=1).")
print("   * O Wizard SOBRESCREVEU C:\\ProgramData\\PrintCollect\\config.yaml")
print("     com o TOKEN do agente 18 (226), apagando o token do agente 11 (CEA 1).")
print("   * Resultado 1: impressora CEA id=1 (cliente1) NÃO RECEBE COLETAS MAIS ❌")
print("   * Resultado 2: impressora cliente 226 também NÃO APARECE (bug #2 commit backend) ❌")
print("   => POR ISSO F5 mostra só 14:09 até hoje! 😤")
print("=" * 100)
