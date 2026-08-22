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

r = conn.run("SELECT id,client_id,hostname,name,api_token,last_heartbeat FROM agents WHERE id=18")
for row in r:
    print("AGENTE_ID =", row[0])
    print("CLIENT_ID =", row[1])
    print("HOSTNAME  =", row[2])
    print("NAME      =", row[3])
    print("API_TOKEN =", row[4])
    print("HEARTBEAT =", row[5])
    with open("C:\\Users\\Julio\\Desktop\\print-collect\\server\\token_agente_18.txt", "w", encoding="utf-8") as f:
        f.write(str(row[4]))
    print("Salvo em token_agente_18.txt")

conn.close()
