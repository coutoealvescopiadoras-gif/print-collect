import ssl
import pg8000.native
from datetime import datetime

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
print("🎊 PROVA NO BANCO DEPOIS DO WIZARD COMPLETO 14:30 (17:30 UTC)")
print("Horário Julio local:", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
print("=" * 100)

print("\n[1] IMPRESSORAS client_id=226 (cleinte teste parceiro CEA):")
p226 = conn.run(
    "SELECT id,client_id,ip_address,model,serial_number,created_at,last_seen,pages_total "
    "FROM printers WHERE client_id=226 ORDER BY id"
)
print(f"   Quantidade impressoras client 226: {len(p226)}")
if len(p226)==0:
    print("   ❌ NÃO TEM NADA AINDA (esperar mais 30s...)? Vamos tentar buscar 'criada hoje 17:30 UTC' em QUALQUER cliente:")
    todas_hoje = conn.run(
        "SELECT id,client_id,c.name,ip_address,model,created_at,last_seen "
        "FROM printers p LEFT JOIN clients c ON c.id=p.client_id WHERE p.created_at >= NOW() - INTERVAL '15 minutes' ORDER BY p.id"
    )
    for r in todas_hoje:
        print(f"   printer_id={r[0]} client_id={r[1]}({r[2]}) ip={r[3]} model={r[4]} criada={r[5]} visto={r[6]}")
else:
    for r in p226:
        print("-" * 95)
        print(f"   ✅ printer_id={r[0]} client_id={r[1]} ip={r[2]} model={r[3]} serial={r[4]}")
        print(f"      criada_em={r[5]}   last_seen={r[6]}   pages_total={r[7]}")

print("\n[2] READINGS NOVAS CRIADAS ÚLTIMAS 15 MINUTOS (todos os clientes):")
rds = conn.run(
    "SELECT r.id,r.printer_id,p.client_id,c.name as cliente,p.ip_address,p.model,r.collected_at,r.pages_total "
    "FROM readings r LEFT JOIN printers p ON p.id=r.printer_id LEFT JOIN clients c ON c.id=p.client_id "
    "WHERE r.collected_at >= NOW() - INTERVAL '15 minutes' ORDER BY r.id DESC"
)
if len(rds)==0:
    print("   Nenhuma? Espera +10s...")
for r in rds:
    print(f"   reading_id={r[0]} printer_id={r[1]} cliente=({r[2]}){r[3]} ip={r[4]} model={r[5]} hora={r[6]} pages={r[7]}")

conn.close()
print("\n" + "=" * 100)
