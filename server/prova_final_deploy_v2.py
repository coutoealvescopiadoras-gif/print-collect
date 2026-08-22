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
        "pages_total": 167999,
        "pages_bw": 167999,
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
print("PROVA FINAL DO BUG DEPLOY - SEM EMOJI (encoding safe)")
print("   Agora:", now.strftime("%d/%m/%Y %H:%M:%S"))
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
        ps = conn.run(
            "SELECT id,client_id,ip_address,model,serial_number,last_seen,pages_total "
            "FROM printers WHERE client_id=:cid ORDER BY id DESC",
            cid=CLIENTE_ALVO,
        )
        rs = conn.run(
            "SELECT id,printer_id,collected_at,pages_total FROM readings "
            "WHERE printer_id IN (SELECT id FROM printers WHERE client_id=:cid) "
            "ORDER BY id DESC LIMIT 5",
            cid=CLIENTE_ALVO,
        )
    finally:
        conn.close()
    print()
    print("--- BANCO APOS " + label + " ---")
    print("  [Impressoras cliente_id=" + str(CLIENTE_ALVO) + "] " + str(len(ps)) + " encontradas:")
    for p in ps:
        pid, cid, ip, model, sn, ls_utc, pt = p
        ls_bsb = (ls_utc - timedelta(hours=3)).strftime("%H:%M:%S") if ls_utc else "nunca"
        sn_s = (sn or "")[:12]
        print("    printer_id=" + str(pid) + " ip=" + str(ip) + " " + str(model) +
              " SN=" + sn_s + " last_seen_BR=" + str(ls_bsb) + " pages=" + str(pt))
    print("  [Ultimas readings desse cliente] " + str(len(rs)) + ":")
    for r in rs:
        rid, pid, col_utc, pt = r
        col_bsb = (col_utc - timedelta(hours=3)).strftime("%H:%M:%S")
        print("    reading=" + str(rid) + " printer=" + str(pid) + " col_BR=" + str(col_bsb) +
              " pages=" + str(pt))
    return len(ps), len(rs)

q1_imp, q1_read = _consulta_banco("ANTES DO POST")

print()
print("--- ENVIANDO POST ---")
req = urllib.request.Request(
    f"{SERVER}/api/agent/report",
    data=json.dumps(PAYLOAD).encode("utf-8"),
    headers={"Content-Type": "application/json", "X-Agent-Token": TOKEN},
    method="POST",
)
status_http = 0
resposta = ""
parse_ok = False
status_json = "?"
processed_ok_json = -1
warns_json = []
try:
    with urllib.request.urlopen(req, timeout=90, context=ssl.create_default_context()) as resp:
        body_raw = resp.read().decode("utf-8", errors="replace")
        status_http = resp.status
        resposta = body_raw
        print("HTTP " + str(status_http))
        print("Resposta: " + body_raw[:800])
        try:
            rj = json.loads(body_raw)
            parse_ok = True
            status_json = rj.get("status", "?")
            processed_ok_json = rj.get("processed_ok", -1)
            warns_json = rj.get("warnings") or []
            print()
            print("[status=" + str(status_json) + "] processed_ok=" + str(processed_ok_json) +
                  " warnings_qty=" + str(len(warns_json)))
            for w in warns_json[:6]:
                print("  WAR: " + str(w)[:200])
        except Exception as parse_err:
            print("Nao parseou JSON? " + str(parse_err))
except urllib.error.HTTPError as he:
    status_http = he.code
    print("HTTPError code=" + str(he.code))
    try:
        print(he.read().decode("utf-8", errors="replace")[:800])
    except Exception:
        pass
except Exception as e:
    print("Exception POST: " + str(e))

time.sleep(4)
q2_imp, q2_read = _consulta_banco("POST + 4s")
time.sleep(8)
q3_imp, q3_read = _consulta_banco("POST + 12s TOTAL")

print()
print("=" * 100)
print("RESULTADO FINAL:")
print("   Antes do POST: impressoras=" + str(q1_imp) + " readings=" + str(q1_read))
print("   Depois 4s    : impressoras=" + str(q2_imp) + " readings=" + str(q2_read))
print("   Depois 12s   : impressoras=" + str(q3_imp) + " readings=" + str(q3_read))

criou_nova = (q3_imp > q1_imp or q3_read > q1_read)
print()
if criou_nova:
    print("SUCESSO! SUCESSO! SUCESSO! IMPRESSORA CRIADA NO BANCO! BUG MORTO!")
    print("Obrigado Julio! Obrigado Deus!")
    sys.exit(0)
else:
    print("AINDA NAO GRAVOU. Vamos verificar: ou deploy nao chegou ainda, ou precisa ajustar mais.")
    sys.exit(1)
