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
print("QUICK CHECK 3 - COLUNAS agents E printers client_id=225")
print("=" * 100)

print("\n[1] Colunas da tabela agents:")
for c in conn.run(
    "SELECT column_name,data_type FROM information_schema.columns WHERE table_name='agents' ORDER BY ordinal_position"
):
    print("   ", c[0], "->", c[1])

print("\n[2] Agente id=17 (Julio empresa pc01) - TODAS as colunas:")
cols_agents = ",".join(
    [
        c[0]
        for c in conn.run(
            "SELECT column_name FROM information_schema.columns WHERE table_name='agents' ORDER BY ordinal_position"
        )
    ]
)
for r in conn.run(f"SELECT {cols_agents} FROM agents WHERE id=17"):
    for k, v in zip(cols_agents.split(","), r):
        print("   ", k, "=", v)

print("\n[3] printers client_id=225 (Posto Falcao) TODAS colunas:")
cols_printers = ",".join(
    [
        c[0]
        for c in conn.run(
            "SELECT column_name FROM information_schema.columns WHERE table_name='printers' ORDER BY ordinal_position"
        )
    ]
)
rows = conn.run(f"SELECT {cols_printers} FROM printers WHERE client_id=225 ORDER BY id DESC")
print("   Total =", len(rows))
for r in rows:
    print("   ", list(zip(cols_printers.split(","), r)))

conn.close()
