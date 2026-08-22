import ssl
import pg8000.native
from datetime import datetime

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
print("PROVA DE FOGO - A IMPRESSORA RICOH ID=1 FOI ATUALIZADA NO CLIENTE ERRADO?")
print("Horário local Julio:", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
print("=" * 100)

print("\n[1] COMPARAÇÃO DOS 2 AGENTES IMPORTANTES:")
print("   - AGENTE 11  -> cliente_id=1 (cea copiadoras / teste loja velho)")
print("   - AGENTE 18  -> cliente_id=226 (cleinte teste novo parceiro CEA, criado AGORA)")
print()

ags = conn.run(
    "SELECT id,client_id,hostname,name,api_token,last_heartbeat,created_at,remote_ip "
    "FROM agents WHERE id IN (11,18) ORDER BY id"
)
for a in ags:
    print("-" * 95)
    print(f"  🧑 AGENTE ID = {a[0]} | client_id={a[1]} | NOME: {a[3]}")
    print(f"     hostname         : {a[2]}")
    print(f"     agent_token      : {str(a[4])[:20]}...")
    print(f"     last_heartbeat   : {a[5]} (UTC)")
    print(f"     criado_em        : {a[6]}")
    print(f"     IP remoto        : {a[7]}")
    if a[5]:
        diff = (datetime.utcnow() - a[5]).total_seconds() / 60
        print(f"     >>> heartbeat há {int(diff)} minutos atrás")

print("\n[2] IMPRESSORA ID=1 (RICOH SP 4510SF 192.168.15.220) - cliente DONO ORIGINAL id=1:")
p1 = conn.run(
    "SELECT id,client_id,ip_address,model,serial_number,created_at,last_seen,pages_total "
    "FROM printers WHERE id=1"
)
for r in p1:
    print("   id=%d client_id=%d ip=%s model=%s serial=%s last_seen=%s pages_total=%s" % (
        r[0],r[1],r[2],r[3],r[4],r[6],r[7]
    ))
    if r[6]:
        diff = (datetime.utcnow() - r[6]).total_seconds() / 60
        print(f"   >>> last_seen há {int(diff)} minutos atrás. SE <= 30 MIN -> ATUALIZADA AGORA PELO WIZARD TESTE!")

print("\n[3] ÚLTIMAS 3 READINGS DA IMPRESSORA ID=1 (por collected_at desc):")
rds = conn.run(
    "SELECT r.id,r.printer_id,p.client_id,c.name,r.collected_at,r.total_counter,r.pages_total "
    "FROM readings r LEFT JOIN printers p ON p.id=r.printer_id LEFT JOIN clients c ON c.id=p.client_id "
    "WHERE r.printer_id=1 ORDER BY r.id DESC LIMIT 3"
)
for r in rds:
    print(f"   reading_id={r[0]} printer={r[1]} cliente=({r[2]}){r[3]} coletado_em={r[4]} total={r[5]}")

print("\n[4] IMPRESSORAS client_id=226 (CLIENTE NOVO TESTE):")
imp226 = conn.run("SELECT id,client_id,ip_address,model,created_at,last_seen FROM printers WHERE client_id=226")
print(f"   Quantidade: {len(imp226)}")
if len(imp226)==0:
    print("   ❌ NÃO EXISTE NENHUMA IMPRESSORA NO CLIENTE ID=226! (A reading do wizard não foi para cá...)")

print("\n[5] READINGS client_id=226:")
r226 = conn.run(
    "SELECT r.id,r.printer_id,p.client_id,r.collected_at "
    "FROM readings r LEFT JOIN printers p ON p.id=r.printer_id WHERE p.client_id=226 ORDER BY r.id DESC"
)
print(f"   Quantidade readings client=226: {len(r226)}")
if len(r226)==0:
    print("   ❌ NÃO EXISTEM READINGS NO CLIENTE ID=226!")

conn.close()
print("\n" + "=" * 100)
