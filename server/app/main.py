from fastapi import FastAPI, __version__ as fastapi_version
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute as _APIRoute
from sqlalchemy import text

from app.config import settings
from app.database import Agent, Client, Location, Partner, Printer, User, init_db, SessionLocal, engine
from app.routes import router, hash_password
from app.routes import __name__ as _routes_mod_name  # garantia import deu certo
import app.schemas as _schemas_mod  # garantia que ReadingOut existe agora (para nao crashar runtime)
import os, sys, time, warnings


_EXPECTED_FASTAPI_MIN = "0.110"
_EXPECTED_FASTAPI_MAX = "0.116"
def _ver_supported() -> bool:
    try:
        parts = [int(x) for x in fastapi_version.split(".")[:3]]
        lo = [int(x) for x in _EXPECTED_FASTAPI_MIN.split(".")]
        hi = [int(x) for x in _EXPECTED_FASTAPI_MAX.split(".")]
        ok_lo = all(a >= b for a, b in zip(parts, lo)) or parts >= lo[: len(parts)]
        ok_hi = parts <= hi[: len(parts)]
        return ok_lo and ok_hi
    except Exception:
        return False


if not _ver_supported():
    warnings.warn(
        f"FASTAPI VERSION MISMATCH! Expectada ~{_EXPECTED_FASTAPI_MIN}-{_EXPECTED_FASTAPI_MAX}, "
        f"rodando {fastapi_version}. Usando workaround de registro de rotas robusto.",
        RuntimeWarning,
        stacklevel=2,
    )


def _robust_include_router(app: FastAPI, r) -> int:
    """Registra rotas de um APIRouter SEM depender do app.include_router.
       Compativel com FastAPI 0.110 - 0.145+ e Starlette 0.38 - 1.x.
       Contorna bug de include_router em versoes novas/desatualizadas.
       Retorna nro de rotas efetivamente adicionadas.
    """
    added = 0
    sub = getattr(r, "routes", None) or []
    _SAFE_BASE_KWARGS = (
        "response_model",
        "status_code",
        "tags",
        "summary",
        "description",
        "dependencies",
        "response_class",
        "include_in_schema",
        "deprecated",
        "response_model_include",
        "response_model_exclude",
        "response_model_by_alias",
        "response_model_exclude_unset",
        "response_model_exclude_defaults",
        "response_model_exclude_none",
        "responses",
        "name",
        "operation_id",
    )
    for entry in sub:
        try:
            path = getattr(entry, "path", None)
            methods = getattr(entry, "methods", None) or set()
            endpoint = getattr(entry, "endpoint", None)
            if not path or not endpoint:
                continue
            methods_clean = set()
            for m in methods:
                if isinstance(m, str):
                    methods_clean.add(m.upper())
            if not methods_clean:
                methods_clean = {"GET"}
            kwargs = {}
            for attr in _SAFE_BASE_KWARGS:
                v = getattr(entry, attr, None)
                if v is not None:
                    kwargs[attr] = v
            try:
                app.add_api_route(path, endpoint, methods=sorted(methods_clean), **kwargs)
                added += 1
            except TypeError as te:
                msg = str(te).lower()
                bad_keys = set()
                if "unexpected keyword argument" in msg:
                    import re
                    for m in re.finditer(r"'([a-zA-Z_][a-zA-Z0-9_]*)'", msg):
                        bad_keys.add(m.group(1))
                filtered = {k: v for k, v in kwargs.items() if k not in bad_keys}
                try:
                    app.add_api_route(path, endpoint, methods=sorted(methods_clean), **filtered)
                    added += 1
                except Exception as ex_inner:
                    try:
                        app.add_api_route(path, endpoint, methods=sorted(methods_clean))
                        added += 1
                    except Exception as ex_final:
                        print(
                            f"[WARN] Falha ao registrar rota {sorted(methods_clean)} {path}: {ex_inner} / {ex_final}",
                            file=sys.stderr,
                        )
        except Exception as ex:
            print(f"[WARN] Erro processando entrada rota: {ex}", file=sys.stderr)
    return added


def _parceiro_cea(db, partner_id_atual: int | None) -> Partner | None:
    if partner_id_atual:
        atual = db.query(Partner).filter(Partner.id == partner_id_atual).first()
        if atual is not None:
            return atual

    def _nome_cea(nome: str) -> bool:
        texto = (nome or "").lower()
        return "copiadora" in texto or "c&a" in texto or "cea" in texto

    candidatos = [p for p in db.query(Partner).all() if _nome_cea(p.name)]
    if not candidatos:
        return None
    return max(
        candidatos,
        key=lambda p: db.query(Client).filter(Client.partner_id == p.id).count(),
    )


def seed_demo_data() -> None:
    db = SessionLocal()
    try:
        # Julio continua superadmin. Financeiro e o revendedor da CEA.
        reset_pwd = (os.environ.get("RESET_JULIO_PASSWORD") or "").strip()
        default_pwd_julio = "CeaJulio2026!"

        email_julio = "julio@ceacopiadoras.com.br"
        julio = (
            db.query(User)
            .filter((User.username == "julio") | (User.email == email_julio))
            .first()
        )
        hash_julio = hash_password(reset_pwd or default_pwd_julio)
        if julio is None:
            julio = User(
                username="julio",
                email=email_julio,
                hashed_password=hash_julio,
                role="superadmin",
                active=True,
            )
            db.add(julio)
        else:
            julio.username = "julio"
            julio.email = email_julio
            julio.hashed_password = hash_julio
            julio.role = "superadmin"
            julio.active = True
        db.flush()

        email_fin = "financeiro@ceacopiadoras.com.br"
        financeiro = (
            db.query(User)
            .filter((User.username == "financeiro") | (User.email == email_fin))
            .first()
        )
        parceiro = _parceiro_cea(db, financeiro.partner_id if financeiro else None)
        hash_fin = hash_password("financeiro")
        if financeiro is None:
            financeiro = User(
                username="financeiro",
                email=email_fin,
                hashed_password=hash_fin,
                role="partner_admin" if parceiro is not None else "superadmin",
                partner_id=parceiro.id if parceiro is not None else None,
                client_id=None,
                active=True,
            )
            db.add(financeiro)
        else:
            financeiro.username = "financeiro"
            financeiro.email = email_fin
            financeiro.hashed_password = hash_fin
            financeiro.client_id = None
            financeiro.active = True
            if parceiro is not None:
                financeiro.role = "partner_admin"
                financeiro.partner_id = parceiro.id
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


