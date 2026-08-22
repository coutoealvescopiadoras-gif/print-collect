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
print("BUSCA RÁPIDA - ULTIMAS 2 READINGS NOVAS & ULTIMAS IMPRESSORAS CRIADAS")
print("=" * 100)

print("\n[1] READINGS novas (order by id desc, 10 ultimas):")
r = conn.run(
    "SELECT r.id, r.printer_id, r.collected_at, r.pages_total FROM readings r ORDER BY r.id DESC LIMIT 10"
)
for row in r:
    print(f"   reading_id={row[0]} printer_id={row[1]} collected={row[2]} pages={row[3]}")

print("\n[2] IMPRESSORAS novas (order by id desc, 10 ultimas):")
p = conn.run(
    "SELECT p.id, p.client_id, p.ip_address, p.model, p.created_at, p.last_seen FROM printers p ORDER BY p.id DESC LIMIT 10"
)
for row in p:
    print(f"   printer_id={row[0]} client_id={row[1]} ip={row[2]} model={row[3]} created={row[4]} seen={row[5]}")

print("\n[3] AGENTE 18 (client_id=226 cleinte teste) - last heartbeat agora:")
a = conn.run("SELECT id, client_id, last_heartbeat FROM agents WHERE id=18")
for row in a:
    print(f"   agente={row[0]} client_id={row[1]} hb={row[2]}")

print("\n[4] CLIENTE id=226 cleinte teste (conferencia):")
c = conn.run("SELECT id, name, partner_id, client_code FROM clients WHERE id=226")
for row in c:
    print(f"   id={row[0]} name={row[1]} partner_id={row[2]} code={row[3]}")

conn.close()
print("\nFIM.")
