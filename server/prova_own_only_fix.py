"""
SCRIPT DE PROVA: COMPARA filtro SuperAdmin own_only ANTES (bug) vs DEPOIS (correto)
Lado a lado, sem tocar no servidor, direto no banco Neon producao via SQLAlchemy + pg8000.
SOMENTE SELECTS (READ-ONLY!) NUNCA ALTERA NADA.
"""
import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine, orm, func
from sqlalchemy.orm import Session, joinedload

# 1) URL do Neon PostgreSQL (pg8000 driver pure-python, SSL obrigatorio)
PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"

DATABASE_URL = (
    f"postgresql+pg8000://{PG_USER}:{quote_plus(PG_PASS)}@{PG_HOST}:5432/{PG_DB}"
)

# Conecta com SSL obrigatorio Neon
import ssl
ssl_context = ssl.create_default_context()
ssl_args = {"ssl_context": ssl_context}

print("[1] Conectando SQLAlchemy + pg8000 no Neon...")
engine = create_engine(
    DATABASE_URL,
    connect_args=ssl_args,
    echo=False,
    pool_pre_ping=True,
)
SessionLocal = orm.sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()
print("[OK] conectado!\n")

# 2) Importa models DO NOSSO APP (nao recria!)
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.database import Base, Client, Printer, Partner

print("=" * 90)
print("PROVA DO BUG vs CORREÇÃO: Rota GET /clients SuperAdmin")
print("=" * 90)
from sqlalchemy.orm import aliased

PartnerAlias = aliased(Partner)

def query_clients_ANTIGA_BUG(db: Session, own_only=None, partner_id=None):
    """CÓDIGO EXATO do backend PRODUÇÃO ANTES DA CORREÇÃO (o bug de hoje!)"""
    query = db.query(Client).outerjoin(PartnerAlias, PartnerAlias.id == Client.partner_id)
    # SUPERADMIN:
    #   BUG LINHA 940: if own_only is None or own_only == True: filtra partner_id IS NULL!
    if own_only is None or own_only == True:
        query = query.filter(Client.partner_id.is_(None))
    if partner_id is not None:
        query = query.filter(Client.partner_id == partner_id)
    return query.order_by(Client.name).all()

def query_clients_NOVA_CORRETA(db: Session, own_only=None, partner_id=None):
    """CÓDIGO EXATO do backend DEPOIS da correção de hoje (routes.py linha 938-942)"""
    query = db.query(Client).outerjoin(PartnerAlias, PartnerAlias.id == Client.partner_id)
    # SUPERADMIN:
    #   own_only=None (default) → NÃO FAZ NENHUM FILTRO, retorna TODOS clientes (diretos + parceiros)
    #   own_only=True → retorna só diretos (partner_id IS NULL)
    if own_only == True:
        query = query.filter(Client.partner_id.is_(None))
    if partner_id is not None:
        query = query.filter(Client.partner_id == partner_id)
    return query.order_by(Client.name).all()

print(
    "\nCENÁRIO 1: SuperAdmin acessa GET /api/clients?own_only=0 (ou só /clients, sem own_only na URL)\n"
    "   o que DEVE ACONTECER: MOSTRAR Posto Falcão (id=225, parceiro id=5)\n"
    "   o que ACONTECIA (BUG): REMOVER Posto Falcão, só mostrar diretos (id 1,3,4)\n"
)
print("-" * 90)
print(f"   [BUG ANTES DA CORREÇÃO]   own_only=None → {len(query_clients_ANTIGA_BUG(db))} clientes:")
for c in query_clients_ANTIGA_BUG(db):
    pname = None
    if c.partner_id:
        p = db.query(Partner).filter(Partner.id == c.partner_id).first()
        pname = p.name if p else None
    print(f"      - id={c.id} name={c.name!r} partner_id={c.partner_id} ({pname}) code={c.client_code}")

print(f"\n   [CORREÇÃO HOJE (routes.py)] own_only=None → {len(query_clients_NOVA_CORRETA(db))} clientes:")
for c in query_clients_NOVA_CORRETA(db):
    pname = None
    if c.partner_id:
        p = db.query(Partner).filter(Partner.id == c.partner_id).first()
        pname = p.name if p else None
    print(f"      - id={c.id} name={c.name!r} partner_id={c.partner_id} ({pname}) code={c.client_code}")

print("\n✅ POSTO FALCÃO (id=225) aparece agora na NOVA consulta? →",
      any(c.id == 225 for c in query_clients_NOVA_CORRETA(db)))

print("\n" + "=" * 90)
print("PROVA DO BUG vs CORREÇÃO: Rota GET /printers SuperAdmin (join com Client para filtro partner_id)")
print("=" * 90)

