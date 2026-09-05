from fastapi import FastAPI, __version__ as fastapi_version
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import Agent, Client, Location, Printer, User, init_db, SessionLocal, engine
from app.routes import router, hash_password
from app.routes import __name__ as _routes_mod_name  # garantia import deu certo
import app.schemas as _schemas_mod  # garantia que ReadingOut existe agora (para nao crashar runtime)
import os, sys, time


def seed_demo_data() -> None:
    db = SessionLocal()
    try:
        # ---- PASSO 1: SUPERADMINS Julio + Financeiro (UPSERT SEMPRE, email lower) ----
        reset_pwd = (os.environ.get("RESET_JULIO_PASSWORD") or "").strip()
        default_pwd_julio = "CeaJulio2026!"
        default_pwd_fin = "CeaFinancas2026!"

        users_to_ensure = [
            ("julio",      "Julio@ceacopiadoras.com.br",      reset_pwd or default_pwd_julio),
            ("financeiro", "financeiro@ceacopiadoras.com.br", reset_pwd or default_pwd_fin),
        ]
        for username, email_orig, pwd in users_to_ensure:
            email_norm = email_orig.strip().lower()
            new_hash = hash_password(pwd)
            user = db.query(User).filter(User.email == email_norm).first()
            if user is None:
                user = User(
                    username=username,
                    email=email_norm,
                    hashed_password=new_hash,
                    role="superadmin",
                    active=True,
                )
                db.add(user)
            else:
                user.username = username
                user.email = email_norm
                user.hashed_password = new_hash
                user.role = "superadmin"
                user.active = True
            db.flush()

        # ---- PASSO 2: Dados exemplo (APENAS se nao tem NENHUM cliente ainda) ----
        if db.query(Client).count() == 0:
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

    @app.get("/debug-init")
    def debug_init():
        db_status = "unknown"
        db_error = None
        try:
            _safe_init_db()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_status = "postgresql" if settings.is_postgres else "sqlite"
        except Exception as e:
            db_status = "error"
            db_error = str(e)[:500]
        rotas = []
        for r in app.routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                rotas.append(f"{sorted(list(r.methods or set()))!s} {r.path!s}")
        return {
            "status": "ok",
            "initialized_at_unix": int(time.time()),
            "python_version": sys.version.split()[0],
            "fastapi_version": fastapi_version,
            "routes_total": len(app.routes),
            "cors_origins": settings.cors_origins[:300],
            "cors_regex_len": len(settings.cors_origin_regex or ""),
            "database_type": db_status,
            "database_error": db_error,
            "database_url_preview": (settings.database_url[:40] + "...") if settings.database_url and len(settings.database_url) > 40 else "***",
            "secret_key_preview": (settings.secret_key[:5] + "...") if len(settings.secret_key or "") > 5 else "?",
            "env_has_direct_url": bool(settings.direct_url),
            "imports": {
                "app.routes": _routes_mod_name or "ok",
                "app.schemas": f"OK (ReadingOut? {hasattr(_schemas_mod, 'ReadingOut')})" if 'app.schemas' in sys.modules else "NOT_IMPORTED",
            },
            "routes_sample": sorted(rotas)[:25],
        }

    return app


app = create_app()
