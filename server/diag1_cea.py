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

now = datetime.now()
print("=" * 100)
print("DIAGNÓSTICO RÁPIDO 1 - SITUAÇÃO CEA COPIADORAS (agora:", now.strftime("%d/%m/%Y %H:%M:%S"), ")")
print("=" * 100)

print("\n[1] Impressora id=1 (RICOH SP 4510 192.168.15.220 - CEA cliente id=1):")
p1 = conn.run(
    "SELECT id,client_id,ip_address,model,created_at,last_seen,pages_total FROM printers WHERE id=1"
)
for r in p1:
    printer_id, client_id, ip, model, criada, last_seen_utc, pages = r
    last_seen_bsb = last_seen_utc - timedelta(hours=3)
    mins_ago = int((datetime.utcnow() - last_seen_utc).total_seconds() / 60)
    print(f"   id={printer_id} | cliente={client_id} | ip={ip} | model={model}")
    print(f"   ultima_coleta_BRASILIA = {last_seen_bsb.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"   >>> Há quantos minutos? {mins_ago} min atrás")
    print(f"   pages_total atual = {pages}")
    print(f"   criada em = {criada}")

print("\n[2] ÚLTIMAS 6 READINGS da impressora id=1 (por horário coleta desc):")
r6 = conn.run(
    "SELECT id,collected_at,pages_total,pages_bw,pages_color FROM readings WHERE printer_id=1 ORDER BY id DESC LIMIT 6"
)
for r in r6:
    r_id, col_utc, pt, pb, pc = r
    col_bsb = col_utc - timedelta(hours=3)
    print(f"   reading_id={r_id} coletado_BRASILIA={col_bsb.strftime('%d/%m %H:%M:%S')} pages_total={pt} pb={pb} pc={pc}")

print("\n[3] TAREFAS QUE DEVEM DISPARAR (instaladas hoje 12:19 CMD + Wizard 14:30):")
print("   👉 HOURLY manual: 12:19, 13:19, 14:19, 15:19, 16:19, 17:19, ...")
print("   👉 Watchdog 10: a cada 10 min (se wizard criou tarefa)")
print("   👉 30 minutos: (se wizard criou tarefa)")

prox_horario = None
for h in range(now.hour, now.hour+3):
    for m in [19, 29, 30, 34, 39, 44, 49]:
        test = datetime(now.year, now.month, now.day, h, m)
        if test > now:
            prox_horario = test.strftime("%H:%M")
            break
    if prox_horario:
        break

if prox_horario:
    print(f"\n🎯 PREVISÃO PRÓXIMA COLETA (de qualquer tarefa): {prox_horario} (faltam ~{int((datetime(now.year,now.month,now.day,int(prox_horario.split(':')[0]),int(prox_horario.split(':')[1])) - now).total_seconds()/60)} min)")

print("\n[4] Agente que cuida da CEA cliente id=1 (agente id=11?):")
ag11 = conn.run(
    "SELECT id,client_id,hostname,name,last_heartbeat FROM agents WHERE client_id=1 OR id=11 ORDER BY last_heartbeat DESC LIMIT 3"
)
for a in ag11:
    a_id, c_id, host, name, hb_utc = a
    if hb_utc:
        hb_bsb = hb_utc - timedelta(hours=3)
        mins = int((datetime.utcnow() - hb_utc).total_seconds() / 60)
        print(f"   ag_id={a_id} cliente={c_id} ({host}) hb_bsb={hb_bsb.strftime('%H:%M')} há {mins} min")

conn.close()
print("\n" + "=" * 100)
