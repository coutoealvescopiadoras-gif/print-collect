import os
from typing import Optional
from pydantic_settings import BaseSettings


def _detect_database_url() -> str:
    candidates = [
        os.getenv("POSTGRES_URL"),
        os.getenv("POSTGRES_URL_NON_POOLING"),
        os.getenv("POSTGRES_PRISMA_URL"),
        os.getenv("DATABASE_URL"),
        os.getenv("DIRECT_URL"),
    ]
    for c in candidates:
        if c:
            c = c.strip()
            if c.startswith("postgres://"):
                c = "postgresql://" + c[len("postgres://"):]
            return c
    return "sqlite:///./printcollect.db"


def _detect_direct_url() -> Optional[str]:
    candidates = [
        os.getenv("POSTGRES_URL_NON_POOLING"),
        os.getenv("DIRECT_URL"),
    ]
    for c in candidates:
        if c:
            c = c.strip()
            if c.startswith("postgres://"):
                c = "postgresql://" + c[len("postgres://"):]
            return c
    return None


class Settings(BaseSettings):
    database_url: str = _detect_database_url()
    direct_url: Optional[str] = _detect_direct_url()
    secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")
    api_key: str = os.getenv("API_KEY", "agent-dev-key")
    cors_origins: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    )
    cors_origin_regex: str = os.getenv(
        "CORS_ORIGIN_REGEX",
        r"^https?://(printcollect\.com\.br|www\.printcollect\.com\.br|[a-zA-Z0-9-]+\.vercel\.app|[a-zA-Z0-9-]+\.onrender\.com|localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2})(:\d+)?$",
    )
    auto_create_tables: bool = True

    # Email configuration
    mail_username: Optional[str] = None
    mail_password: Optional[str] = None
    mail_from: Optional[str] = None
    mail_port: int = 587
    mail_server: str = "smtp.gmail.com"
    mail_starttls: bool = True
    mail_ssl_tls: bool = False
    mail_use_credentials: bool = True
    mail_validate_certs: bool = True

    # Email notifications
    alert_email_recipients: Optional[str] = None

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def migration_url(self) -> str:
        """Session pooler para operações que exigem conexão persistente."""
        if self.direct_url:
            return self.direct_url
        return self.database_url

    class Config:
        env_file = ".env"


settings = Settings()
