from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import Agent, Client, Location, Printer, init_db, SessionLocal, engine
from app.routes import router


def seed_demo_data() -> None:
    db = SessionLocal()
    try:
        if db.query(Client).count() > 0:
            return

        client = Client(
            name="Empresa Exemplo Ltda",
            cnpj="12.345.678/0001-90",
            contact_name="João Silva",
            contact_email="joao@empresa.com",
            contact_phone="(11) 99999-0000",
            address="Av. Paulista, 1000 - São Paulo/SP",
        )
        db.add(client)
        db.flush()

        location = Location(
            client_id=client.id,
            name="Matriz",
            sector="Administrativo",
            responsible="Maria Santos",
        )
        db.add(location)
        db.flush()

        db.add(
            Printer(
                client_id=client.id,
                location_id=location.id,
                ip_address="192.168.1.100",
                serial_number="DEMO001",
                model="HP LaserJet Pro M404dn",
                manufacturer="HP",
                status="online",
                pages_total=15420,
                pages_bw=15420,
                pages_color=0,
                toner_black=45.0,
            )
        )

        db.add(
            Agent(
                client_id=client.id,
                name="Agente Matriz",
                api_token=settings.api_key,
            )
        )

        db.commit()
    finally:
        db.close()


def _safe_init_db() -> None:
    try:
        init_db()
        if not settings.is_postgres:
            seed_demo_data()
    except Exception as e:
        import traceback
        import sys
        print("[WARN] init_db falhou (provavelmente rede intermitente no cold-start):", repr(e), file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Print Collect API",
        description="API para coleta e gestão de impressoras alugadas",
        version="0.1.0",
    )

    origins = [o.strip() for o in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.on_event("startup")
    def on_startup():
        _safe_init_db()

    @app.get("/health")
    def health():
        db_status = "unknown"
        db_error = None
        try:
            _safe_init_db()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_status = "postgresql" if settings.is_postgres else "sqlite"
        except Exception as e:
            db_status = "error"
            db_error = str(e)[:200]
        payload = {
            "status": "ok",
            "database": db_status,
        }
        if db_error:
            payload["error"] = db_error
        return payload

    return app


app = create_app()
