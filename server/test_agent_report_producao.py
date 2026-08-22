import json
import urllib.request
import urllib.error
import ssl

URL = "https://www.printcollect.com.br/api/agent/report"
HEADERS = {
    "X-Agent-Token": "vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "PrintCollectAgent/0.3.0 TesteManualProducao/1.0",
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
            "location": "Sala Financeiro",
            "status": "online",
            "pages_total": 79288,
            "pages_bw": 79288,
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
print("TESTE FINAL - Payload EXATO do agente Windows -> https://www.printcollect.com.br/api/agent/report")
print("Header X-Agent-Token = vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ (agente id=17 Posto Falcão id=225)")
print("=" * 100)
print("\nPAYLOAD ENVIADO (1 impressora RICOH 220):")
print(json.dumps(PAYLOAD, indent=3, ensure_ascii=False))

try:
    req = urllib.request.Request(URL, data=data, headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=40, context=ctx) as resp:
        status_code = resp.status
        resp_body = resp.read().decode("utf-8", errors="replace")
        print("\n" + "=" * 100)
        print(f"✅ HTTP STATUS CODE = {status_code}")
        print("=" * 100)
        print("\nRESPOSTA JSON DO SERVIDOR PRODUCAO:")
        print("-" * 100)
        print(resp_body)
        try:
            obj = json.loads(resp_body)
            print("\n" + "=" * 100)
            print("📋 ANALISE DA RESPOSTA:")
            print("-" * 100)
            print(f"   status          = {obj.get('status')}")
            print(f"   readings_received = {obj.get('readings_received')}")
            print(f"   processed_ok    = {obj.get('processed_ok')}")
            print(f"   processed_errors = {obj.get('processed_errors')}")
            warns = obj.get("warnings") or []
            print(f"   warnings        = {len(warns)}")
            for i, w in enumerate(warns, 1):
                print(f"      WARN #{i}: {w}")
        except Exception as e_json:
            print("\n   (nao consegui parsear JSON resposta):", str(e_json))
except urllib.error.HTTPError as e:
    print("\n" + "=" * 100)
    print(f"❌ HTTP ERROR CODE = {e.code}")
    print("=" * 100)
    body = e.read().decode("utf-8", errors="replace")
    print(f"\nCORPO DO ERRO (detalhe do bug!):\n{body}")
except Exception as e:
    print("\n" + "=" * 100)
    print(f"❌ ERRO PYTHON (fora HTTP): {type(e).__name__}: {str(e)}")
    print("=" * 100)
    import traceback
    traceback.print_exc()
