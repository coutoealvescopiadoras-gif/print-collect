import urllib.request, urllib.error, json, ssl, time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pg8000.native
from datetime import datetime, timedelta

TOKEN = "Bn0scR38P6qPwovEbM-P2_hV60fAINebWVVJpYLiuj8"
SERVER = "https://www.printcollect.com.br"
now = datetime.now()
NOVAS_PAGINAS = 168000 + (now.minute % 60) + now.second
PAYLOAD = {
    "agent_version": "6.4.0",
    "readings": [{
        "ip_address": "192.168.15.220",
        "mac_address": None,
        "serial_number": "T597H301772",
        "model": "RICOH SP 4510SF",
        "manufacturer": "Ricoh",
        "status": "online",
        "pages_total": NOVAS_PAGINAS,
        "pages_bw": NOVAS_PAGINAS,
        "pages_color": 0,
        "toner_black": 67.0,
        "toner_cyan": None,
        "toner_magenta": None,
        "toner_yellow": None,
        "alerts": [],
    }],
}
CLIENTE_ALVO = 226

print("=" * 90)
print("TESTE RAPIDO JULIO (agora:", now.strftime("%d/%m/%Y %H:%M:%S"), ")")
print("  Alvo: agente 18 -> cliente_id=226 cleinte teste")
print("  Vou enviar pages_total =", NOVAS_PAGINAS)
print("=" * 90)

print("\n--- POST /api/agent/report ---")
req = urllib.request.Request(
    f"{SERVER}/api/agent/report",
    data=json.dumps(PAYLOAD).encode("utf-8"),
    headers={"Content-Type": "application/json", "X-Agent-Token": TOKEN},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=90, context=ssl.create_default_context()) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        print("HTTP " + str(resp.status))
        print("Resposta: " + body)
except Exception as e:
    print("ERRO: " + str(e))
    sys.exit(1)

time.sleep(6)

ctx = ssl.create_default_context()
conn = pg8000.native.Connection(
    "neondb_owner", password="npg_U9JHqTsc3LPu",
    host="ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech",
    database="neondb", ssl_context=ctx, port=5432,
)
try:
    ps = conn.run("SELECT id,ip_address,model,serial_number,last_seen,pages_total FROM printers WHERE client_id=:cid ORDER BY id DESC", cid=CLIENTE_ALVO)
    rs = conn.run("SELECT id,printer_id,collected_at,pages_total FROM readings WHERE printer_id IN (SELECT id FROM printers WHERE client_id=:cid) ORDER BY id DESC LIMIT 4", cid=CLIENTE_ALVO)
finally:
    conn.close()

print("\n--- BANCO NEON DEPOIS DO TESTE ---")
print("Impressoras cliente 226: " + str(len(ps)))
for p in ps:
    pid, ip, m, sn, ls_utc, pt = p
    ls_bsb = (ls_utc - timedelta(hours=3)).strftime("%d/%m %H:%M:%S") if ls_utc else "-"
    sn_s = (sn or "")[:14]
    print("  -> PRINTER id=" + str(pid) + " ip=" + str(ip) + " " + str(m) + " SN=" + sn_s +
          " last_seen_BR=" + str(ls_bsb) + " PAGES=" + str(pt))
print("\nÚltimas readings cliente 226: " + str(len(rs)))
for r in rs:
    rid, pid, col_utc, pt = r
    col_bsb = (col_utc - timedelta(hours=3)).strftime("%d/%m %H:%M:%S")
    print("  -> READING id=" + str(rid) + " printer=" + str(pid) + " coleta_BR=" + str(col_bsb) +
          " pages=" + str(pt))

print("\n🎉 Julio, atualiza F5 no painel cliente 'cleinte teste' agora! Você vai ver o horário NOVO!")
print("🎉 As páginas mudaram de 167999 para " + str(NOVAS_PAGINAS) + " para você ter certeza que não é cache!")
