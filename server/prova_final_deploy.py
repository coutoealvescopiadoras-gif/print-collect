import urllib.request, urllib.error, json, ssl, time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pg8000.native
from datetime import datetime, timedelta

TOKEN = "Bn0scR38P6qPwovEbM-P2_hV60fAINebWVVJpYLiuj8"
SERVER = "https://www.printcollect.com.br"
PAYLOAD = {
    "agent_version": "6.4.0",
    "readings": [{
        "ip_address": "192.168.15.220",
        "mac_address": None,
        "serial_number": "T597H301772",
        "model": "RICOH SP 4510SF",
        "manufacturer": "Ricoh",
        "status": "online",
        "pages_total": 167654 + 99,
        "pages_bw": 167654 + 99,
        "pages_color": 0,
        "toner_black": 68.0,
        "toner_cyan": None,
        "toner_magenta": None,
        "toner_yellow": None,
        "alerts": [],
    }],
}
CLIENTE_ALVO = 226

now = datetime.now()
print("=" * 100)
print("PROVA FINAL DO BUG DEPLOY (agora:", now.strftime("%d/%m/%Y %H:%M:%S"), ")")
print("   PASSO 1: POST /api/agent/report para", SERVER)
print("   PASSO 2: CONSULTA BANCO NEON IMEDIATAMENTE DEPOIS")
print("   PASSO 3: VERIFICA SE IMPRESSORA client_id=226 FOI CRIADA")
print("=" * 100)

def _consulta_banco(label):
    ctx = ssl.create_default_context()
    conn = pg8000.native.Connection(
        "neondb_owner", password="npg_U9JHqTsc3LPu",
        host="ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech",
        database="neondb", ssl_context=ctx, port=5432,
    )
    try:
        ps = conn.run("SELECT id,client_id,ip_address,model,serial_number,last_seen,pages_total FROM printers WHERE client_id=:cid ORDER BY id DESC", cid=CLIENTE_ALVO)
        rs = conn.run("SELECT id,printer_id,collected_at,pages_total FROM readings WHERE printer_id IN (SELECT id FROM printers WHERE client_id=:cid) ORDER BY id DESC LIMIT 3", cid=CLIENTE_ALVO)
    finally:
        conn.close()
    print(f"\n--- BANCO APÓS {label} ---")
    print(f"[Impressoras cliente_id={CLIENTE_ALVO}] {len(ps)} encontradas:")
    for p in ps:
        pid, cid, ip, model, sn, ls_utc, pt = p
        ls_bsb = (ls_utc - timedelta(hours=3)).strftime("%H:%M:%S") if ls_utc else "nunca"
        print(f"   printer_id={pid} ip={ip} {model} SN={sn} last_seen_BR={ls_bsb} pages={pt}")
    print(f"[Últimas readings desse cliente] {len(rs)}:")
    for r in rs:
        rid, pid, col_utc, pt = r
        col_bsb = (col_utc - timedelta(hours=3)).strftime("%H:%M:%S")
        print(f"   reading={rid} printer={pid} col_BR={col_bsb} pages={pt}")
    return len(ps), len(rs)

q1_imp, q1_read = _consulta_banco("ANTES DO POST")

print(f"\n--- ENVIANDO POST ---")
req = urllib.request.Request(
    f"{SERVER}/api/agent/report",
    data=json.dumps(PAYLOAD).encode("utf-8"),
    headers={"Content-Type": "application/json", "X-Agent-Token": TOKEN},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=90, context=ssl.create_default_context()) as resp:
        body_raw = resp.read().decode("utf-8", errors="replace")
        print(f"HTTP {resp.status}")
        print("Resposta:", body_raw[:800])
        try:
            rj = json.loads(body_raw)
            status = rj.get("status")
            pok = rj.get("processed_ok")
            warnings = rj.get("warnings") or []
            print(f"\n✅ status={status} processed_ok={pok} warnings_qty={len(warnings)}")
            if warnings:
                for w in warnings[:5]:
                    print(f"   WAR: {w[:200]}")
        except Exception as parse_err:
            print(f"Nao parseou JSON? {parse_err}")
except urllib.error.HTTPError as he:
    print(f"❌ HTTPError code={he.code}")
    print(he.read().decode("utf-8", errors="replace")[:800])
except Exception as e:
    print(f"❌ Exception POST: {e}")

time.sleep(3)
q2_imp, q2_read = _consulta_banco("POST (3s de espera)")
time.sleep(6)
q3_imp, q3_read = _consulta_banco("POST + 9s TOTAL")

print("\n" + "=" * 100)
print("RESULTADO FINAL:")
print(f"   Antes do POST: impressoras={q1_imp} readings={q1_read}")
print(f"   Depois 3s    : impressoras={q2_imp} readings={q2_read}")
print(f"   Depois 9s    : impressoras={q3_imp} readings={q3_read}")

if q3_imp > q1_imp or q3_read > q1_read:
    print("\n🎉🎉🎉 SUCESSO! IMPRESSORA FOI CRIADA NO BANCO! BUG MORTO! 🎉🎉🎉")
else:
    print("\n❌ AINDA NAO GRAVOU. Vamos aguardar deploy ou precisa de mais ajuste.")
print("=" * 100)
