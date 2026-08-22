import json
import urllib.request
import urllib.error
import ssl

URL = "https://www.printcollect.com.br/api/agent/report"
HEADERS = {
    "X-Agent-Token": "7sBdYelLa9V0PSFHQtRjXg5evKDWjL2Xwqi0flpcW24",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "PrintCollectAgent/0.3.0 ColetaManualCEA_Cliente/1.0",
}

PAYLOAD = {
    "hostname": "pc01",
    "version": "0.3.0",
    "readings": [
        {
            "ip_address": "192.168.15.220",
            "mac_address": "A4:3B:F5:2F:2E:53",
            "serial_number": "T597H301772",
            "model": "SP 4510SF",
            "manufacturer": "Ricoh",
            "status": "online",
            "pages_total": 79289,
            "pages_bw": 79289,
            "pages_color": 0,
            "toner_black": 42,
            "toner_cyan": None,
            "toner_magenta": None,
            "toner_yellow": None,
            "alerts": [],
        }
    ],
}

ctx = ssl.create_default_context()
data = json.dumps(PAYLOAD).encode("utf-8")

print("=" * 100)
print("⚡ COLETA FORÇADA CLIENTE CEA COPIADORAS (id=1) - TOKEN agente id=11")
print(f"Header X-Agent-Token = 7sBdYelLa9V0PSFHQtRjXg5evKDWjL2Xwqi0flpcW24")
print("=" * 100)

try:
    req = urllib.request.Request(URL, data=data, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        status_code = resp.status
        resp_body = resp.read().decode("utf-8", errors="replace")
        print(f"\n✅ HTTP STATUS CODE = {status_code}")
        print("\nRESPOSTA JSON:")
        print("-" * 100)
        print(resp_body)
except urllib.error.HTTPError as e:
    print(f"\n❌ HTTP ERROR CODE = {e.code}")
    print(e.read().decode("utf-8", errors="replace"))
except Exception as e:
    import traceback
    print(f"\n❌ ERRO PYTHON: {type(e).__name__}: {str(e)}")
    traceback.print_exc()