def _corrigir_contador_papelaria_c308() -> None:
    """Coleta de 02/10/2026 10:20 ja veio certa. O site segurou o geral no preto."""
    import json
    from app.database import Printer, Reading, SessionLocal

    serial = "A7PY012000472"
    bw, color, total = 159483, 270558, 430068
    # Divisao do painel do mesmo dia. A soma fecha os 3 cards.
    detalhe = json.dumps(
        {
            "geral": total,
            "copia_pb": 59039,
            "impressao_pb": 100444,
            "copia_cor": 66035,
            "impressao_cor": 204523,
        },
        separators=(",", ":"),
    )
    db = SessionLocal()
    try:
        printer = db.query(Printer).filter(Printer.serial_number.ilike(serial)).first()
        if printer is None:
            return
        atual_bw = int(printer.pages_bw or 0)
        atual_color = int(printer.pages_color or 0)
        atual_total = int(printer.pages_total or 0)
        mudou = False
        if not (atual_bw == bw and atual_color == color and atual_total == total):
            if atual_color > 0 and (atual_bw + atual_color) > int(total * 1.2):
                printer.pages_bw = bw
                printer.pages_color = color
                printer.pages_total = total
                ultima = (
                    db.query(Reading)
                    .filter(Reading.printer_id == printer.id)
                    .order_by(Reading.collected_at.desc(), Reading.id.desc())
                    .first()
                )
                if ultima is not None:
                    ultima.pages_bw = bw
                    ultima.pages_color = color
                    ultima.pages_total = total
                mudou = True
        if int(printer.pages_bw or 0) == bw and int(printer.pages_color or 0) == color:
            if (getattr(printer, "counter_detail", None) or "") != detalhe:
                printer.counter_detail = detalhe
                mudou = True
        if mudou:
            db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print("[WARN] correcao papelaria C308:", repr(exc), file=sys.stderr)
    finally:
        db.close()


def _vincular_prefeitura_santa_rita_cea() -> None:
    """Liga o cliente na revenda CEA. Nao apaga impressora, leitura nem usuario."""
    db = SessionLocal()
    try:
        clientes = (
            db.query(Client)
            .filter(Client.name.ilike("%santa rita%itueta%"))
            .all()
        )
        if len(clientes) != 1:
            return
        cliente = clientes[0]
        parceiros = db.query(Partner).filter(Partner.name.ilike("%copiadora%")).all()
        escolhido = None
        for parceiro in parceiros:
            nome = (parceiro.name or "").lower()
            if "c&a" in nome or "cea" in nome:
                escolhido = parceiro
                break
        if escolhido is None and len(parceiros) == 1:
            escolhido = parceiros[0]
        if escolhido is None or cliente.partner_id == escolhido.id:
            return
        cliente.partner_id = escolhido.id
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print("[WARN] vinculo prefeitura santa rita:", repr(exc), file=sys.stderr)
    finally:
        db.close()


def _safe_init_db() -> None:
    try:
        init_db()
        seed_demo_data()
        _corrigir_contador_papelaria_c308()
        _vincular_prefeitura_santa_rita_cea()
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

    @app.on_event("startup")
    def _startup_contadores() -> None:
        _safe_init_db()

    origins = []
    for origin in settings.cors_origins.split(","):
        item = origin.strip()
        low = item.lower()
        if not item or "vercel.app" in low or "onrender.com" in low:
            continue
        origins.append(item)
    origin_regex = settings.cors_origin_regex
    if any(token in origin_regex for token in ("vercel.app", "onrender.com", "192.168", "10(?:")):
        origin_regex = r"^https://(www\.)?printcollect\.com\.br$|^http://(localhost|127\.0\.0\.1)(:\d+)?$"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _api_routes_added = _robust_include_router(app, router)

    @app.get("/", include_in_schema=False)
    @app.head("/", include_in_schema=False)
    def root():
        return {"status": "ok", "service": "print-collect-api", "message": "Welcome. Use /health for status check."}

    @app.get("/health", include_in_schema=False)
    @app.head("/health", include_in_schema=False)
    def health():
        return {
            "status": "ok",
            "service": "print-collect-api",
            "version": "0.1.0",
            "message": "Use /health-db to check database connectivity",
        }

    @app.get("/health-db", include_in_schema=False)
    @app.head("/health-db", include_in_schema=False)
    def health_db():
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
        rotas_api = 0
        for r in app.routes:
            if hasattr(r, "path") and hasattr(r, "methods"):
                p = str(getattr(r, "path", ""))
                if p.startswith("/api"):
                    rotas_api += 1
                rotas.append(f"{sorted(list(r.methods or set()))!s} {p!s}")
        return {
            "status": "ok",
            "initialized_at_unix": int(time.time()),
            "python_version": sys.version.split()[0],
            "fastapi_version": fastapi_version,
            "fastapi_supported": _ver_supported(),
            "routes_total": len(app.routes),
            "routes_api_count": rotas_api,
            "api_routes_added_by_workaround": _api_routes_added,
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
