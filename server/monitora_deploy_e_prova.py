import urllib.request, json, ssl, time, sys, subprocess, os, datetime

SERVER = "https://www.printcollect.com.br"
SCRIPT_PROVA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prova_final_deploy_v2.py")
OUT_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_monitor_deploy.log")

ctx = ssl.create_default_context()

def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    linha = f"[{ts}] {msg}"
    print(linha, flush=True)
    try:
        with open(OUT_LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass

def health_check():
    try:
        req = urllib.request.Request(f"{SERVER}/health")
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status == 200:
                try:
                    rj = json.loads(body)
                    db = rj.get("database", "?")
                    st = rj.get("status", "?")
                    return True, f"HTTP200 status={st} db={db}"
                except Exception:
                    return True, f"HTTP200 (sem JSON)"
            return False, f"HTTP{resp.status}"
    except Exception as e:
        return False, f"ERRO: {str(e)[:80]}"

log("=" * 80)
log(f"MONITOR DEPLOY INICIADO. Aguardando deploy commit 56bc815")
log(f"  Health: {SERVER}/health")
log(f"  Prova final automatica: {SCRIPT_PROVA}")
log("=" * 80)

max_polls = 22  # ~ 11 minutos
ok_count = 0
last_msg = ""

for i in range(1, max_polls + 1):
    ok, msg = health_check()
    mudou = (msg != last_msg)
    last_msg = msg
    prefix = f"[{i:>2}/{max_polls}] "
    if ok:
        ok_count += 1
        log(prefix + f"OK  health -> {msg}" + ("  (acumula OK={ok_count})" if mudou else ""))
    else:
        ok_count = 0
        log(prefix + f"FALHA health -> {msg}")
        time.sleep(30)
        continue
    if ok_count >= 2:
        log("")
        log(f"HEALTH ESTAVEL ({ok_count} vezes OK). INICIANDO PROVA FINAL V2...")
        log("=" * 80)
        time.sleep(2)
        try:
            rc = subprocess.call(
                [sys.executable, SCRIPT_PROVA],
                cwd=os.path.dirname(SCRIPT_PROVA),
                stdout=None,
                stderr=None,
            )
            log("=" * 80)
            log(f"PROVA FINAL TERMINOU com exit_code={rc}")
            if rc == 0:
                log("SUCESSO GERAL! BUG MORTO!")
            else:
                log("Ainda falhou. Vamos ver log da prova.")
            sys.exit(rc)
        except Exception as sub_err:
            log(f"ERRO ao rodar prova final: {sub_err}")
            sys.exit(3)
    time.sleep(30)

log("")
log("TIMEOUT DEPOIS DE 11 MINUTOS. Deploy nao chegou ou Vercel travou.")
log("Manual: rodar python prova_final_deploy_v2.py")
sys.exit(4)
