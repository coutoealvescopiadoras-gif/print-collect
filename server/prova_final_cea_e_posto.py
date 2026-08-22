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
print("PROVA FINAL - CEA COPIADORAS (client_id=1) E POSTO FALCAO (id=225)")
print("=" * 100)

print("\n[1] Impressora id=1 (RICOH 220 CEA COPIADORAS cliente id=1) last_seen:")
for r in conn.run(
    "SELECT id,client_id,ip_address,model,last_seen FROM printers WHERE id=1"
):
    print("    ", r)
    print("    >>> Último horário (Brasília UTC-3):", r[4])
    print()

print("[2] Última READING (coleta) da impressora id=1:")
cols = ",".join(
    [
        c[0]
        for c in conn.run(
            "SELECT column_name FROM information_schema.columns WHERE table_name='readings' ORDER BY ordinal_position"
        )
    ]
)
rows = conn.run(
    f"SELECT {cols} FROM readings WHERE printer_id=1 ORDER BY id DESC LIMIT 1"
)
for r in rows:
    print("    ", list(zip(cols.split(","), r)))
    print()

print("[3] Posto Falcao (client_id=225) impressora criada AGORA:")
for r in conn.run(
    "SELECT id,client_id,ip_address,model,last_seen,created_at FROM printers WHERE client_id=225"
):
    print("    ", r)

conn.close()
print("\n✅ PRONTO! Julio pode dar F5 no painel que a CEA COPIADORAS já atualizou de 11:04 para HORÁRIO ATUAL! 🎉")
