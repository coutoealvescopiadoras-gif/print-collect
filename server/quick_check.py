import ssl
import pg8000.native

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
print("QUICK CHECK NEON (pg8000 puro)")
print("=" * 100)

print("\n[1] Impressoras com serial T597H301772 (RICOH SP 4510SF 192.168.15.220):")
for row in conn.run(
    "SELECT id,client_id,ip_address,model,serial_number,created_at,last_seen FROM printers WHERE serial_number ILIKE 'T597H301772'"
):
    print("   ", row)

print("\n[2] Impressoras criadas HOJE (created_at >= 2026-08-11 00:00 UTC):")
for row in conn.run(
    "SELECT id,client_id,ip_address,model,created_at FROM printers WHERE created_at >= '2026-08-11' ORDER BY id DESC"
):
    print("   ", row)

print("\n[3] Agentes últimos 5 (por id desc):")
for row in conn.run(
    "SELECT id,client_id,hostname,last_heartbeat,created_at FROM agents ORDER BY id DESC LIMIT 5"
):
    print("   ", row)

print("\n[4] Readings últimas 5 (por id desc):")
for row in conn.run(
    "SELECT id,printer_id,pages_total,pages_bw,pages_color,created_at FROM readings ORDER BY id DESC LIMIT 5"
):
    print("   ", row)

print("\n[5] Último heartbeat de agent.id=17 (aqui na empresa Julio, pc01):")
for row in conn.run(
    "SELECT id,client_id,hostname,last_heartbeat FROM agents WHERE id=17"
):
    print("   ", row)

conn.close()
