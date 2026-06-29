from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Agent, Client, Location, Printer, init_db, SessionLocal
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
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.on_event("startup")
    def on_startup():
        init_db()
        if not settings.is_postgres:
            seed_demo_data()

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "database": "postgresql" if settings.is_postgres else "sqlite",
        }

    return app


app = create_app()
