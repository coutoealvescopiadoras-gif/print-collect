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
print("CONSULTA PÓS POST SIMULADO (agora!): IMPRESSORA CRIADA EM client_id=226?")
print("=" * 100)

print("\n[1] IMPRESSORAS client_id=226 (cleinte teste):")
r = conn.run(
    "SELECT id,client_id,ip_address,model,serial_number,created_at,last_seen "
    "FROM printers WHERE client_id=226 ORDER BY id DESC"
)
print(f"Quantidade: {len(r)}")
if len(r)==0:
    print("  ❌ ❌ ❌ NÃO EXISTE NENHUMA IMPRESSORA AQUI!")
    print("BUG CONFIRMADO: rota RETORNA processed_ok=1 status=ok MAS NAO GRAVA NADA NO BANCO NEON!")
    print("db.commit() ESTÁ FALHANDO (serverless reutiliza sessao/conn poolado!)")
else:
    for row in r:
        print(f"  ✅ printer_id={row[0]} cliente_id={row[1]} ip={row[2]} model={row[3]} serial={row[4]} criada={row[5]}")

print("\n[2] READINGS novas (ÚLTIMAS 5 readings, order by id desc):")
rds = conn.run(
    "SELECT r.id,r.printer_id,p.client_id,c.name as cliente,p.ip_address,r.collected_at,r.pages_total "
    "FROM readings r LEFT JOIN printers p ON p.id=r.printer_id LEFT JOIN clients c ON c.id=p.client_id "
    "ORDER BY r.id DESC LIMIT 5"
)
for row in rds:
    print(f"  reading_id={row[0]} printer={row[1]} cliente={row[3]}({row[2]}) ip={row[4]} hora={row[5]} pages={row[6]}")

print("\n[3] IMPRESSORAS com serial=T597H301772 (RICOH loja CEA) em QUALQUER cliente:")
serials = conn.run(
    "SELECT p.id,p.client_id,c.name as cliente,p.ip_address,p.model,p.created_at FROM printers p "
    "LEFT JOIN clients c ON c.id=p.client_id WHERE p.serial_number ILIKE '%T597H301772%'"
)
print(f"Quantidade: {len(serials)}")
for row in serials:
    print(f"  printer_id={row[0]} cliente={row[1]}({row[2]}) ip={row[3]} model={row[4]} criada={row[5]}")

print("\n[4] IMPRESSORAS ip='192.168.15.220' em QUALQUER cliente:")
ips = conn.run(
    "SELECT p.id,p.client_id,c.name as cliente,p.ip_address,p.model,p.created_at FROM printers p "
    "LEFT JOIN clients c ON c.id=p.client_id WHERE p.ip_address='192.168.15.220'"
)
for row in ips:
    print(f"  printer_id={row[0]} cliente={row[1]}({row[2]}) ip={row[3]} model={row[4]} criada={row[5]}")

conn.close()
print("\n" + "=" * 100)
