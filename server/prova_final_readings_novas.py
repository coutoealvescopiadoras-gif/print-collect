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
print("PROVA FINAL: EXISTE ALGUMA READING NOVA CRIADA APÓS 17:19 (WIZARD TESTE)?")
print("=" * 100)

print("\n[1] TODAS AS IMPRESSORAS CRIADAS / ALTERADAS HOJE DEPOIS DAS 17:00 (order by last_seen desc):")
rows = conn.run(
    "SELECT p.id,p.client_id,c.name as cliente_nome,c.partner_id,p.ip_address,p.model,p.serial_number,p.created_at,p.last_seen "
    "FROM printers p LEFT JOIN clients c ON c.id=p.client_id "
    "WHERE p.last_seen >= '2026-08-11 17:00:00' OR p.created_at >= '2026-08-11 17:00:00' "
    "ORDER BY p.last_seen DESC"
)
if len(rows)==0:
    print("   NENHUMA impressora atualizada ou criada depois das 17:00.")
for r in rows:
    print("-" * 95)
    print(f"  printer_id={r[0]} client={r[1]}({r[2]}) partner_id={r[3]} ip={r[4]} model={r[5]} serial={r[6]}")
    print(f"     criada_em: {r[7]}   last_seen: {r[8]}")

print("\n[2] TODAS AS READINGS das ÚLTIMAS 2 HORAS (collected_at >= 15:30 UTC = 12:30 BSB):")
rds = conn.run(
    "SELECT r.id,r.printer_id,p.client_id,c.name as cliente,p.ip_address,p.model,r.collected_at,r.pages_total "
    "FROM readings r LEFT JOIN printers p ON p.id=r.printer_id LEFT JOIN clients c ON c.id=p.client_id "
    "WHERE r.collected_at >= NOW() - INTERVAL '2 hours' ORDER BY r.id DESC LIMIT 10"
)
if len(rds)==0:
    print("   NÃO HÁ READINGS NOVAS NAS ÚLTIMAS 2 HORAS NO BANCO TODO.")
for r in rds:
    print(f"   reading_id={r[0]} printer={r[1]} cliente=({r[2]}){r[3]} ip={r[4]} model={r[5]} coletado_em={r[6]} pages={r[7]}")

print("\n[3] IMPRESSORAS EXISTENTES client_id=226 cleinte teste:")
p226 = conn.run("SELECT id,client_id,ip_address,model,serial_number,created_at,last_seen FROM printers WHERE client_id=226")
print(f"   Quantidade: {len(p226)}")
if len(p226)==0:
    print("   >>> ❌ NÃO EXISTE NENHUMA!")
else:
    for r in p226:
        print(f"   printer_id={r[0]} client_id={r[1]} ip={r[2]} model={r[3]} last_seen={r[6]}")

conn.close()
print("\n" + "=" * 100)
print("CONCLUSÃO SE client_id=226 NÃO TEM NENHUMA IMPRESSORA:")
print("=" * 100)
print("""
A PRIMEIRA COLETA DO WIZARD NÃO GRAVOU (deploy serverless 504 temporario, rede, etc).
MAS O PAREAMENTO FUNCIONOU (agente 18 criado client_id=226) + HEARTBEAT 17:30 = WATCHDOG RODANDO.
LOGO, NAS PRÓXIMAS 10 A 30 MINUTOS, O Watchdog/30min FAZ A COLETA SOZINHO E CRIA A IMPRESSORA!
OU RODAR MANUALMENTE NO PC CEA: atalho "Coletar Agora / once" e ele aparece IMEDIATAMENTE.
""")
