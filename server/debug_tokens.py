import ssl
import pg8000.native

PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"

ssl_ctx = ssl.create_default_context()
conn = pg8000.native.Connection(PG_USER, password=PG_PASS, host=PG_HOST, database=PG_DB, ssl_context=ssl_ctx)

# Busca os 2 agentes do Posto Falcão e os TOKENS COMPLETOS + ultimos readings (se existirem)
print("=" * 90)
print("TOKEN COMPLETO dos agentes Posto Falcao (id=225) + readings")
print("=" * 90)

r = conn.run(
    "SELECT id, client_id, name, hostname, api_token, last_heartbeat FROM agents "
    "WHERE client_id = 225 ORDER BY id ASC"
)
print(f"\nAgentes Posto Falcao (client_id=225): {len(r)} encontrados:")
tokens = []
for row in r:
    print(f"\n   agent_id={row[0]} name={row[2]!r} host={row[3]!r}")
    print(f"   ✅ TOKEN COMPLETO = '{row[4]}'")
    print(f"   last_heartbeat = {row[5]}")
    tokens.append((row[0], row[4]))

for aid, tok in tokens:
    print(f"\n--- READINGS (impressoes salvas) do agente id={aid}:")
    rr = conn.run(
        "SELECT rd.id, rd.created_at, rd.pages_total, p.id, p.client_id, p.ip_address, p.model "
        "FROM readings rd "
        "JOIN printers p ON p.id = rd.printer_id "
        "WHERE p.client_id = (SELECT client_id FROM agents WHERE id = $1) "
        "ORDER BY rd.created_at DESC LIMIT 5",
        aid
    )
    if rr:
        for reading in rr:
            print(f"    reading id={reading[0]} created={reading[1]} pages={reading[2]} printer_id={reading[3]} cid={reading[4]} ip={reading[5]!r} model={reading[6]!r}")
    else:
        print("    (0 readings - NUNCA FOI CRIADA UMA READING PARA ESTE CLIENTE!)")

print("\n--- Impressoras diretamente client_id=225:")
rp = conn.run("SELECT id, client_id, ip_address, model, serial_number FROM printers WHERE client_id=225")
if rp:
    for p in rp:
        print(f"   printer id={p[0]} cid={p[1]} ip={p[2]!r} model={p[3]!r}")
else:
    print("   (0 impressoras - NENHUMA impressora salva no banco para Posto Falcao!)")

conn.close()
