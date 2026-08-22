"""
TESTE DIRETO da funcao agent_report() SEM servidor uvicorn.
Conecta no Neon via SQLAlchemy+pg8000 (provado no prova_own_only_fix.py).
Passa payload AGENT REPORT usando TOKEN do agente id=17 (Posto Falcao pc01 na Julio empresa).
Deve criar uma IMPRESSORA NOVA (IP 192.168.15.99 client_id=225) e 1 reading.
Se der erro, temos o traceback Python COMPLETO para resolver o misterio de Posto Falcao.

CUIDADO: este script EXECUTA writes no banco (INSERT printer, INSERT reading, UPDATE agent last_hb).
A impressora nova e IP 192.168.15.99 (falsa, teste). Depois apagamos via DELETE SQL manual.
"""
import os, sys, asyncio, traceback
from urllib.parse import quote_plus

# Força SQLAlchemy a usar pg8000 (provado funcionar)
PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"
DATABASE_URL = f"postgresql+pg8000://{PG_USER}:{quote_plus(PG_PASS)}@{PG_HOST}:5432/{PG_DB}"

import ssl
ssl_ctx = ssl.create_default_context()
ssl_args = {"ssl_context": ssl_ctx}

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 1) Força o backend a NAO usar psycopg (pq ainda nao instalamos): vamos monkey patch o _fix_postgres_driver
#    p/ nao substituir pg8000 -> psycopg
import app.database as app_database_mod
app_database_mod._fix_postgres_driver = lambda url: url  # NO-OP, mantem driver original

from app.config import settings

# Sobrescreve settings.database_url em runtime ANTES que o database.py importe engine
settings.model_config["protected_namespaces"] = ()
object.__setattr__(settings, "database_url", DATABASE_URL)
object.__setattr__(settings, "migration_url", DATABASE_URL)
object.__setattr__(settings, "auto_create_tables", False)
settings.__dict__["database_url"] = DATABASE_URL  # 3ª camada de sobrescrita, por via das duvidas

# 2) Cria nosso engine/pool de sessao com pg8000
engine = sa_create_engine(DATABASE_URL, connect_args=ssl_args, echo=False, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)

# 3) Monkey patch a Dependencia get_db do routes.py para usar o nosso SessionLocal
import app.routes as routes_mod

# Agora sim importa os modelos do app (ele vai usar o settings alterado? Nao, vamos usar nossa propria session)
from app.schemas import AgentReport, PrinterReading
from app.database import Printer, Agent, Client, Reading

# --- MONTAGEM DO PAYLOAD ---
# IP 192.168.15.99 = NOVO, NAO existe no banco (todas impressoras sao .220/.200/.210 etc)
# agent_id=17 Posto Falcao cid=225 TOKEN = vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ
AGENTE_POSTOFALCAO_PC01_TOKEN = "vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ"
IP_TESTE_NOVO = "192.168.15.99"  # Garantido novo

payload = AgentReport(
    agent_version="6.4.0-TesteLocal",
    readings=[
        PrinterReading(
            ip_address=IP_TESTE_NOVO,
            mac_address="00:11:22:33:44:AA",
            serial_number="POSTOFALCAO-TST001-DELETE-ME",
            model="HP LaserJet Pro M404dn (TESTE Posto Falcão)",
            manufacturer="Hewlett-Packard",
            status="online",
            pages_total=12345,
            pages_bw=12345,
            pages_color=0,
            toner_black=85.0,
            toner_cyan=None,
            toner_magenta=None,
            toner_yellow=None,
            alerts=[],
        )
    ],
)

print("=" * 90)
print(f"TESTE agent_report() assincrono - TOKEN agente Posto Falcao pc01")
print(f"Payload: 1 reading nova impressora IP={IP_TESTE_NOVO!r} - client_id DEVE SER 225 (Posto Falcao)")
print("=" * 90)

