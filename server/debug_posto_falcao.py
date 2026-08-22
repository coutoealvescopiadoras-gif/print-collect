import os
import ssl
from pathlib import Path
import sys

server_dir = Path(__file__).parent
sys.path.insert(0, str(server_dir))

os.environ["DATABASE_URL"] = "sqlite:///./dummy_temp_ignore.db"

from app.database import (
    Base,
    Client,
    Printer,
    Agent,
    User,
    Partner,
    Reading,
)  # noqa: E402

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"
URL_NO_PARAMS = (
    f"postgresql+pg8000://{PG_USER}:{PG_PASS}@{PG_HOST}:5432/{PG_DB}"
)

ssl_ctx = ssl.create_default_context()
engine = create_engine(
    URL_NO_PARAMS,
    connect_args={"ssl_context": ssl_ctx},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

print("=" * 80)
print("DEBUG DIRETO NO BANCO NEON PRODUÇÃO (SÓ SELECTS, NÃO MODIFICA NADA!)")
print("=" * 80)

print("\n[1] Achar token do agente LOCAL (config.yaml Julio): api_token='vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ'")
agent_local = (
    db.query(Agent)
    .filter(Agent.api_token == "vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ")
    .first()
)
if agent_local:
    print(
        f"   [OK] ENCONTRADO! Agent ID={agent_local.id} | name={agent_name:200 if (agent_name:=agent_local.name) else ''}"
        f"\n       client_id = {agent_local.client_id}"
        f"\n       hostname  = {agent_local.hostname}"
        f"\n       last_heartbeat = {agent_local.last_heartbeat}"
    )
else:
    print("   ❌ NÃO ENCONTRADO! (token não existe ou errado)")

print("\n[2] Achar Cliente Posto Falcão (id=225 OU nome):")
pf = (
    db.query(Client)
    .filter((Client.id == 225) | (Client.name.ilike("%POSTO FALCAO%")))
    .all()
)
if pf:
    for c in pf:
        partner = db.query(Partner).filter(Partner.id == c.partner_id).first() if c.partner_id else None
        print(
            f"   [OK] Client ID={c.id} | name={c.name}"
            f"\n       partner_id = {c.partner_id} | partner_name = {partner.name if partner else 'NULL'}"
            f"\n       client_code = {c.client_code}"
            f"\n       active = {c.active}"
        )
else:
    print("   ❌ Posto Falcão não existe no banco!")

print("\n[3] Achar Impressora RICOH SP 4510SF instalada hoje (IP 192.168.15.220):")
ricohs = (
    db.query(Printer)
    .filter(
        (Printer.ip_address.ilike("192.168.15.220"))
        | (Printer.model.ilike("%RICOH SP 4510SF%"))
    )
    .order_by(Printer.id.desc())
    .limit(10)
    .all()
)
if ricohs:
    for p in ricohs:
        client_of_printer = db.query(Client).filter(Client.id == p.client_id).first()
        partner_of_client = (
            db.query(Partner).filter(Partner.id == client_of_printer.partner_id).first()
            if client_of_printer and client_of_printer.partner_id
            else None
        )
        print(
            f"   [OK] Printer ID={p.id} | model={p.model} | ip={p.ip_address}"
            f"\n       client_id = {p.client_id} | client_name = {client_of_printer.name if client_of_printer else '?'}"
            f"\n       partner = {partner_of_client.name if partner_of_client else 'NULL / direto'}"
            f"\n       last_seen = {p.last_seen}"
        )
else:
    print("   ❌ Nenhuma RICOH 192.168.15.220 / SP 4510SF encontrada!")

print("\n[4] Últimos 10 heartbeats da Cea Cliente (para confirmar que realmente parou em 11:04):")
cea_client = db.query(Client).filter(Client.client_code == "FJ37S3W6").first()
if cea_client:
    print(f"   Cea Cliente (client_code FJ37S3W6) ID={cea_client.id} name={cea_client.name}")
    agents_cea = (
        db.query(Agent)
        .filter(Agent.client_id == cea_client.id)
        .order_by(Agent.id.desc())
        .limit(10)
        .all()
    )
    for a in agents_cea:
        print(
            f"   Agent ID={a.id} | name={a.name} | hostname={a.hostname}"
            f"\n       last_heartbeat = {a.last_heartbeat}"
            f"\n       paired_at      = {a.paired_at}"
        )
else:
    print("   ❌ Cea Cliente (FJ37S3W6) não encontrada!")

print("\n[5] Últimas 5 leituras (Readings) enviadas pela RICOH cea copiadoras de ontem:")
if cea_client:
    readings_cea = (
        db.query(Reading)
        .join(Printer, Printer.id == Reading.printer_id)
        .filter(Printer.client_id == cea_client.id)
        .order_by(Reading.created_at.desc())
        .limit(5)
        .all()
    )
    for r in readings_cea:
        print(
            f"   Reading ID={r.id} | printer {r.printer_id} (ip {r.printer.ip_address if r.printer else '?'})"
            f"\n       created_at = {r.created_at}"
            f"\n       pages_total = {r.pages_total} pages_bw={r.pages_bw} color={r.pages_color}"
        )
else:
    print("   ⚠️ Cea cliente não encontrado")

print("\n" + "=" * 80)
print("FIM DEBUG")
print("=" * 80)
db.close()
