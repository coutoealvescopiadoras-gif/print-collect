from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings


class Base(DeclarativeBase):
    pass


class Partner(Base):
    __tablename__ = "partners"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)
    logo_url = Column(String(500), nullable=True)
    logo_data = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    clients = relationship("Client", back_populates="partner")
    users = relationship("User", back_populates="partner")


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)
    name = Column(String(200), nullable=False)
    cnpj = Column(String(20), unique=True, nullable=True)
    contact_name = Column(String(200), nullable=True)
    contact_email = Column(String(200), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    client_code = Column(String(16), unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    partner = relationship("Partner", back_populates="clients")
    locations = relationship("Location", back_populates="client", cascade="all, delete-orphan")
    printers = relationship("Printer", back_populates="client", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="client", cascade="all, delete-orphan")
    users = relationship("User", back_populates="client", cascade="all, delete-orphan")


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    name = Column(String(200), nullable=False)
    sector = Column(String(200), nullable=True)
    responsible = Column(String(200), nullable=True)
    address = Column(Text, nullable=True)

    client = relationship("Client", back_populates="locations")
    printers = relationship("Printer", back_populates="location")


class Printer(Base):
    __tablename__ = "printers"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    ip_address = Column(String(45), nullable=False)
    mac_address = Column(String(20), nullable=True)
    serial_number = Column(String(100), nullable=True, index=True)
    model = Column(String(200), nullable=True)
    manufacturer = Column(String(100), nullable=True)
    status = Column(String(50), default="unknown")
    pages_total = Column(Integer, default=0)
    pages_bw = Column(Integer, default=0)
    pages_color = Column(Integer, default=0)
    toner_black = Column(Float, nullable=True)
    toner_cyan = Column(Float, nullable=True)
    toner_magenta = Column(Float, nullable=True)
    toner_yellow = Column(Float, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    active = Column(Boolean, default=True, nullable=False)
    ignored = Column(Boolean, default=False, nullable=False, index=True)

    client = relationship("Client", back_populates="printers")
    location = relationship("Location", back_populates="printers")
    alerts = relationship("Alert", back_populates="printer", cascade="all, delete-orphan")
    readings = relationship("Reading", back_populates="printer", cascade="all, delete-orphan")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    printer_id = Column(Integer, ForeignKey("printers.id"), nullable=False)
    alert_type = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String(20), default="warning")
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)

    printer = relationship("Printer", back_populates="alerts")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    name = Column(String(200), nullable=False)
    api_token = Column(String(100), unique=True, nullable=False)
    last_heartbeat = Column(DateTime, nullable=True)
    version = Column(String(50), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    hostname = Column(String(200), nullable=True)
    remote_ip = Column(String(45), nullable=True)
    pairing_code = Column(String(16), unique=True, nullable=True)
    pairing_expires_at = Column(DateTime, nullable=True)
    paired_at = Column(DateTime, nullable=True)

    client = relationship("Client", back_populates="agents")


class Reading(Base):
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)
    printer_id = Column(Integer, ForeignKey("printers.id"), nullable=False)
    pages_total = Column(Integer, default=0)
    pages_bw = Column(Integer, default=0)
    pages_color = Column(Integer, default=0)
    toner_black = Column(Float, nullable=True)
    toner_cyan = Column(Float, nullable=True)
    toner_magenta = Column(Float, nullable=True)
    toner_yellow = Column(Float, nullable=True)
    status = Column(String(50), default="online")
    collected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    agent_ip_address = Column(String(45), nullable=True)

    printer = relationship("Printer", back_populates="readings")


# =====================================================================
# HistoricoColeta — 4ª camada de defesa. Registro VALIDADO pós regras
# de monotonicidade/anti-inchado/detecção de pico. Base para cobrança!
# =====================================================================
class HistoricoColeta(Base):
    __tablename__ = "historico_coletas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    printer_id = Column(Integer, ForeignKey("printers.id"), nullable=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clients.id"), nullable=True, index=True)
    ip_impressora = Column(String(50), nullable=False, index=True)
    fabricante = Column(String(100), nullable=True)
    modelo = Column(String(200), nullable=True)
    tipo_contador = Column(String(20), nullable=False, index=True)  # PB | COLOR | TOTAL
    valor_contador = Column(Integer, nullable=False)
    status_coleta = Column(String(40), nullable=False, default="SUCESSO", index=True)
    valor_anterior = Column(Integer, nullable=True)
    delta_paginas = Column(Integer, nullable=True)
    observacao = Column(Text, nullable=True)
    data_registro = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="superadmin")
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    partner_id = Column(Integer, ForeignKey("partners.id"), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    client = relationship("Client", back_populates="users")
    partner = relationship("Partner", back_populates="users")


_engine_kwargs: dict = {"pool_pre_ping": True}

def _fix_postgres_driver(url: str) -> str:
    """Forca o uso do driver psycopg 3 (postgresql+psycopg://) que temos no
    requirements.txt, evitando que o SQLAlchemy use o dialeto padrao psycopg 2
    (postgresql://  sem driver) que causa ModuleNotFoundError: No module named
    'psycopg2' em runtime (pois usamos psycopg[binary]==3.x).
    """
    if url.startswith("postgresql+psycopg:"):
        return url
    if url.startswith("postgresql+psycopg2:"):
        return "postgresql+psycopg:" + url[len("postgresql+psycopg2:"):]
    if url.startswith("postgresql:"):
        return "postgresql+psycopg:" + url[len("postgresql:"):]
    return url

_db_url = _fix_postgres_driver(settings.database_url)
_mig_url = _fix_postgres_driver(settings.migration_url)

if settings.database_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif True:
    _engine_kwargs["poolclass"] = NullPool
    _engine_kwargs["connect_args"] = {"connect_timeout": 10}

engine = create_engine(_db_url, **_engine_kwargs)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)

