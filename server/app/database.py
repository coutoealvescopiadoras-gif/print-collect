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
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings


class Base(DeclarativeBase):
    pass


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    cnpj = Column(String(20), unique=True, nullable=True)
    contact_name = Column(String(200), nullable=True)
    contact_email = Column(String(200), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    locations = relationship("Location", back_populates="client", cascade="all, delete-orphan")
    printers = relationship("Printer", back_populates="client", cascade="all, delete-orphan")
    agents = relationship("Agent", back_populates="client", cascade="all, delete-orphan")


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

    printer = relationship("Printer", back_populates="readings")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(200), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


_engine_kwargs: dict = {"pool_pre_ping": True}

if settings.database_url.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif "pgbouncer=true" in settings.database_url or ":6543/" in settings.database_url:
    # Transaction pooler do Supabase — evita prepared statements persistentes
    _engine_kwargs["poolclass"] = NullPool

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_migration_engine = None


def _get_migration_engine():
    global _migration_engine
    if _migration_engine is None:
        _migration_engine = create_engine(settings.migration_url, pool_pre_ping=True)
    return _migration_engine


def init_db() -> None:
    if settings.auto_create_tables:
        target = _get_migration_engine() if settings.is_postgres else engine
        Base.metadata.create_all(bind=target)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
