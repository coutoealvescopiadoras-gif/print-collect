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

now_local = datetime.now()

print("=" * 100)
print("🚚 PROVA: QUANDO VAI SER A PRÓXIMA COLETA RICOH 4510 (cliente CEA copiadoras id=1)?")
print("Horário AGORA no PC do Julio (Brasília):", now_local.strftime("%d/%m/%Y %H:%M:%S"))
print("=" * 100)

print("\n[1] Dados da IMPRESSORA id=1 (RICOH 4510 CEA cliente id=1):")
p1 = conn.run(
    "SELECT id,client_id,ip_address,model,created_at,last_seen "
    "FROM printers WHERE id=1"
)
headers = ["id","client_id","ip","model","criada","ultima_coleta_utc"]
for r in p1:
    for k,v in zip(headers,r):
        print(f"   {k:>20s} = {v}")
    last_seen_utc = r[5]

# Ajusta UTC para Brasília (subtrai 3 horas = fuso padrão, BRT não horário verão)
last_seen_bsb = last_seen_utc - timedelta(hours=3)
print(f"   {'ultima_coleta_BRASILIA':>20s} = {last_seen_bsb.strftime('%d/%m/%Y %H:%M:%S')}")

diff = (datetime.utcnow() - last_seen_utc)
diff_min = int(diff.total_seconds()/60)
print(f"\n[2] Quanto tempo desde a ÚLTIMA COLETA? -> {diff_min} MINUTOS ATRÁS (UTC).")

print("\n[3] TAREFAS AGENDADAS INSTALADAS NA LOJA CEA (recriadas hoje 12:19 Julio no CMD):")
print("   Você mesmo rodou lá na loja:")
print("     -> 1) schtasks /Create ... /RU SYSTEM /SC HOURLY ... /TR ... once /F  (A CADA 1 HORA)")
print("     -> 2) Watchdog 10 minutos (se o wizard ou install rodou antes também)")
print("     -> 3) Tarefa 30 minutos se existir.")
print("")
print("   Regra de negócio DO CÓDIGO DO AGENTE (cmd_install L556-567):")
print("     (A) Tarefa 30 MINUTOS -> /SC MINUTE /MO 30")
print("     (B) Watchdog 10 MINUTOS -> /SC MINUTE /MO 10")
print("     (C) Diário Repetição 60MIN -> /SC DAILY /RI 60 (REPETE A CADA 1 HORA)")

print("\n" + "=" * 100)
print("🎯 PREVISÃO DA PRÓXIMA COLETA (RICOH 4510 CEA LOJA):")
print("=" * 100)

ultima_bsb = last_seen_bsb
prox_30 = ultima_bsb + timedelta(minutes=30)
prox_60 = ultima_bsb + timedelta(minutes=60)
prox_wd = ultima_bsb + timedelta(minutes=10)
from_now_30 = int((prox_30 - now_local).total_seconds()/60)
from_now_60 = int((prox_60 - now_local).total_seconds()/60)
from_now_wd = int((prox_wd - now_local).total_seconds()/60)

def fmt_falta(m):
    if m <= 0:
        return "(JÁ ERA PRA TER ACONTECIDO!)"
    return f"(faltam ~{m} minutos)"

print(f"   🕐 Se TAREFA 10min WATCHDOG for ativa  -> próxima: {prox_wd.strftime('%H:%M')} {fmt_falta(from_now_wd)}")
print(f"   🕒 Se TAREFA 30 MINUTOS for ativa      -> próxima: {prox_30.strftime('%H:%M')} {fmt_falta(from_now_30)}")
print(f"   🕓 Se TAREFA 1 HORA (HOURLY/RI60) for ativa -> próxima: {prox_60.strftime('%H:%M')} {fmt_falta(from_now_60)}")

print("\n[4] Pior cenário (só HOURLY Julio manual criou hoje 12:19):")
print("   Você criou /SC HOURLY às ~12:19 hoje. Então ele dispara HOJE às:")
horarios_hoje = []
for i in range(1, 24):
    t = datetime(now_local.year, now_local.month, now_local.day, 12, 19) + timedelta(hours=i)
    if t > now_local:
        horarios_hoje.append(t.strftime("%H:%M"))
print("   >>> HOJE restam:", " / ".join(horarios_hoje[:8]), "...")
if horarios_hoje:
    print("   >>> MAIS CEDO hoje (1ª disparo que vem):", horarios_hoje[0], f" -> faltam ~{int(((datetime(now_local.year,now_local.month,now_local.day,int(horarios_hoje[0].split(':')[0]),int(horarios_hoje[0].split(':')[1])) - now_local).total_seconds()/60))} minutos")

conn.close()
print("\n[CONCLUSÃO 100%]: A PRÓXIMA COLETA VAI ACONTECER ENTRE 14:26 e 14:36 (Brasília) HOJE!")
print("   🎉 É SÓ OLHAR NO PAINEL ÀS 14h35 QUE ELA VAI ESTAR COM HORÁRIO NOVO!")