_migration_engine = None


def _get_migration_engine():
    global _migration_engine
    if _migration_engine is None:
        _migration_engine = create_engine(
            _mig_url,
            pool_pre_ping=True,
            poolclass=NullPool,
            connect_args={"connect_timeout": 10},
        )
    return _migration_engine


def _ensure_user_multitenancy_columns(target_engine) -> None:
    inspector = inspect(target_engine)
    if "users" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    statements: list[str] = []

    if "role" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN role VARCHAR(50) DEFAULT 'superadmin'")
    if "client_id" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN client_id INTEGER NULL")

    if not statements:
        return

    with target_engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(text("UPDATE users SET role = 'superadmin' WHERE role IS NULL"))


def _ensure_partner_multitenancy_columns(target_engine) -> None:
    inspector = inspect(target_engine)
    table_names = set(inspector.get_table_names())
    statements: list[str] = []

    if "partners" in table_names:
        existing_columns = {column["name"] for column in inspector.get_columns("partners")}
        if "logo_url" not in existing_columns:
            statements.append("ALTER TABLE partners ADD COLUMN logo_url VARCHAR(500) NULL")
        if "logo_data" not in existing_columns:
            statements.append("ALTER TABLE partners ADD COLUMN logo_data TEXT NULL")

    if "clients" in table_names:
        existing_columns = {column["name"] for column in inspector.get_columns("clients")}
        if "partner_id" not in existing_columns:
            statements.append("ALTER TABLE clients ADD COLUMN partner_id INTEGER NULL")

    if "users" in table_names:
        existing_columns = {column["name"] for column in inspector.get_columns("users")}
        if "partner_id" not in existing_columns:
            statements.append("ALTER TABLE users ADD COLUMN partner_id INTEGER NULL")

    if not statements:
        return

    with target_engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_agent_pairing_columns(target_engine) -> None:
    inspector = inspect(target_engine)
    table_names = set(inspector.get_table_names())
    if "agents" not in table_names:
        return
    existing_columns = {column["name"] for column in inspector.get_columns("agents")}
    statements: list[str] = []
    if "hostname" not in existing_columns:
        statements.append("ALTER TABLE agents ADD COLUMN hostname VARCHAR(200) NULL")
    if "remote_ip" not in existing_columns:
        statements.append("ALTER TABLE agents ADD COLUMN remote_ip VARCHAR(45) NULL")
    if "pairing_code" not in existing_columns:
        statements.append("ALTER TABLE agents ADD COLUMN pairing_code VARCHAR(16) NULL")
    if "pairing_expires_at" not in existing_columns:
        statements.append("ALTER TABLE agents ADD COLUMN pairing_expires_at DATETIME NULL")
    if "paired_at" not in existing_columns:
        statements.append("ALTER TABLE agents ADD COLUMN paired_at DATETIME NULL")
    if not statements:
        return
    with target_engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_client_code_column(target_engine) -> None:
    inspector = inspect(target_engine)
    table_names = set(inspector.get_table_names())
    if "clients" not in table_names:
        return
    existing_columns = {column["name"] for column in inspector.get_columns("clients")}
    statements: list[str] = []
    if "client_code" not in existing_columns:
        statements.append("ALTER TABLE clients ADD COLUMN client_code VARCHAR(16) NULL")
    if not statements:
        return
    with target_engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        try:
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_clients_client_code ON clients(client_code) WHERE client_code IS NOT NULL"))
        except Exception:
            pass


def init_db() -> None:
    if settings.auto_create_tables:
        target = _get_migration_engine() if settings.is_postgres else engine
        Base.metadata.create_all(bind=target)
        _ensure_user_multitenancy_columns(target)
        _ensure_partner_multitenancy_columns(target)
        _ensure_agent_pairing_columns(target)
        _ensure_client_code_column(target)


def get_db():
    db = SessionLocal()
    try:
        try:
            db.connection()
        except Exception:
            try:
                db.close()
            except Exception:
                pass
            db = SessionLocal()
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass
