import ssl
import pg8000.native
from datetime import datetime, timedelta

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
print("DIAGNÓSTICO - CLIENTE FICTÍCIO NOVO TESTE WIZARD CEA LOJA")
print("=" * 100)

print("\n[1] CLIENTES NOVOS criados HOJE (após 11/08 12:00) com partner_id=5 CEA:")
rows = conn.run(
    "SELECT id,name,partner_id,client_code,created_at "
    "FROM clients WHERE created_at >= '2026-08-11 12:00:00' AND partner_id=5 "
    "ORDER BY created_at DESC"
)
h = ["id","name","partner_id","client_code","created_at"]
novo_cliente_id = None
novo_cliente_name = None
novo_codigo = None
for r in rows:
    print("-" * 90)
    for k,v in zip(h,r):
        print(f"   {k:>12s} = {v}")
    if novo_cliente_id is None:
        novo_cliente_id = r[0]
        novo_cliente_name = r[1]
        novo_codigo = r[3]

if not novo_cliente_id:
    print("\n   >>> Nenhum cliente novo parceiro CEA criado depois de 12h hoje? Espera mais um pouco...")
    print("   >>> Ou talvez login parceiro não usou o campo revenda CEA corretamente? Vamos buscar os últimos clientes de qualquer parceiro:")
    rows2 = conn.run(
        "SELECT id,name,partner_id,client_code,created_at FROM clients ORDER BY created_at DESC LIMIT 5"
    )
    print("\n   [1b] ÚLTIMOS 5 CLIENTES CRIADOS NO BANCO (order by created_at desc):")
    for r in rows2:
        print("   -", r)
        if novo_cliente_id is None and r[1] and ("TESTE" in str(r[1]).upper() or "WIZARD" in str(r[1]).upper() or "FICT" in str(r[1]).upper() or "LOJA" in str(r[1]).upper()):
            novo_cliente_id = r[0]
            novo_cliente_name = r[1]
            novo_codigo = r[3]

print("\n" + "=" * 100)
print(f"[2] CLIENTE IDENTIFICADO: {novo_cliente_name} id={novo_cliente_id} código={novo_codigo}")
print("=" * 100)

if novo_cliente_id:
    print("\n[3] AGENTES PAREADOS COM ESSE NOVO CLIENTE (client_id=%d):" % novo_cliente_id)
    ags = conn.run(
        "SELECT id,client_id,hostname,name,last_heartbeat,agent_token,remote_ip,created_at "
        "FROM agents WHERE client_id=%d ORDER BY created_at DESC" % novo_cliente_id
    )
    print(f"   >>> Quantidade: {len(ags)} agentes pareados.")
    if len(ags)==0:
        print("   >>> NENHUM AGENTE PAREADO AINDA (wizard pode ter falhado no pareamento?)")
    ag_id = None
    for a in ags:
        print("   - agente_id:",a[0],"hostname:",a[2],"name:",a[3],"last_hb:",a[4],"ip_remoto:",a[6])
        if ag_id is None:
            ag_id = a[0]

    print("\n[4] IMPRESSORAS VINCULADAS A ESSE NOVO CLIENTE (client_id=%d):" % novo_cliente_id)
    imp = conn.run(
        "SELECT id,client_id,ip_address,model,serial_number,created_at,last_seen "
        "FROM printers WHERE client_id=%d ORDER BY created_at DESC" % novo_cliente_id
    )
    print(f"   >>> Quantidade impressoras: {len(imp)}")
    if len(imp)==0:
        print("   >>> ZERO IMPRESSORAS. Duas possibilidades:")
        print("       (a) Nenhuma reading foi enviada ainda (wizard não terminou passo 3/4 scan+envio)")
        print("       (b) A impressora JÁ EXISTE com MESMO IP + SERIAL/MODEL e ela fez UPDATE na impressora ORIGINAL (cliente id=1)!")
    for i in imp:
        print("   - id:",i[0],"ip:",i[2],"modelo:",i[3],"serial:",i[4],"criada:",i[5],"visto:",i[6])

    print("\n[5] IMPRESSORA id=1 (RICOH 192.168.15.220 cliente id=1 cea copiadoras) - ÚLTIMO last_seen:")
    p1 = conn.run("SELECT id,client_id,ip_address,model,serial_number,created_at,last_seen FROM printers WHERE id=1")
    for r in p1:
        print("   id=%d client_id=%d ip=%s model=%s serial=%s last_seen=%s" % (r[0],r[1],r[2],r[3],r[4],r[6]))
        if ag_id:
            print("   >>> Vamos checar se houve UPDATE nessa impressora id=1 recentemente — se sim, a regra de upsert atualizou a impressora original e NÃO CRIOU duplicada!")

    print("\n[6] READINGS NOVAS das últimas 30min (vamos ver qual printer_id foi salvo):")
    rds = conn.run(
        "SELECT r.id,r.printer_id,p.client_id,c.name as cliente_name,p.ip_address,p.model,r.collected_at,r.total_counter "
        "FROM readings r LEFT JOIN printers p ON p.id=r.printer_id LEFT JOIN clients c ON c.id=p.client_id "
        "WHERE r.collected_at >= NOW() - INTERVAL '30 minutes' ORDER BY r.id DESC LIMIT 5"
    )
    for r in rds:
        print("   - reading_id=%d printer_id=%d cliente(id=%d %s) ip=%s model=%s coletada_em=%s total=%s" % (r[0],r[1],r[2],r[3],r[4],r[5],r[6],r[7]))

conn.close()
print("\n" + "=" * 100)
