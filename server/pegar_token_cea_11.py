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
print("TOKEN do AGENTE id=11 (cea copiadoras cliente id=1)")
print("=" * 100)

rows = conn.run(
    "SELECT id,client_id,name,hostname,api_token,last_heartbeat FROM agents WHERE id=11"
)
for r in rows:
    print(f"id={r[0]}, client_id={r[1]}, name={r[2]}, hostname={r[3]}")
    print(f"TOKEN = {r[4]}")
    print(f"ultimo heartbeat = {r[5]}")

print("\n[2] Impressora id=1 (cea copiadoras ip 192.168.15.220) HORARIO ATUAL last_seen:")
for r in conn.run(
    "SELECT id,client_id,ip_address,model,last_seen FROM printers WHERE id=1"
):
    print("   ", r)

conn.close()
