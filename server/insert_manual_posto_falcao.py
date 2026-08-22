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
print("TESTE FINAL - INSERT MANUAL de impressora RICOH 220 para Posto Falcao id=225")
print("MÉTODO: pg8000 NATIVO (sem SQLAlchemy, sem routes.py, 100% RAW SQL)")
print("=" * 100)

print("\n[1] ANTES do INSERT: printers client_id=225:")
rows_before = conn.run(
    "SELECT id,client_id,ip_address,model,serial_number,ignored,active FROM printers WHERE client_id=225"
)
print(f"    Total = {len(rows_before)}")
for r in rows_before:
    print("    ", r)

print("\n[2] EXECUTANDO INSERT MANUAL (sem SQLAlchemy intermediário):")
conn.run(
    """
    INSERT INTO printers (client_id, ip_address, mac_address, serial_number, model, manufacturer, status, pages_total, pages_bw, pages_color, ignored, active, last_seen, created_at, updated_at)
    VALUES (:cid, :ip, :mac, :serial, :model, :manuf, :status, :pt, :pbw, :pc, FALSE, TRUE, NOW(), NOW(), NOW())
    """,
    cid=225,
    ip="192.168.15.220",
    mac="A4:3B:F5:2F:2E:53",
    serial="T597H301772",
    model="RICOH SP 4510SF",
    manuf="Ricoh",
    status="online",
    pt=79288,
    pbw=79288,
    pc=0,
)
conn.run("COMMIT")
print("    ✅ INSERT e COMMIT executados via pg8000! (sem erro)")

print("\n[3] DEPOIS do INSERT (mesma query):")
rows_after = conn.run(
    "SELECT id,client_id,ip_address,model,serial_number,ignored,active,created_at FROM printers WHERE client_id=225"
)
print(f"    Total = {len(rows_after)}")
for r in rows_after:
    print("    ", r)

print("\n[4] Última impressora criada GERAL (order by id desc limit 1):")
for r in conn.run(
    "SELECT id,client_id,ip_address,model,created_at FROM printers ORDER BY id DESC LIMIT 1"
):
    print("    ", r)

conn.close()
print("\nFIM. Se apareceu 1 linha no item [3], o INSERT MANUAL funcionou!")
