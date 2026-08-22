import ssl
import pg8000.native

PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"

ssl_ctx = ssl.create_default_context()
print("[1] Conectando Neon PostgreSQL...")
conn = pg8000.native.Connection(PG_USER, password=PG_PASS, host=PG_HOST, database=PG_DB, ssl_context=ssl_ctx)
print("[OK] conectado!\n")

def cols(cur):
    try:
        return [d[0] for d in (getattr(conn, 'description', None) or [])]
    except Exception:
        return []

def q(sql, params=None):
    try:
        rows = conn.run(sql, *params) if params else conn.run(sql)
        print(f"   ↳ {len(rows)} linhas. Colunas: {cols(rows)}")
        return rows
    except Exception as e:
        print(f"   ❌ ERRO SQL: {e}")
        return []

print("=" * 80)
print("DEBUG BANCO NEON - CONSULTAS MANUAIS")
print("=" * 80)

print("\n[1] LISTA DE TABELAS (verificar se conectou no banco CERTO):")
r = q("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
for row in r:
    print(f"    - {row[0]}")

print("\n[2] TOTAL CLIENTES (clients):")
r = q("SELECT COUNT(*), MIN(id), MAX(id) FROM clients")
for row in r:
    print(f"    Total={row[0]} min_id={row[1]} max_id={row[2]}")

print("\n[3] ÚLTIMOS 5 CLIENTES (últimos cadastrados):")
r = q("SELECT id, name, partner_id, client_code, active, created_at FROM clients ORDER BY id DESC LIMIT 5")
for row in r:
    print(f"    id={row[0]} | name={row[1]!r} | partner_id={row[2]} | code={row[3]} | active={row[4]} | created={row[5]}")

print("\n[4] BUSCA Posto Falcão OU id=225 (nome ilike, id específico):")
r = q("SELECT id, name, partner_id, client_code FROM clients WHERE id = 225 OR name ILIKE $1 ORDER BY id DESC", ["%POSTO FALCAO%"])
if r:
    for row in r:
        print(f"    ENCONTRADO id={row[0]} name={row[1]!r} partner_id={row[2]} code={row[3]}")
        pid = row[2]
        if pid:
            rp = q("SELECT id, name FROM partners WHERE id = $1", [pid])
            for p in rp:
                print(f"        → parceiro id={p[0]} name={p[1]!r}")
else:
    print("    ❌ NÃO ENCONTRADO (id=225 / nome Posto Falcão)")

print("\n[5] TOTAL AGENTES + últimos 5 agentes (api_tokens):")
r = q("SELECT COUNT(*), MIN(id), MAX(id) FROM agents")
for row in r:
    print(f"    Total agents: {row[0]}")
r = q("SELECT id, client_id, name, hostname, api_token, last_heartbeat FROM agents ORDER BY id DESC LIMIT 5")
for row in r:
    token = (row[4][:20] + "...") if row[4] and len(row[4]) > 20 else row[4]
    print(f"    Agent id={row[0]} | client_id={row[1]} | name={row[2]!r} | host={row[3]!r} | token_20={token!r} | last_hb={row[5]}")

print("\n[6] BUSCA ESPECÍFICA por TOKEN Julio da config.yaml local: 'vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ'")
r = q("SELECT id, client_id, name, hostname, last_heartbeat, paired_at FROM agents WHERE api_token = $1 LIMIT 1",
      ["vxMhcBoMFidNDS6ha3mo30PyzfR23UFMDi7Ij1Qb7AQ"])
if r:
    for row in r:
        print(f"    ✅ TOKEN ENCONTRADO! agent_id={row[0]} | client_id={row[1]} | name={row[2]!r} | host={row[3]!r} | last_hb={row[4]} | paired_at={row[5]}")
        cid = row[1]
        rc = q("SELECT id, name, partner_id, client_code FROM clients WHERE id = $1 LIMIT 1", [cid])
        if rc:
            for c in rc:
                pid = c[2]
                pname = None
                if pid:
                    rp = q("SELECT name FROM partners WHERE id = $1", [pid])
                    if rp:
                        pname = rp[0][0]
                print(f"        → Cliente vinculado id={c[0]} name={c[1]!r} partner_id={pid} ({pname!r}) code={c[3]}")
else:
    print("    ❌ TOKEN NÃO EXISTE NO BANCO (config.yaml local tem token que não está cadastrado!)")

print("\n[7] TOTAL IMPRESSORAS + ÚLTIMAS 10 impressoras cadastradas (RICOH?):")
r = q("SELECT COUNT(*), MIN(id), MAX(id) FROM printers")
for row in r:
    print(f"    Total printers: {row[0]}")
r = q("SELECT id, client_id, ip_address, model, serial_number, last_seen FROM printers ORDER BY id DESC LIMIT 10")
if r:
    for row in r:
        cname = None
        if row[1]:
            rc = q("SELECT name FROM clients WHERE id = $1 LIMIT 1", [row[1]])
            if rc:
                cname = rc[0][0]
        print(f"    id={row[0]} | cid={row[1]} [{cname!r}] | ip={row[2]!r} | model={row[3]!r} | serial={row[4]!r} | last_seen={row[5]}")

print("\n[8] IMPRESSORAS COM ip_address ILIKE 192.168.15.220 OU model ILIKE RICOH SP 4510SF:")
r = q("SELECT id, client_id, ip_address, model, last_seen FROM printers WHERE ip_address ILIKE $1 OR model ILIKE $2 ORDER BY id DESC LIMIT 10",
      ["%192.168.15.220%", "%RICOH SP 4510SF%"])
if r:
    for row in r:
        cname = None
        if row[1]:
            rc = q("SELECT name, partner_id FROM clients WHERE id = $1 LIMIT 1", [row[1]])
            if rc:
                cname = rc[0][0]
                pid = rc[0][1]
                pname = None
                if pid:
                    rp = q("SELECT name FROM partners WHERE id = $1", [pid])
                    if rp:
                        pname = rp[0][0]
                print(f"    printer_id={row[0]} | client_id={row[1]} name={cname!r} partner={pname!r} ip={row[2]!r} model={row[3]!r} last_seen={row[4]}")
else:
    print("    ❌ Nenhuma RICOH / 192.168.15.220 no banco!")

print("\n[9] CLIENTE CEA COPIADORAS (client_code FJ37S3W6 + seus agentes + readings):")
r = q("SELECT id, name, partner_id, client_code FROM clients WHERE client_code = $1 LIMIT 1", ["FJ37S3W6"])
if r:
    cid = r[0][0]
    cname = r[0][1]
    pid = r[0][2]
    pname = None
    if pid:
        rp = q("SELECT name FROM partners WHERE id = $1", [pid])
        if rp:
            pname = rp[0][0]
    print(f"    ✅ CLIENTE id={cid} name={cname!r} partner_id={pid} ({pname!r}) code={r[0][3]}")
    print("    → Ultimos 3 agentes deste cliente:")
    ra = q("SELECT id, hostname, last_heartbeat, paired_at FROM agents WHERE client_id = $1 ORDER BY id DESC LIMIT 3", [cid])
    for a in ra:
        print(f"        agent_id={a[0]} host={a[1]!r} last_hb={a[2]} paired_at={a[3]}")
    print("    → Ultimas 5 leituras (Readings) deste cliente:")
    rr = q(
        "SELECT rd.id, rd.created_at, rd.pages_total, p.ip_address "
        "FROM readings rd JOIN printers p ON p.id = rd.printer_id "
        "WHERE p.client_id = $1 ORDER BY rd.created_at DESC LIMIT 5", [cid]
    )
    if rr:
        for rd in rr:
            print(f"        reading id={rd[0]} created_at={rd[1]} pages_total={rd[2]} ip={rd[3]!r}")
    else:
        print("        ❌ ZERO readings (nenhuma Reading criada nunca!)")
else:
    print("    ❌ NÃO ENCONTRADO CLIENTE COM CODIGO FJ37S3W6")

print("\n" + "=" * 80)
print("FIM DEBUG")
print("=" * 80)
conn.close()
