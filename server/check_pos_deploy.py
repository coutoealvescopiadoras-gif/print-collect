"""
CHECK RAPIDO:
1) Verifica se POSTO FALCAO (id=225) tem impressora criada agora em printers(client_id=225)
2) Mostra lista clientes como seria a nova listagem (4 clientes, com Posto Falcao)
3) Lista ultimos heartbeats dos agentes.
Usa pg8000 puro (provado funcionar, sem dependencia nenhuma alem de pg8000).
"""
import ssl, pg8000.native

PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"

ssl_ctx = ssl.create_default_context()
conn = pg8000.native.Connection(PG_USER, password=PG_PASS, host=PG_HOST, database=PG_DB, ssl_context=ssl_ctx)

def q(sql, params=None, label=""):
    print("\n" + "=" * 80)
    print(label)
    print("=" * 80)
    try:
        rows = conn.run(sql, *params) if params else conn.run(sql)
        if not rows:
            print("   (nenhuma linha - VAZIO)")
            return []
        for r in rows:
            print("   -", list(r))
        return rows
    except Exception as e:
        print(f"   ❌ ERRO: {e}")
        return []

# [1] Clientes (4, inclui Posto Falcao 225 parceiro id=5)
q("SELECT id, name, partner_id, client_code FROM clients ORDER BY partner_id NULLS FIRST, name ASC",
  label="[1] Lista CLIENTES (Posto Falcao id=225 com partner_id=5 aparece aqui?)")

# [2] Impressoras do Posto Falcao (client_id=225)
q("SELECT id, client_id, ip_address, model, serial_number, pages_total, last_seen, updated_at FROM printers WHERE client_id = 225 ORDER BY id DESC",
  label="[2] Impressoras CRIADAS para Posto Falcao (client_id=225). DEVERIA ser >= 1 se voce rodou run-once pareado aqui na empresa!")

# [3] Total printers cadastradas
q("SELECT id, client_id, ip_address, model FROM printers ORDER BY id ASC",
  label="[3] Lista TODAS impressoras cadastradas.")

# [4] Agentes Posto Falcao heartbeats ultimos
q("SELECT id, client_id, name, hostname, api_token, last_heartbeat FROM agents WHERE client_id=225 ORDER BY id ASC",
  label="[4] Agentes do Posto Falcao (client_id=225) - last heartbeat?")

conn.close()
print("\n\nCHECK FINALIZADO")
