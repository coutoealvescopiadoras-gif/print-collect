from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./printcollect.db"
    direct_url: Optional[str] = None
    secret_key: str = "change-me-in-production"
    api_key: str = "agent-dev-key"
    cors_origins: str = "http://localhost:5173"
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
    alert_email_recipients: Optional[str] = None  # Comma-separated list

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
