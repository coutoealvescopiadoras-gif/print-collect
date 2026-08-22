import ssl
import pg8000.native

PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"

ssl_context = ssl.create_default_context()
print("[1] Conectando ao Neon PostgreSQL (pg8000 pure-python)...")
conn = pg8000.native.Connection(PG_USER, password=PG_PASS, host=PG_HOST, database=PG_DB, ssl_context=ssl_context, port=5432)
print("[OK] conectado!\n")

def query(sql, params=None):
    try:
        if params:
            cur = conn.run(sql, *params)
        else:
            cur = conn.run(sql)
        cols = [c['name'] if isinstance(c, dict) else c for c in (conn.columns or [])]
        rows = []
        for r in cur:
            row = {}
            for i, val in enumerate(r):
                key = cols[i] if i < len(cols) else f"col{i}"
                row[key] = val
            rows.append(row)
        return rows
    except Exception as e:
        print(f"  ❌ Erro SQL: {e}")
        return []

print("=" * 80)
print("DEBUG DIRETO NO BANCO (SÓ SELECTS, NÃO ALTERA NADA)")
print("=" * 80)

# [1] Agente token local Julio
print("\n[1] Token do agente local configurado: 'vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ'")
rows = query("SELECT id, name, client_id, hostname, active, last_heartbeat, paired_at FROM agents WHERE api_token = %s LIMIT 1", (
    "vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ",
))
if rows:
    for r in rows:
        print(f"   [OK] Encontrado! id={r['id']} | name={r['name']} | client_id={r['client_id']} | hostname={r['hostname']} | last_hb={r['last_heartbeat']}")
else:
    print("   ❌ Token NÃO EXISTE no banco (errado ou expirado)")

# [2] Cliente Posto Falcão (id=225 ou nome)
print("\n[2] Cliente Posto Falcão (id=225 OU nome):")
rows = query("SELECT id, name, partner_id, client_code, active, created_at FROM clients WHERE id = %s OR name ILIKE %s ORDER BY id DESC LIMIT 5", (
    225, "%POSTO FALCAO%"
))
if rows:
    partners_cache = {}
    for r in rows:
        partner_name = None
        if r["partner_id"]:
            if r["partner_id"] not in partners_cache:
                pr = query("SELECT name FROM partners WHERE id = %s LIMIT 1", (r["partner_id"],))
                partners_cache[r["partner_id"]] = pr[0]["name"] if pr else None
            partner_name = partners_cache[r["partner_id"]]
        print(
            f"   id={r['id']} | name={r['name']} | partner_id={r['partner_id']} ({partner_name}) "
            f"| code={r['client_code']} | active={r['active']}"
        )
else:
    print("   ❌ Posto Falcão NÃO EXISTE no banco")

# [3] Impressoras RICOH SP 4510SF / IP 192.168.15.220
print("\n[3] Impressoras RICOH SP 4510SF / 192.168.15.220 (últimas 10):")
rows = query(
    "SELECT p.id, p.client_id, p.model, p.ip_address, p.mac_address, p.serial_number, p.last_seen "
    "FROM printers p "
    "WHERE p.ip_address ILIKE %s OR p.model ILIKE %s "
    "ORDER BY p.id DESC LIMIT 10",
    ("%192.168.15.220%", "%RICOH SP 4510SF%"),
)
if rows:
    clients_cache = {}
    partners_cache = {}
    for r in rows:
        cname = None
        pname = None
        if r["client_id"]:
            if r["client_id"] not in clients_cache:
                c = query("SELECT id, name, partner_id FROM clients WHERE id=%s LIMIT 1", (r["client_id"],))
                if c:
                    clients_cache[r["client_id"]] = (c[0]["name"], c[0]["partner_id"])
                else:
                    clients_cache[r["client_id"]] = (f"DESCONHECIDO {r['client_id']}", None)
            cname, pid = clients_cache[r["client_id"]]
            if pid and pid not in partners_cache:
                pr = query("SELECT name FROM partners WHERE id=%s LIMIT 1", (pid,))
                partners_cache[pid] = pr[0]["name"] if pr else None
            pname = partners_cache[pid] if pid else None
        print(
            f"   Printer id={r['id']} | client_id={r['client_id']} (cliente={cname!r}, parceiro={pname!r})"
            f"\n       model={r['model']} | ip={r['ip_address']} | serial={r['serial_number']}"
            f"\n       last_seen={r['last_seen']}\n"
        )
else:
    print("   ❌ Nenhuma impressora RICOH / 192.168.15.220 encontrada!")

# [4] Cea Copiadoras (codigo FJ37S3W6) - ultimos agentes e readings
print("\n[4] Cea Copiadoras / codigo FJ37S3W6 - ultimos heartbeats + readings:")
cea = query("SELECT id, name, partner_id, client_code FROM clients WHERE client_code = %s LIMIT 1", ("FJ37S3W6",))
if cea:
    c = cea[0]
    print(f"   Cliente id={c['id']} | name={c['name']} | partner_id={c['partner_id']}")
    agents_cea = query(
        "SELECT id, name, hostname, last_heartbeat, paired_at FROM agents WHERE client_id = %s ORDER BY id DESC LIMIT 5",
        (c["id"],)
    )
    print("   Últimos agentes deste cliente:")
    for a in agents_cea:
        print(f"     - id={a['id']} {a['name']} (host={a['hostname']}) last_hb={a['last_heartbeat']} paired_at={a['paired_at']}")
    reads = query(
        "SELECT rd.id, rd.printer_id, rd.created_at, rd.pages_total, rd.pages_bw, rd.pages_color, p.ip_address "
        "FROM readings rd JOIN printers p ON p.id = rd.printer_id "
        "WHERE p.client_id = %s ORDER BY rd.created_at DESC LIMIT 5",
        (c["id"],)
    )
    print("   Últimas 5 leituras (Readings) deste cliente:")
    for r in reads:
        print(f"     - reading id={r['id']} printer_ip={r['ip_address']} created_at={r['created_at']} pages={r['pages_total']} bw={r['pages_bw']} color={r['pages_color']}")
else:
    print("   ❌ Cea FJ37S3W6 não encontrado!")

print("\n" + "=" * 80)
print("FIM DEBUG")
print("=" * 80)

conn.close()
