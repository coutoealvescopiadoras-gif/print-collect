"""
DEBUG MISTERIO: Por que parceiro cea copiadoras (financeiro@) logado nao ve
clientes/impressoras que ele mesmo criou (Posto Falcao id=225 partner_id=5)?

Checar a tabela partners (qual é a parceira cea copiadoras id=5?)
e tabela users (qual partner_id do user financeiro@ id=6?)
E o _required_partner_id como funciona?
"""
import ssl
import pg8000.native

PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"

ssl_ctx = ssl.create_default_context()
conn = pg8000.native.Connection(PG_USER, password=PG_PASS, host=PG_HOST, database=PG_DB, ssl_context=ssl_ctx)

def show(title, sql, params=None):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    try:
        rows = conn.run(sql, *params) if params else conn.run(sql)
        cols = []
        try:
            cols = [d[0] for d in (getattr(conn, 'description', None) or [])]
        except Exception:
            pass
        if not cols and rows:
            cols = [f"col{i}" for i in range(len(rows[0]))]
        print("COLUNAS:", cols or "desconhecidas")
        if not rows:
            print("   (0 linhas - VAZIO!)")
        for r in rows:
            print("  ", dict(zip(cols, r)) if cols else list(r))
    except Exception as e:
        print(f"   ❌ ERRO: {e}")

show(
    "[1] TABELA partners (parceiros cadastrados - onde esta CEA COPIADORAS parceira?)",
    "SELECT id, name, cnpj, email, active, created_at FROM partners ORDER BY id ASC"
)

show(
    "[2] TABELA users - TODOS os usuarios. VER partner_id NULL vs nao NULL:",
    "SELECT id, email, username, role, partner_id, client_id, active FROM users ORDER BY id ASC"
)

show(
    "[3] PERGUNTA DO DIA: Posto Falcao (id=225) tem partner_id=5. Quem tem partner_id=5 na tabela users?",
    "SELECT id, email, role, partner_id FROM users WHERE partner_id = 5 OR partner_id IS NULL ORDER BY id"
)

show(
    "[4] Clientes com partner_id=5 (todos clientes da parceira cea copiadoras id=5):",
    "SELECT id, name, partner_id, client_code FROM clients WHERE partner_id = 5 ORDER BY id DESC"
)

conn.close()
print("\n\nFIM DEBUG")