def query_printers_ANTIGA_BUG(db: Session, own_only=None, partner_id=None):
    """BUG PRODUÇÃO (antes de hoje) linhas 1078-1084"""
    query = (
        db.query(Printer)
        .filter(Printer.ignored == False)
        .join(Client, Client.id == Printer.client_id, isouter=False)
    )
    # SUPERADMIN BUG: own_only=None or True → filtra clientes DIRETOS (partner_id NULL)
    if own_only is None or own_only == True:
        query = query.filter(Client.partner_id.is_(None))
    if partner_id is not None:
        query = query.filter(Client.partner_id == partner_id)
    return query.order_by(Client.name, Printer.model).all()

def query_printers_NOVA_CORRETA(db: Session, own_only=None, partner_id=None):
    """CORREÇÃO routes.py linhas 1078-1082 (feita hoje)"""
    query = (
        db.query(Printer)
        .filter(Printer.ignored == False)
        .join(Client, Client.id == Printer.client_id, isouter=False)
    )
    if own_only == True:
        query = query.filter(Client.partner_id.is_(None))
    if partner_id is not None:
        query = query.filter(Client.partner_id == partner_id)
    return query.order_by(Client.name, Printer.model).all()

# Primeiro imprimimos as impresoras do banco com seus clientes/parceiros para contexto:
print("\n📋 DADOS REAIS BANCO NEON - impressoras CADASTRADAS hoje (5 total):")
all_printers = (
    db.query(Printer)
    .filter(Printer.ignored == False)
    .join(Client, Client.id == Printer.client_id)
    .all()
)
for p in all_printers:
    pname = None
    pid = p.client.partner_id
    if pid:
        pp = db.query(Partner).filter(Partner.id == pid).first()
        pname = pp.name if pp else None
    print(f"   printer_id={p.id} ip={p.ip_address!r} model={p.model!r} → cliente.name={p.client.name!r} (id={p.client.id}) partner_id={pid} ({pname})")

print("\n\nCENÁRIO 2: SuperAdmin acessa GET /api/printers (sem own_only) → tem que listar TODAS impressoras:")
print("-" * 90)
print(f"   [BUG ANTES DA CORREÇÃO]    own_only=None → {len(query_printers_ANTIGA_BUG(db))} impressoras (só clientes diretos)")
for p in query_printers_ANTIGA_BUG(db):
    pname = None
    pid = p.client.partner_id
    if pid:
        pp = db.query(Partner).filter(Partner.id == pid).first()
        pname = pp.name if pp else None
    print(f"      - printer id={p.id} ip={p.ip_address!r} model={p.model!r} client={p.client.name!r} partner={pname}")

print(f"\n   [CORREÇÃO routes.py HOJE] own_only=None → {len(query_printers_NOVA_CORRETA(db))} impressoras (todos! diretos + parceiros quando tem)")
for p in query_printers_NOVA_CORRETA(db):
    pname = None
    pid = p.client.partner_id
    if pid:
        pp = db.query(Partner).filter(Partner.id == pid).first()
        pname = pp.name if pp else None
    print(f"      - printer id={p.id} ip={p.ip_address!r} model={p.model!r} client={p.client.name!r} partner={pname}")

# 🔑 A PROVA FINAL DO FIM DO BUG DO DIA:
# Quando o Posto Falcão tiver impressoras cadastradas (client_id=225), elas teriam
# Client.partner_id=5. O bug filtrava `Client.partner_id IS NULL` por padrão, removendo.
# Vamos criar UM PRINT FAKE IN-MEMORY temporário? Não, melhor fazer uma query bruta:
print("\n\n🔑 PROVA DEFINITIVA do BUG QUE VOCE RECLAMOU HOJE (Posto Falcão não tinha impressoras hoje):")
print("   Se a impressora do Posto Falcão existisse client_id=225 partner_id=5:")
print("   - QUERY ANTIGA (bug): where Client.partner_id IS NULL → REMOVERIA da listagem ❌")
print("   - QUERY NOVA (correta): SEM filtro nenhum → APARECERIA normalmente ✅")

# Para provar, forçamos uma busca raw:
print("\n📊 Query raw BUG (where partner_id IS NULL):")
r_bug = db.query(Printer).join(Client, Client.id == Printer.client_id).filter(Client.partner_id.is_(None)).count()
print(f"      Nº de impressoras retornadas = {r_bug}")

print("📊 Query raw CORRETA (nenhum filtro partner_id = todos clientes):")
r_ok = db.query(Printer).join(Client, Client.id == Printer.client_id).count()
print(f"      Nº de impressoras retornadas = {r_ok}")

db.close()
print("\n" + "=" * 90)
print("FIM DA PROVA. NENHUM DADO FOI ALTERADO.")
print("=" * 90)
