import ssl
import pg8000.native

PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"

ssl_context = ssl.create_default_context()
print("[1] Conectando ao Neon PostgreSQL (pg8000 native)...")
conn = pg8000.native.Connection(
    user=PG_USER, password=PG_PASS, host=PG_HOST,
    database=PG_DB, ssl_context=ssl_context, port=5432
)
print("[OK] conectado!\n")

cols_cache = {}

def query(sql, params=None):
    try:
        cur = conn.run(sql, *params) if params else conn.run(sql)
        col_names = []
        try:
            for desc in getattr(conn, 'description', None) or []:
                col_names.append(desc[0] if isinstance(desc, (list, tuple)) else str(desc))
        except Exception:
            pass
        if not col_names:
            try:
                col_names = [str(getattr(c, 'name', c)) for c in (conn.columns or [])]
            except Exception:
                col_names = [f"col{i}" for i in range(len(cur[0]) if cur else 0)]
        rows = []
        for r in cur:
            row = {}
            for i, val in enumerate(r):
                key = col_names[i] if i < len(col_names) else f"col{i}"
                row[key] = val
            rows.append(row)
        return rows
    except Exception as e:
        print(f"  ❌ SQL Error: {e}")
        return []

def query_raw(sql, params=None):
    try:
        return conn.run(sql, *params) if params else conn.run(sql)
    except Exception as e:
        print(f"  ❌ SQL Error RAW: {e}")
        return []

print("=" * 80)
print("DEBUG BANCO NEON PRODUCAO (SOMENTE SELECTS - NUNCA ALTERA DADOS)")
print("=" * 80)

# [1] Token agente local Julio
print("\n[1] Agente com api_token = 'vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ'")
rows = query_raw("SELECT id, name, client_id, hostname, active, last_heartbeat, paired_at FROM agents WHERE api_token = $1 LIMIT 1",
                 ["vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ"])
if rows:
    for r in rows:
        print(f"   [OK] Encontrado! id={r[0]} | name={r[1]} | client_id={r[2]} | hostname={r[3]} | last_hb={r[5]}")
else:
    print("   ❌ NÃO EXISTE (token inválido ou não gravado)")

# [2] Cliente Posto Falcão
print("\n[2] Clientes Posto Falcão / id=225:")
rows = query_raw("SELECT id, name, partner_id, client_code, active FROM clients WHERE id = $1 OR name ILIKE $2 ORDER BY id DESC LIMIT 5",
                 [225, "%POSTO FALCAO%"])
if rows:
    for r in rows:
        pid = r[2]
        partner_name = ""
        if pid:
            p = query_raw("SELECT name FROM partners WHERE id = $1 LIMIT 1", [pid])
            partner_name = f"parceiro={p[0][0] if p else '?'}"
        print(f"   client_id={r[0]} | name={r[1]!r} | partner_id={pid} ({partner_name}) | code={r[3]} | active={r[4]}")
else:
    print("   ❌ Cliente não encontrado (id=225 / nome Posto Falcão)")

# [3] Impressoras RICOH / 192.168.15.220
print("\n[3] Impressoras (RICOH SP 4510SF / IP 192.168.15.220) ultimas 10:")
rows = query_raw("SELECT id, client_id, model, ip_address, serial_number, last_seen FROM printers "
                 "WHERE ip_address ILIKE $1 OR model ILIKE $2 ORDER BY id DESC LIMIT 10",
                 ["%192.168.15.220%", "%RICOH SP 4510SF%"])
client_cache = {}
partner_cache = {}
if rows:
    for r in rows:
        cid = r[1]
        cname = ""
        pname = ""
        if cid:
            if cid not in client_cache:
                c = query_raw("SELECT name, partner_id FROM clients WHERE id=$1 LIMIT 1", [cid])
                if c:
                    client_cache[cid] = (c[0][0], c[0][1])
                else:
                    client_cache[cid] = (f"DESCONHECIDO {cid}", None)
            cname, pid = client_cache[cid]
            if pid and pid not in partner_cache:
                p = query_raw("SELECT name FROM partners WHERE id=$1 LIMIT 1", [pid])
                partner_cache[pid] = p[0][0] if p else None
            pname = partner_cache[pid] if pid else "direto (NULL)"
        print(
            f"   printer_id={r[0]} | client_id={cid} [{cname!r} / {pname}]"
            f"\n       model={r[2]!r} | ip={r[3]!r} | serial={r[4]!r}"
            f"\n       last_seen={r[5]}\n"
        )
else:
    print("   ❌ Nenhuma impressora RICOH / 192.168.15.220 encontrada")

# [4] Cea Copiadoras (FJ37S3W6) - ultimos heartbeats / readings
print("\n[4] Cliente 'cea copiadoras' (client_code FJ37S3W6):")
cea = query_raw("SELECT id, name, partner_id FROM clients WHERE client_code = $1 LIMIT 1", ["FJ37S3W6"])
if cea:
    cid = cea[0][0]
    cname = cea[0][1]
    pid = cea[0][2]
    pname = query_raw("SELECT name FROM partners WHERE id=$1", [pid]) if pid else None
    print(f"   [OK] id={cid} name={cname!r} partner_id={pid} nome_parceiro={pname[0][0] if pname else 'direto'}")
    agents = query_raw("SELECT id, name, hostname, last_heartbeat, paired_at FROM agents WHERE client_id=$1 ORDER BY id DESC LIMIT 5", [cid])
    print("   Agentes deste cliente:")
    for a in agents:
        print(f"     - id={a[0]} | name={a[1]!r} host={a[2]!r} last_hb={a[3]} paired={a[4]}")
    reads = query_raw(
        "SELECT rd.id, rd.created_at, rd.pages_total, rd.pages_bw, rd.pages_color, p.ip_address "
        "FROM readings rd JOIN printers p ON p.id = rd.printer_id "
        "WHERE p.client_id = $1 ORDER BY rd.created_at DESC LIMIT 5", [cid]
    )
    print("   Últimas 5 leituras (Readings):")
    if reads:
        for rd in reads:
            print(f"     - id={rd[0]} created={rd[1]} ip={rd[5]} pages={rd[2]} bw={rd[3]} color={rd[4]}")
    else:
        print("     ❌ SEM LEITURAS (nenhuma Reading criada!)")
else:
    print("   ❌ Cliente FJ37S3W6 não existe no banco!")

print("\n" + "=" * 80)
print("FIM DEBUG")
print("=" * 80)
conn.close()
