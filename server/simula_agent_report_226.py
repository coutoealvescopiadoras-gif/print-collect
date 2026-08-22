import urllib.request
import urllib.error
import json
import ssl

# ==============================
# SIMULANDO AGENTE id=18 (client_id=226 cleinte teste parceiro CEA)
# Token pego DIRETO do banco de dados agora:
TOKEN = "Bn0scR38P6qPwovEbM-P2_hV60fAINebWVVJpYLiuj8"
SERVER = "https://www.printcollect.com.br"
# MESMO PAYLOAD DA RICOH SP 4510SF 192.168.15.220 (loja CEA)
payload = {
    "agent_version": "6.4.0",
    "readings": [
        {
            "ip_address": "192.168.15.220",
            "mac_address": None,
            "serial_number": "T597H301772",
            "model": "RICOH SP 4510SF",
            "manufacturer": "Ricoh",
            "status": "online",
            "pages_total": 167654,
            "pages_bw": 167654,
            "pages_color": 0,
            "toner_black": 68.0,
            "toner_cyan": None,
            "toner_magenta": None,
            "toner_yellow": None,
            "alerts": [],
        }
    ],
}

print("=" * 95)
print("SIMULANDO POST /api/agent/report — AGENTE 18 (client_id=226 cleinte teste)")
print("=" * 95)
print(f"URL      : {SERVER}/api/agent/report")
print(f"Token    : {TOKEN[:15]}...")
print(f"Impressora: 192.168.15.220 RICOH SP 4510SF serial T597H301772 pages=167654")
print()

ctx_no_verify = ssl.create_default_context()
req = urllib.request.Request(
    f"{SERVER}/api/agent/report",
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "X-Agent-Token": TOKEN,
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=60, context=ctx_no_verify) as resp:
        body_raw = resp.read().decode("utf-8", errors="replace")
        print(f"HTTP STATUS CODE = {resp.status}")
        print(f"RAW RESPOSTA ({len(body_raw)} chars):")
        print(body_raw)
        try:
            resp_json = json.loads(body_raw)
            print("\nPARSED JSON:")
            print(json.dumps(resp_json, indent=2, ensure_ascii=False))
            print("\n" + "=" * 95)
            if resp_json.get("status") == "ok" and resp_json.get("processed_ok") == 1:
                print("✅ RESPOSTA DIZ QUE GRAVOU! processed_ok=1 status=ok")
                print("   AGORA VOU CONSULTAR O BANCO PARA VER SE IMPRESSORA EXISTE REALMENTE em client_id=226")
            else:
                print("❌ RESPOSTA MOSTRA ERRO DE COMMIT OU FATAL!")
        except Exception as parse_err:
            print(f"Nao parseou JSON? {parse_err}")
except urllib.error.HTTPError as he:
    print(f"❌ HTTP Error code: {he.code}")
    print("Body erro:", he.read().decode("utf-8", errors="replace")[:1500])
except Exception as e:
    print(f"❌ Exception: {e}")
