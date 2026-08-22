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

print("=" * 90)
print("🎫 PEGANDO CÓDIGO DO CLIENTE CEA COPIADORAS (id=1) PARA WIZARD AGORA NA LOJA:")
print("=" * 90)
r = conn.run("SELECT id,name,partner_id,client_code,created_at FROM clients WHERE id=1")
headers = ["id","name","partner_id","client_code (CODIGO 8 DIGITOS)","created_at"]
for row in r:
    print("")
    for k,v in zip(headers, row):
        print(f"  {k:>35s} = {v}")
    codigo = row[3]
    print("")
    print("=" * 90)
    print(f"👉 NO WIZARD NA LOJA CEA, DIGITE ESSE CÓDIGO: {codigo}")
    print("=" * 90)

print("\n🎫 (Posto Falcão código para referência amanhã: LWFTASJN — NÃO USE ESSE HOJE NA CEA!)")
conn.close()
