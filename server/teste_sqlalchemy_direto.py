import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app"))

from datetime import datetime, timezone, timedelta
from sqlalchemy import or_ as sql_or
from sqlalchemy.sql import false as sql_false
from app.database import SessionLocal, engine, Base
from app.database import Agent, Printer, Reading
from app.config import settings

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

print("=" * 95)
print("TESTE DIRETO SQLALCHEMY - MESMA LOGICA DA ROTA /api/agent/report (SEM HTTP)")
print("=" * 95)

print(f"\n[0] Conectado? engine.url = {engine.url}")
print(f"    NullPool? {settings.database_url[:40]} ... NullPool ok")

TOKEN_AG18 = "Bn0scR38P6qPwovEbM-P2_hV60fAINebWVVJpYLiuj8"
r_ip = "192.168.15.220"
r_mac = None
r_serial = "T597H301772"
r_model = "RICOH SP 4510SF"
r_manufacturer = "Ricoh"
r_status = "online"
r_pages_total = 167654
r_pages_bw = 167654
r_pages_color = 0
r_toner_black = 68.0
r_toner_cyan = None
r_toner_magenta = None
r_toner_yellow = None

db = SessionLocal()
try:
    now = _now()
    print(f"\n[1] Buscando agente com token...")
    agent = db.query(Agent).filter(Agent.api_token == TOKEN_AG18).first()
    if not agent:
        print("   ❌ AGENTE NAO ENCONTRADO")
        sys.exit(1)
    print(f"   ✅ agente id={agent.id} | cliente_id={agent.client_id} | {agent.name}")

    print(f"\n[2] UPSERT impressora igual rota agent_report L2404-2547:")
    _ip_filter = Printer.ip_address.ilike(r_ip)
    printer = (
        db.query(Printer)
        .filter(Printer.client_id == agent.client_id, _ip_filter)
        .first()
    )
    if not printer and r_serial:
        printer = (
            db.query(Printer)
            .filter(Printer.client_id == agent.client_id, Printer.serial_number.ilike(r_serial))
            .first()
        )
    criou_nova = False
    if not printer:
        print(f"   Não achou impressora no cliente {agent.client_id}. CRIANDO NOVA.")
        printer = Printer(client_id=agent.client_id, ip_address=r_ip)
        db.add(printer)
        criou_nova = True
    else:
        print(f"   Achou impressora existente id={printer.id}")

    # Campos do printer
    printer.ip_address = r_ip
    if r_mac: printer.mac_address = r_mac
    if r_serial: printer.serial_number = r_serial
    if r_model: printer.model = r_model
    if r_manufacturer: printer.manufacturer = r_manufacturer
    printer.status = r_status
    try:
        if r_pages_total and r_pages_total > int(printer.pages_total or 0):
            printer.pages_total = r_pages_total
    except: pass
    try:
        if r_pages_bw and r_pages_bw > int(printer.pages_bw or 0):
            printer.pages_bw = r_pages_bw
    except: pass
    try:
        if r_pages_color and r_pages_color > int(printer.pages_color or 0):
            printer.pages_color = r_pages_color
    except: pass
    printer.toner_black = r_toner_black
    printer.toner_cyan = r_toner_cyan
    printer.toner_magenta = r_toner_magenta
    printer.toner_yellow = r_toner_yellow
    # Força PB
    printer.toner_cyan = None
    printer.toner_magenta = None
    printer.toner_yellow = None
    printer.last_seen = now
    printer.updated_at = now

    print(f"\n[3] FLUSH obrigatório (captura FK printer.id se era nova)")
    try:
        db.flush()
        print(f"   ✅ FLUSH OK. printer.id={printer.id}")
    except Exception as e_flush:
        print(f"   ❌ FLUSH ERROR: {e_flush}")
        db.rollback()
        raise

    print(f"\n[4] Cria reading nova:")
    reading_row = Reading(
        printer_id=printer.id,
        pages_total=int(printer.pages_total or 0),
        pages_bw=int(printer.pages_bw or 0),
        pages_color=int(printer.pages_color or 0),
        toner_black=printer.toner_black,
        toner_cyan=printer.toner_cyan,
        toner_magenta=printer.toner_magenta,
        toner_yellow=printer.toner_yellow,
        status="online",
        collected_at=now,
    )
    db.add(reading_row)
    db.flush()
    print(f"   ✅ Reading criada id={reading_row.id}")

    agent.last_heartbeat = now

    print(f"\n[5] 🔥 COMMIT FINAL 1ª tentativa:")
    try:
        db.commit()
        print(f"   ✅ COMMIT 1 OK (sem exception)")
    except Exception as e1:
        print(f"   ❌ COMMIT 1 FALHOU: {e1}")
        db.rollback()
        try:
            print(f"\n[5b] Tentando COMMIT 2ª vez após rollback parcial:")
            agent.last_heartbeat = now
            db.commit()
            print(f"   ✅ COMMIT 2 OK")
        except Exception as e2:
            print(f"   ❌ COMMIT 2 FALHOU TAMBÉM: {e2}")
            raise

    # Validação final: reabre sessão nova e consulta
    print(f"\n[6] VALIDAÇÃO: abre Session NOVA e consulta impressora no banco real:")
    db2 = SessionLocal()
    try:
        p_nova = (
            db2.query(Printer)
            .filter(Printer.client_id == agent.client_id, Printer.ip_address.ilike(r_ip))
            .first()
        )
        if p_nova:
            print(f"   ✅ IMPRESSORA EXISTE NO BANCO id={p_nova.id} cliente={p_nova.client_id}")
            print(f"      pages_total={p_nova.pages_total} last_seen={p_nova.last_seen}")
            r_nova = (
                db2.query(Reading)
                .filter(Reading.printer_id == p_nova.id)
                .order_by(Reading.id.desc())
                .first()
            )
            if r_nova:
                print(f"   ✅ READING EXISTE id={r_nova.id} coletada_em={r_nova.collected_at} pag={r_nova.pages_total}")
            else:
                print(f"   ❌ READING NÃO EXISTE - COMMIT FANTASMA! Reading sumiu!")
        else:
            print(f"   ❌ IMPRESSORA NÃO EXISTE NO BANCO CLIENTE {agent.client_id}! COMMIT FANTASMA!")
    finally:
        db2.close()

finally:
    db.close()

print("\n" + "=" * 95)
print("FIM DO TESTE DIRETO SQLALCHEMY")
print("=" * 95)
