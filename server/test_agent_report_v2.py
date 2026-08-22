"""
TESTE DIRETO da funcao agent_report() SEM servidor uvicorn.
MELHORADO: seta variaveis de AMBIENTE ANTES de importar app.config
(assim _detect_database_url() carrega nossa URL Neon pg8000 certinha).
"""
import os, sys, asyncio, traceback
from urllib.parse import quote_plus

# ========== SET ENV VARS ANTES DE IMPORTAR NOSSO APP (config.py) ==========
PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"
DATABASE_URL = f"postgresql+pg8000://{PG_USER}:{quote_plus(PG_PASS)}@{PG_HOST}:5432/{PG_DB}"
os.environ["DATABASE_URL"] = DATABASE_URL
os.environ["DIRECT_URL"]  = DATABASE_URL
os.environ["AUTO_CREATE_TABLES"] = "false"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Agora sim pode importar:
from app.schemas import AgentReport, PrinterReading
import app.database as DB
import app.routes   as routes_mod

# ----- MONTAGEM PAYLOAD: impressora IP 192.168.15.99 NOVA (client_id=225) -----
AGENTE_POSTOFALCAO_PC01_TOKEN = "vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ"
IP_TESTE_NOVO = "192.168.15.99"

payload = AgentReport(
    agent_version="6.4.0-TesteLocal",
    readings=[
        PrinterReading(
            ip_address=IP_TESTE_NOVO,
            mac_address="00:11:22:33:44:AA",
            serial_number="POSTOFALCAO-TST001-DELETAR",
            model="HP LaserJet Pro M404dn TESTE Posto Falcao",
            manufacturer="Hewlett-Packard",
            status="online",
            pages_total=12345,
            pages_bw=12345,
            pages_color=0,
            toner_black=85.0,
            toner_cyan=None, toner_magenta=None, toner_yellow=None,
            alerts=[],
        )
    ],
)

print("=" * 90)
print(f"TESTE agent_report() assincrono - TOKEN Posto Falcao pc01")
print(f"Engine SQLAlchemy URL driver: {DATABASE_URL[:DATABASE_URL.find('@')].split('//')[0]}//****")
print("=" * 90)

# ---- Limpeza previa: apaga impressora 192.168.15.99 se existir (de rodada anterior) ----
db = DB.SessionLocal()
try:
    exist = db.query(DB.Printer).filter(DB.Printer.ip_address == IP_TESTE_NOVO).all()
    if exist:
        for p in exist:
            db.query(DB.Reading).filter(DB.Reading.printer_id == p.id).delete()
            db.delete(p)
        db.commit()
        print(f"[PREP] Limpei {len(exist)} impressora(s) antigas de teste no IP {IP_TESTE_NOVO}.")
    else:
        print(f"[PREP] IP {IP_TESTE_NOVO} limpo (nunca existiu).")
finally:
    db.close()

# ---- Agente valido? ----
db = DB.SessionLocal()
try:
    agent = db.query(DB.Agent).filter(DB.Agent.api_token == AGENTE_POSTOFALCAO_PC01_TOKEN).first()
    if not agent:
        print("❌ TOKEN agente INVALIDO! Abortando.")
        sys.exit(1)
    c = db.query(DB.Client).filter(DB.Client.id == agent.client_id).first()
    print(f"[PREP] ✅ Agente VALIDO id={agent.id} name={agent.name!r} cliente id={c.id} name={c.name!r} (parceiro={c.partner_id}) last_hb={agent.last_heartbeat}")
finally:
    db.close()

# ========================================================================
# EXECUCAO PRINCIPAL: chamar a função AGENT REPORT (igual POST /api/agent/report)
# ========================================================================
db = DB.SessionLocal()
resultado = None
try:
    print("\n[EXEC] Chamando routes_mod.agent_report(payload, token, db)...")
    resultado = asyncio.run(routes_mod.agent_report(payload, AGENTE_POSTOFALCAO_PC01_TOKEN, db))
    print(f"\n✅ EXECUCAO CONCLUIDA (sem exception). Retorno JSON: {resultado!r}")
    try:
        db.commit()
    except Exception as cm_e:
        print(f"   [WARN] db.commit falhou (esperado se a funcao ja deu commit internamente): {str(cm_e)[:120]}")
        db.rollback()
except Exception as exc:
    print("\n" + "!" * 90)
    print("❌ EXCEPTION CAPTURADA NO agent_report! AQUI ESTA O MOTIVO:")
    print("!" * 90)
    traceback.print_exc()
finally:
    try: db.close()
    except Exception: pass

# ========================================================================
# VALIDACAO FINAL: a impressora foi gravada com client_id=225 (Posto Falcao)?
# ========================================================================
print("\n" + "=" * 90)
print("VALIDACAO FINAL - consulta SELECT")
print("=" * 90)

db2 = DB.SessionLocal()
try:
    p = db2.query(DB.Printer).filter(DB.Printer.ip_address == IP_TESTE_NOVO).order_by(DB.Printer.id.desc()).first()
    if not p:
        print(f"❌ NENHUMA impressora criada com IP {IP_TESTE_NOVO}.")
    else:
        cli = db2.query(DB.Client).filter(DB.Client.id == p.client_id).first()
        partner_nome = None
        if cli and cli.partner_id:
            part = db2.query(DB.Partner).filter(DB.Partner.id == cli.partner_id).first()
            partner_nome = part.name if part else None
        rds = db2.query(DB.Reading).filter(DB.Reading.printer_id == p.id).count()
        print(f"✅ IMPRESSORA ENCONTRADA printer_id={p.id}")
        print(f"   client_id  = {p.client_id} (esperado 225)")
        print(f"   cliente    = {cli.name if cli else '?'} (esperado POSTO FALCAO)")
        print(f"   parceiro   = {partner_nome if partner_nome else '(sem parceiro - cliente direto)'} (esperado C&A COPIADORAS id=5)")
        print(f"   model      = {p.model!r}")
        print(f"   pages_total= {p.pages_total} (esperado 12345)")
        print(f"   readings qt= {rds} (esperado >= 1)")
        print(f"   last_seen  = {p.last_seen}")

        OK_ID = p.client_id == 225
        OK_NAME = cli and cli.name.upper() == "POSTO FALCÃO"
        if OK_ID and OK_NAME:
            print("\n" + "🎊" * 25)
            print("🎉🎉🎉 PROVA DEFINITIVA: impressora foi criada NO CLIENTE CERTO (Posto Falcao id=225) 🎉🎉🎉")
            print("🎊" * 25)
        else:
            print(f"\n❌ PROBLEMA: client_id={p.client_id} nao e 225 OU nome nao e Posto Falcao.")
finally:
    db2.close()
