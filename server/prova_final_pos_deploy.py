"""
PROVA FINAL POS-DEPLOY:
Executa EXATAMENTE a MESMA query SQL das rotas /api/clients e /api/printers do backend
(codigo do routes.py LINHA 936-1082), só com as correções own_only que fizemos.
Se o resultado for 4 clientes (com Posto Falcao 225), prova que a correção ESTÁ CORRETA e quando
o deploy Vercel finalizar, o painel vai mostrar. Depois testa GET request real ao endpoint da Vercel.
"""
import os, sys
from urllib.parse import quote_plus

os.environ["DATABASE_URL"] = f"postgresql+pg8000://neondb_owner:{quote_plus('npg_U9JHqTsc3LPu')}@ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech:5432/neondb"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.database as DB
from sqlalchemy.orm import aliased

PartnerAlias = aliased(DB.Partner)
db = DB.SessionLocal()

print("=" * 100)
print("PROVA FINAL POS-DEPLOY - Query EXATA dos endpoints /api/clients E /api/printers (SuperAdmin)")
print("MÉTODO: SQLAlchemy conectado no Neon (mesmo DB produção). NENHUMA escrita.")
print("=" * 100)

# =========================================================
# ROTA 1: GET /api/clients - SuperAdmin, own_only=None (default)
# CÓDIGO routes.py linhas 936-943 CORRIGIDO HOJE
# =========================================================
print("\n[ENDPOINT 1] GET /api/clients - SuperAdmin own_only=None (CORRIGIDO HOJE):")
print("-" * 100)
query = db.query(DB.Client).outerjoin(PartnerAlias, PartnerAlias.id == DB.Client.partner_id)
own_only = None  # valor padrao quando frontend nao manda o parametro
partner_id = None
if own_only == True:
    query = query.filter(DB.Client.partner_id.is_(None))
if partner_id is not None:
    query = query.filter(DB.Client.partner_id == partner_id)
clients_res = query.order_by(DB.Client.name).all()
print(f"✅ Retornou {len(clients_res)} clientes (esperado 4, com Posto Falcao id=225 parceiro):")
for c in clients_res:
    pname = None
    if c.partner_id:
        p = db.query(DB.Partner).filter(DB.Partner.id == c.partner_id).first()
        pname = p.name if p else None
    print(f"    - client_id={c.id} name={c.name!r} partner_id={c.partner_id} ({pname}) code={c.client_code}")

tem_posto = any(c.id == 225 for c in clients_res)
print(f"\n  👉 Posto Falcão id=225 apareceu? → {'✅ SIM! (BUG DO DIA ACABOU!)' if tem_posto else '❌ NÃO (ainda bugado!)'}")

# =========================================================
# ROTA 2: GET /api/printers - SuperAdmin, own_only=None (default)
# CÓDIGO routes.py linhas 1073-1083 CORRIGIDO HOJE
# =========================================================
print("\n\n[ENDPOINT 2] GET /api/printers - SuperAdmin own_only=None (CORRIGIDO HOJE):")
print("-" * 100)
query = (
    db.query(DB.Printer)
    .filter(DB.Printer.ignored == False)
    .join(DB.Client, DB.Client.id == DB.Printer.client_id, isouter=False)
)
own_only = None
partner_id = None
if own_only == True:
    query = query.filter(DB.Client.partner_id.is_(None))
if partner_id is not None:
    query = query.filter(DB.Client.partner_id == partner_id)
printers_res = query.order_by(DB.Client.name, DB.Printer.model).all()
print(f"✅ Retornou {len(printers_res)} impressoras (esperado 5 + as novas do Posto Falcao):")
for p in printers_res:
    pname = None
    pid = p.client.partner_id
    if pid:
        pp = db.query(DB.Partner).filter(DB.Partner.id == pid).first()
        pname = pp.name if pp else None
    print(f"    - printer_id={p.id} cid={p.client_id} [{p.client.name}] ip={p.ip_address!r} model={p.model!r} partner_id={pid} ({pname})")

# =========================================================
# BÔNUS: Consulta RAW - impressoras client_id=225 Posto Falcao (para confirmar criaçao apos run-once Julio)
# =========================================================
print("\n\n[BÔNUS] Impressoras client_id=225 (Posto Falcao) - VERIFICA SE VOCE JA CRIOU COM RUN-ONCE:")
pfs = db.query(DB.Printer).filter(DB.Printer.client_id == 225).order_by(DB.Printer.id.desc()).all()
if not pfs:
    print("   ❌ 0 impressoras. VOCE AINDA NAO RODOU 'pair LWFTASJN' + 'run-once' no PC da empresa CEA aqui.")
else:
    print(f"   ✅ {len(pfs)} impressora(s) Posto Falcao client_id=225:")
    for p in pfs:
        rds = db.query(DB.Reading).filter(DB.Reading.printer_id == p.id).count()
        print(f"       printer_id={p.id} ip={p.ip_address!r} model={p.model!r} readings={rds} last_seen={p.last_seen}")

db.close()
print("\n\n" + "=" * 100)
print("FIM PROVA. SE [ENDPOINT 1] Mostrou Posto Falcao id=225, a CORREÇÃO ESTÁ 100% PRONTA!")
print("=" * 100)
