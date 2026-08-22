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
print("BUSCA COMPLETA BANCO TODO - ULTIMAS 15 MINUTOS (17:20 UTC = 14:20 BSB)")
print("=" * 100)

print("\n[1] TODAS AS IMPRESSORAS serial T597H301772 (RICOH loja CEA) - MESMO SERIAL):")
serials = conn.run(
    "SELECT id,client_id,c.name as cliente, partner_id, ip_address,model,serial_number,created_at,last_seen "
    "FROM printers p LEFT JOIN clients c ON c.id=p.client_id WHERE p.serial_number ILIKE '%T597H301772%' OR p.ip_address='192.168.15.220'"
)
if len(serials)==0:
    print("   Nenhuma?")
for r in serials:
    print(f"  printer_id={r[0]} client={r[1]}({r[2]}) partner_id={r[3]} ip={r[4]} model={r[5]} serial={r[6]} criada={r[7]} seen={r[8]}")

print("\n[2] TODAS AS IMPRESSORAS last_seen >= 17:28 UTC (14:28 BSB) — WIZARD TIME:")
imp = conn.run(
    "SELECT p.id,p.client_id,c.name as cname,p.ip_address,p.model,p.last_seen "
    "FROM printers p LEFT JOIN clients c ON c.id=p.client_id WHERE p.last_seen >= '2026-08-11 17:28:00' OR p.created_at >= '2026-08-11 17:28:00' ORDER BY p.last_seen DESC"
)
print(f"   Quantidade: {len(imp)}")
for r in imp:
    print(f"   printer={r[0]} client_id={r[1]}({r[2]}) ip={r[3]} model={r[4]} last_seen={r[5]}")

print("\n[3] READINGS coletadas >= 17:28 UTC (14:28 BSB):")
rds = conn.run(
    "SELECT r.id,r.printer_id,p.client_id,c.name,p.ip_address,r.collected_at,r.pages_total FROM readings r "
    "LEFT JOIN printers p ON p.id=r.printer_id LEFT JOIN clients c ON c.id=p.client_id "
    "WHERE r.collected_at >= '2026-08-11 17:28:00' ORDER BY r.id DESC"
)
print(f"   Quantidade readings: {len(rds)}")
if len(rds)==0:
    print("   ❌ NÃO EXISTEM READINGS NOVAS! BUG: o POST /api/agent/report RETORNOU processed_ok=1 MAS NAO GRAVOU READINGS!")
else:
    for r in rds:
        print(f"   reading_id={r[0]} printer={r[1]} client_id={r[2]}({r[3]}) ip={r[4]} hora={r[5]} pages={r[6]}")

print("\n[4] HEARTBEATS agentes atualizados >= 17:28:")
ag = conn.run("SELECT id,client_id,name,last_heartbeat,hostname FROM agents WHERE last_heartbeat >= '2026-08-11 17:28:00'")
for r in ag:
    print(f"   ag={r[0]} client_id={r[1]} name={r[2]} hb={r[3]}")

conn.close()
print("\n" + "=" * 100)
