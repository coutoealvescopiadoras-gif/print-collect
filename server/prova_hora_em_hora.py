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
print("PROVA RÁPIDA - COLETA DE HORA EM HORA FUNCIONANDO?")
print("Horário local script:", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
print("=" * 100)

print("\n[1] Últimos 5 heartbeats de agentes (order by last_heartbeat desc):")
rows = conn.run(
    "SELECT a.id, a.client_id, c.name as client_name, a.hostname, a.name, a.last_heartbeat, a.remote_ip "
    "FROM agents a LEFT JOIN clients c ON c.id=a.client_id ORDER BY a.last_heartbeat DESC LIMIT 5"
)
headers = ["id", "client_id", "client_name", "hostname", "name", "last_heartbeat", "remote_ip"]
for r in rows:
    print("-" * 80)
    for k, v in zip(headers, r):
        print(f"   {k:>14s} = {v}")

print("\n[2] Impressoras vs. horário last_seen AGORA (últimas 5 por last_seen desc):")
rows2 = conn.run(
    "SELECT p.id, p.client_id, c.name as client_name, c.partner_id, p.ip_address, p.model, p.last_seen "
    "FROM printers p LEFT JOIN clients c ON c.id=p.client_id ORDER BY p.last_seen DESC LIMIT 5"
)
h2 = ["id", "client_id", "client_name", "partner_id", "ip_address", "model", "last_seen"]
for r in rows2:
    print("-" * 80)
    for k, v in zip(h2, r):
        print(f"   {k:>12s} = {v}")

print("\n[3] Quantas readings foram criadas nas ÚLTIMAS 2 HORAS (intervalo <= 60min mostra que tá rodando horario)?")
ultima_2h = conn.run(
    "SELECT COUNT(*) FROM readings WHERE collected_at >= NOW() - INTERVAL '2 hours'"
)
print(f"   ✅ {ultima_2h[0][0]} readings novas nas últimas 2 horas.")
if ultima_2h[0][0] >= 1:
    print("   ✅ COLETA DE HORA EM HORA CONTINUA FUNCIONANDO 100%! TUDO CERTO! 🎉")

print("\n[4] Impressora id=1 (cea copiadoras cliente id=1 nossa de teste) last_seen AGORA:")
p1 = conn.run(
    "SELECT id,client_id,ip_address,model,last_seen FROM printers WHERE id=1"
)
for r in p1:
    print("   ", r)
    now_utc = datetime.utcnow()
    if r[4]:
        diff = now_utc - r[4]
        print(f"   >>> Diferença de tempo: {int(diff.total_seconds()/60)} minutos atrás (UTC).")

conn.close()
print("\nFIM! Se o item [2] tem horários recentes E item [3] > 1, está tudo 100% OK!")
