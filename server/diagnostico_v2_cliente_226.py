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
print("DIAGNÓSTICO v2 - CLIENTE FICTÍCIO NOVO id=226 (cleinte teste)")
print("=" * 100)

print("\n[1] CLIENTE NOVO id=226:")
r = conn.run("SELECT id,name,partner_id,client_code,created_at FROM clients WHERE id=226")
h = ["id","name","partner_id","client_code","created_at"]
for k,v in zip(h, r[0]):
    print(f"   {k:>12s} = {v}")
novo_cliente_id = 226

print("\n[2] AGENTES PAREADOS COM client_id=226 (cliente ficticio novo):")
ags = conn.run(
    "SELECT id,client_id,hostname,name,last_heartbeat,remote_ip,created_at "
    "FROM agents WHERE client_id=%d ORDER BY created_at DESC" % novo_cliente_id
)
print(f"   >>> Quantidade agentes pareados: {len(ags)}")
if len(ags)==0:
    print("   ❌ NENHUM AGENTE PAREADO! (Wizard não terminou o passo 2/4 pareio, ou usou código errado?)")
    print("\n   [2b] Quais agentes foram atualizados nos últimos 15 min? (olhando o que o wizard tocou):")
    ags_recent = conn.run(
        "SELECT id,client_id,hostname,name,last_heartbeat,created_at FROM agents ORDER BY last_heartbeat DESC LIMIT 5"
    )
    for a in ags_recent:
        print("   - agente_id=%d client_id=%d hostname=%s name=%s last_hb=%s" % (a[0],a[1],a[2],a[3],a[4]))
else:
    ag_id = None
    for a in ags:
        print("   ✅ agente_id=%d client_id=%d hostname=%s name=%s last_hb=%s ip=%s criado=%s" % (a[0],a[1],a[2],a[3],a[4],a[5],a[6]))
        if ag_id is None:
            ag_id = a[0]

    print("\n[3] IMPRESSORAS client_id=226:")
    imp = conn.run(
        "SELECT id,client_id,ip_address,model,serial_number,created_at,last_seen "
        "FROM printers WHERE client_id=%d ORDER BY created_at DESC" % novo_cliente_id
    )
    print(f"   >>> Quantidade impressoras client_id=226: {len(imp)}")
    if len(imp)==0:
        print("   ❌ ZERO IMPRESSORAS! (Wizard não rodou scan/enviou readings passo 3/4?)")
    else:
        for i in imp:
            print("   ✅ printer_id=%d client_id=%d ip=%s model=%s serial=%s last_seen=%s" % (i[0],i[1],i[2],i[3],i[4],i[6]))

    print("\n[4] READINGS NOVAS (últimos 15 min) por qualquer agente ativo:")
    rds = conn.run(
        "SELECT r.id,r.printer_id,p.client_id,c.name as cliente_name,p.ip_address,p.model,r.collected_at "
        "FROM readings r LEFT JOIN printers p ON p.id=r.printer_id LEFT JOIN clients c ON c.id=p.client_id "
        "WHERE r.collected_at >= NOW() - INTERVAL '15 minutes' ORDER BY r.id DESC LIMIT 10"
    )
    if not rds:
        print("   Nenhuma reading nova.")
    for r in rds:
        print("   - reading_id=%d printer_id=%d cliente=%s(%d) ip=%s model=%s hora=%s" % (r[0],r[1],r[3],r[2],r[4],r[5],r[6]))

print("\n" + "=" * 100)
print("REGRA PROVA DO CÓDIGO routes.py L2408-L2425:")
print("=" * 100)
print("""
O UPSERT BUSCA SEMPRE:
   1) WHERE client_id == agent.client_id AND ip_address == r_ip
   2) SE NÃO ACHAR: WHERE client_id == agent.client_id AND serial_number == r_serial
   3) SE AINDA NÃO ACHAR ===> CRIA UMA NOVA impressora! (com o client_id DO AGENTE NOVO)

🎯 CONCLUSÃO: MESMA IMPRESSORA (mesmo IP/mesma RICOH 4510) PODE EXISTIR EM VÁRIOS CLIENTES DIFERENTES!
   NÃO HÁ NENHUM BLOQUEIO DE DUPLICIDADE GLOBAL! A duplicidade é SÓ POR (client_id + ip) ou (client_id + serial).
   Então a intuição de Julio sobre 'duplicada global bloqueou' NÃO É A CAUSA!
""")

conn.close()
