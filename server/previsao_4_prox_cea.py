from datetime import datetime, timedelta
import ssl
import pg8000.native

now = datetime.now()

ctx = ssl.create_default_context()
conn = pg8000.native.Connection(
    "neondb_owner",
    password="npg_U9JHqTsc3LPu",
    host="ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech",
    database="neondb",
    ssl_context=ctx,
    port=5432,
)

print("=" * 95)
print("4 PRÓXIMAS ATUALIZAÇÕES ESPERADAS DA CEA COPIADORAS LOJA FÍSICA")
print("Agora no seu relógio Julio (Brasília):", now.strftime("%d/%m/%Y %H:%M:%S"))
print("=" * 95)

r = conn.run(
    "SELECT last_seen FROM printers WHERE id=1"
)
last_seen_utc = r[0][0]
conn.close()

last_bsb = last_seen_utc - timedelta(hours=3)

print(f"\n✅ Última coleta REALIZADA (RICOH id=1): {last_bsb.strftime('%d/%m/%Y %H:%M')}")
print()
print("=" * 95)
print("TAREFA 1: A CADA 1 HORA (/SC HOURLY criada por você hoje às 12:19)")
print("=" * 95)
t1 = []
base_horario_fixo = datetime(last_bsb.year, last_bsb.month, last_bsb.day, 12, 19)
for i in range(1, 20):
    prox = base_horario_fixo + timedelta(hours=i)
    if prox > last_bsb:
        t1.append(prox)
print(f"   Próximas 4 (fuso BSB):")
for k, h in enumerate(t1[:4]):
    print(f"   [{k+1}] {h.strftime('%H:%M')} (faltam ~{int((h - now).total_seconds()/60)} min)")

print()
print("=" * 95)
print("TAREFA 2: A CADA 30 MINUTOS (criada pelo Wizard 14:30 hoje)")
print("=" * 95)
base_t2 = datetime(last_bsb.year, last_bsb.month, last_bsb.day, 14, 30)
t2 = []
for i in range(1, 40):
    prox = base_t2 + timedelta(minutes=30 * i)
    if prox > last_bsb:
        t2.append(prox)
print(f"   Próximas 4 (se tarefa 30min foi criada corretamente no schtasks):")
for k, h in enumerate(t2[:4]):
    print(f"   [{k+1}] {h.strftime('%H:%M')} (faltam ~{max(0,int((h - now).total_seconds()/60))} min)")

print()
print("=" * 95)
print("TAREFA 3: WATCHDOG A CADA 10 MINUTOS (criada pelo Wizard 14:30 hoje)")
print("=" * 95)
base_t3 = datetime(last_bsb.year, last_bsb.month, last_bsb.day, 14, 30)
t3 = []
for i in range(1, 120):
    prox = base_t3 + timedelta(minutes=10 * i)
    if prox > last_bsb:
        t3.append(prox)
print(f"   Próximas 4 (se Watchdog 10min OK):")
for k, h in enumerate(t3[:4]):
    print(f"   [{k+1}] {h.strftime('%H:%M')} (faltam ~{max(0,int((h - now).total_seconds()/60))} min)")

print()
print("=" * 95)
print("🎯 TABELA FINAL DOS 4 PRÓXIMOS HORÁRIOS MAIS PROVÁVEIS (CONSIDERANDO TUDO):")
print("=" * 95)

todos = t1 + t2 + t3
todos_unicos = []
vistos = set()
for x in sorted(todos):
    chave = x.strftime("%H:%M")
    if chave not in vistos and x > now:
        vistos.add(chave)
        todos_unicos.append(x)

for k, h in enumerate(todos_unicos[:4]):
    print(f"   🎯 Próxima #{k+1}: {h.strftime('%H:%M')} BSB (faltam ~{max(0,int((h - now).total_seconds()/60))} minutos)")

print()
print("💡 DICA: Se as tarefas 30min/Watchdog 10min existirem, a próxima atualização")
print("   vai ser ANTES de 15:19! Se só existir a HOURLY manual, vai ser 15:19 mesmo.")
print("   Abra o painel às 15:00 e atualize F5 a cada 2 minutos, você vai ver! 🟢")
print()
print("   Se quiser conferir as tarefas instaladas hoje na loja CEA:")
print("     CMD Admin: schtasks /Query /FO LIST | findstr /i 'Print Collect'")
