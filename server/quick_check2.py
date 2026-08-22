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
print("QUICK CHECK + PEGAR TOKEN DO AGENTE 17")
print("=" * 100)

print("\n[1] Impressoras client_id=225 (Posto Falcao) — INCLUSIVE IGNORADAS:")
rows = conn.run(
    "SELECT id,client_id,ip_address,model,serial_number,ignored,created_at,last_seen FROM printers WHERE client_id=225 ORDER BY id DESC"
)
print("   Total =", len(rows))
for r in rows:
    print("   ", r)

print("\n[2] Agente id=17 (Julio empresa pc01):")
rows = conn.run(
    "SELECT id,client_id,hostname,agent_token,last_heartbeat FROM agents WHERE id=17"
)
for r in rows:
    print("   id=       ", r[0])
    print("   client_id=", r[1])
    print("   hostname= ", r[2])
    print("   TOKEN=    ", r[3])
    print("   last_hb=  ", r[4])

print("\n[3] Colunas da tabela readings (para nao errar mais):")
cols = conn.run(
    "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'readings' ORDER BY ordinal_position"
)
for c in cols:
    print("   ", c[0], "->", c[1])

print("\n[4] Readings últimas 3 (por id desc, sem created_at):")
rcols = ",".join([c[0] for c in cols])
try:
    for r in conn.run(f"SELECT {rcols} FROM readings ORDER BY id DESC LIMIT 3"):
        print("   ", r)
except Exception as e:
    print("   (erro leitura readings ultima hora):", str(e)[:200])

conn.close()
