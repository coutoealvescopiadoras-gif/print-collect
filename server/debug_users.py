import ssl
import pg8000.native

PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"

ssl_ctx = ssl.create_default_context()
conn = pg8000.native.Connection(PG_USER, password=PG_PASS, host=PG_HOST, database=PG_DB, ssl_context=ssl_ctx)

print("=" * 80)
print("DEBUG RÁPIDO - USUÁRIOS (para login SuperAdmin teste local)")
print("=" * 80)

try:
    r = conn.run("SELECT id, email, username, role, active FROM users ORDER BY id ASC")
    for row in r:
        print(f"id={row[0]} | email={row[1]!r} | user={row[2]!r} | role={row[3]!r} | active={row[4]}")
except Exception as e:
    print(f"ERRO: {e}")

print("\n[1] Total clientes no banco (4 que ja sabiamos):")
r = conn.run("SELECT id, name, partner_id, client_code FROM clients ORDER BY id")
for row in r:
    print(f"  client id={row[0]} name={row[1]!r} partner_id={row[2]} code={row[3]}")

conn.close()