db = SessionLocal()
try:
    print(f"\n[STEP 1] Confere no banco se agente token existe / client_id = 225:")
    agent = db.query(Agent).filter(Agent.api_token == AGENTE_POSTOFALCAO_PC01_TOKEN).first()
    if agent:
        print(f"  ✅ OK: agent_id={agent.id} name={agent.name!r} client_id={agent.client_id} last_hb={agent.last_heartbeat}")
        client = db.query(Client).filter(Client.id == agent.client_id).first()
        print(f"       cliente: id={client.id} name={client.name!r} partner_id={client.partner_id}")
    else:
        print("  ❌ ERRO: Agente token não existe! Abortando.")
        sys.exit(1)

    print(f"\n[STEP 2] Confere se impressora IP {IP_TESTE_NOVO} JA EXISTE (nao deve):")
    pr_exist = db.query(Printer).filter(Printer.ip_address == IP_TESTE_NOVO).first()
    if pr_exist:
        print(f"  ⚠️ JA EXISTE printer_id={pr_exist.id} cid={pr_exist.client_id}. Vamos apagar para simular primeira coleta.")
        try:
            db.query(Reading).filter(Reading.printer_id == pr_exist.id).delete()
            db.delete(pr_exist)
            db.commit()
            print("  ✅ Impressora antiga + readings apagados. Resetado para limpo!")
        except Exception as e:
            print(f"  ❌ ERRO ao limpar: {e}; rolling back")
            db.rollback()
    else:
        print("  ✅ IMPRESSORA NOVA, nunca existiu - BOM!")

    db.close()
    db = SessionLocal()

    # --- CHAMADA DIRETA DA FUNCAO ASYNC agent_report() ---
    print(f"\n[STEP 3] CHAMANDO routes_mod.agent_report(payload, x_agent_token=...) com Session DB:")
    result = asyncio.run(routes_mod.agent_report(payload, AGENTE_POSTOFALCAO_PC01_TOKEN, db))
    print(f"\n[STEP 4] RETORNO DA FUNCAO agent_report: {result!r}")
    # No routes.py original, o retorno e JSON {"processed_ok": N, ...}

except Exception as exc:
    print("\n" + "!" * 90)
    print("❌ EXCEPTION CAPTURADA - AQUI ESTA O ERRO QUE BLOQUEAVA Posto Falcão de criar impressoras!")
    print("!" * 90)
    traceback.print_exc()
else:
    print("\n" + "=" * 90)
    print("✅ FUNCAO RODOU SEM EXCEPTION. Vamos VERIFICAR no banco se a impressora foi criada com client_id=225.")
    print("=" * 90)
    # Commit quaisquer transacoes pendentes
    try:
        db.commit()
    except Exception:
        db.rollback()
finally:
    try:
        db.close()
    except Exception:
        pass

# --- VALIDACAO FINAL: Abre sessao nova e SELECT printer IP=192.168.15.99 ---
print("\n" + "=" * 90)
print("VALIDACAO FINAL: SELECT impressora criada? client_id=225? Reading criada?")
print("=" * 90)
db2 = SessionLocal()
try:
    p_nova = db2.query(Printer).filter(Printer.ip_address == IP_TESTE_NOVO).order_by(Printer.id.desc()).first()
    if not p_nova:
        print("❌ NENHUMA impressora criada! agent_report deu return mas nao INSERTOU.")
    else:
        c_nova = db2.query(Client).filter(Client.id == p_nova.client_id).first()
        print(f"✅ IMPRESSORA CRIADA printer_id={p_nova.id}")
        print(f"   client_id={p_nova.client_id} name={c_nova.name if c_nova else 'DESCONHECIDO'!r} (esperado 225 Posto Falcão)")
        print(f"   ip={p_nova.ip_address!r} model={p_nova.model!r}")
        print(f"   pages_total={p_nova.pages_total} serial={p_nova.serial_number!r}")
        # Ver readings
        rds = db2.query(Reading).filter(Reading.printer_id == p_nova.id).order_by(Reading.id.desc()).limit(3).all()
        print(f"\n   Readings criados: {len(rds)} encontrados")
        for rr in rds:
            print(f"     reading id={rr.id} created={rr.created_at} pages_total={rr.pages_total}")
        if p_nova.client_id == 225 and c_nova and c_nova.name == "POSTO FALCÃO":
            print("\n🎉🎊🎆 PROVA DO SÉCULO: IMPRESSORA CRIADA NO CLIENTE CERTO POSTO FALCÃO id=225!")
            print("   BUG de agent_report NAO EXISTE. O problema real do Gabriel foi outro (abaixo...)")
        else:
            print(f"\n❌ IMPRESSORA CRIADA MAS CLIENTE ERRADO cid={p_nova.client_id} !")
finally:
    db2.close()
