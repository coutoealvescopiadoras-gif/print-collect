from datetime import datetime
from typing import Optional, Any

from pydantic import BaseModel, Field, field_validator, model_validator


def _clean_str(value: Any, max_len: Optional[int] = None) -> Optional[str]:
    """Limpa strings: None -> None, strip, remove control chars, trunca.
    Se ficar vazio após limpeza, retorna None."""
    if value is None:
        return None
    s = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = " ".join(s.split())  # múltiplos espaços vira 1
    s = s.strip()
    if not s:
        return None
    if max_len is not None and len(s) > max_len:
        s = s[:max_len]
    return s


def _clean_ip(value: Any) -> str:
    """Limpa IP: sempre retorna uma string NÃO VAZIA.
    Trunca 45 chars (IPv6 max + zone). Valor inválido/vazio -> placeholder seguro."""
    if value is None:
        cleaned = None
    else:
        s = str(value).strip().replace("\r", "").replace("\n", "").replace("\t", "")
        s = s.strip().strip("[]")  # alguns agentes mandam [::1]
        s = s.split("%")[0]  # tira zone id de IPv6: fe80::1%eth0
        s = s.strip()
        cleaned = s if s else None
    if cleaned is None:
        # Placeholder SEGURO NÃO NULO (não causa NotNullViolation, e é único se não tem serial)
        # O usuário pode corrigir depois manualmente pelo painel.
        return "0.0.0.0"
    if len(cleaned) > 45:
        cleaned = cleaned[:45]
    return cleaned


def _clean_mac(value: Any) -> Optional[str]:
    """Limpa MAC: sempre 20 chars max, None se vazio."""
    return _clean_str(value, max_len=20)


class ClientBase(BaseModel):
    name: str
    cnpj: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    active: bool = True


class ClientCreate(ClientBase):
    pass


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    cnpj: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    active: Optional[bool] = None


class ClientOut(ClientBase):
    id: int
    partner_id: Optional[int] = None
    partner_name: Optional[str] = None
    client_code: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PartnerBase(BaseModel):
    name: str
    logo_url: Optional[str] = None
    logo_data: Optional[str] = None
    active: bool = True


class PartnerCreate(PartnerBase):
    pass


class PartnerUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
    logo_data: Optional[str] = None
    active: Optional[bool] = None


class PartnerOut(PartnerBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PartnerBillingStats(BaseModel):
    partner_id: int
    partner_name: str
    total_clients: int
    total_printers: int
    billable_printers: int
    online_printers: int
    offline_printers: int


class LocationBase(BaseModel):
    name: str
    sector: Optional[str] = None
    responsible: Optional[str] = None
    address: Optional[str] = None


class LocationCreate(LocationBase):
    client_id: int


class LocationOut(LocationBase):
    id: int
    client_id: int

    model_config = {"from_attributes": True}


class PrinterBase(BaseModel):
    ip_address: str
    mac_address: Optional[str] = None
    serial_number: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    location_id: Optional[int] = None

    @field_validator("ip_address", mode="before")
    @classmethod
    def _v_ip(cls, v: Any) -> str:
        return _clean_ip(v)

    @field_validator("mac_address", mode="before")
    @classmethod
    def _v_mac(cls, v: Any) -> Optional[str]:
        return _clean_mac(v)

    @field_validator("serial_number", mode="before")
    @classmethod
    def _v_serial(cls, v: Any) -> Optional[str]:
        return _clean_str(v, max_len=100)

    @field_validator("model", mode="before")
    @classmethod
    def _v_model(cls, v: Any) -> Optional[str]:
        return _clean_str(v, max_len=200)

    @field_validator("manufacturer", mode="before")
    @classmethod
    def _v_manufacturer(cls, v: Any) -> Optional[str]:
        return _clean_str(v, max_len=100)


class PrinterCreate(PrinterBase):
    client_id: int


class PrinterUpdate(BaseModel):
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None
    serial_number: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    location_id: Optional[int] = None
    status: Optional[str] = None

    @field_validator("ip_address", mode="before")
    @classmethod
    def _v_ip(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        return _clean_ip(v)

    @field_validator("mac_address", mode="before")
    @classmethod
    def _v_mac(cls, v: Any) -> Optional[str]:
        return _clean_mac(v)

    @field_validator("serial_number", mode="before")
    @classmethod
    def _v_serial(cls, v: Any) -> Optional[str]:
        return _clean_str(v, max_len=100)

    @field_validator("model", mode="before")
    @classmethod
    def _v_model(cls, v: Any) -> Optional[str]:
        return _clean_str(v, max_len=200)

    @field_validator("manufacturer", mode="before")
    @classmethod
    def _v_manufacturer(cls, v: Any) -> Optional[str]:
        return _clean_str(v, max_len=100)

    @field_validator("status", mode="before")
    @classmethod
    def _v_status(cls, v: Any) -> Optional[str]:
        return _clean_str(v, max_len=50)


class PrinterOut(PrinterBase):
    id: int
    client_id: int
    status: str
    pages_total: int
    pages_bw: int
    pages_color: int
    toner_black: Optional[float] = None
    toner_cyan: Optional[float] = None
    toner_magenta: Optional[float] = None
    toner_yellow: Optional[float] = None
    last_seen: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    active: bool = True
    ignored: bool = False
    client_name: str = ""
    partner_id: Optional[int] = None
    partner_name: Optional[str] = None

    model_config = {"from_attributes": True}


class AlertOut(BaseModel):
    id: int
    printer_id: int
    alert_type: str
    message: str
    severity: str
    resolved: bool
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AgentCreate(BaseModel):
    client_id: int
    name: str


class AgentOut(BaseModel):
    id: int
    client_id: int
    name: str
    api_token: str
    last_heartbeat: Optional[datetime] = None
    version: Optional[str] = None
    active: bool
    created_at: datetime
    hostname: Optional[str] = None
    remote_ip: Optional[str] = None
    pairing_code: Optional[str] = None
    pairing_expires_at: Optional[datetime] = None
    paired_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AgentPairingGenerateRequest(BaseModel):
    client_id: int
    name: Optional[str] = None
    ttl_minutes: int = 1440


class AgentPairingCodeOut(BaseModel):
    agent_id: int
    client_id: int
    name: str
    pairing_code: str
    pairing_expires_at: datetime
    server_url: Optional[str] = None

    model_config = {"from_attributes": True}


class AgentPairingRequest(BaseModel):
    pairing_code: str
    hostname: Optional[str] = None
    version: Optional[str] = None


class AgentPairingResponse(BaseModel):
    agent_token: str
    agent_id: int
    client_id: int
    client_name: str
    server_url: Optional[str] = None


class AgentClientCodeExchangeRequest(BaseModel):
    client_code: str
    hostname: Optional[str] = None
    version: Optional[str] = None


class AgentClientCodeExchangeResponse(BaseModel):
    agent_token: str
    agent_id: int
    client_id: int
    client_name: str
    client_code: str
    server_url: Optional[str] = None


class PrinterReading(BaseModel):
    ip_address: str
    mac_address: Optional[str] = None
    serial_number: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    status: str = "online"
    pages_total: int = 0
    pages_bw: int = 0
    pages_color: int = 0
    toner_black: Optional[float] = None
    toner_cyan: Optional[float] = None
    toner_magenta: Optional[float] = None
    toner_yellow: Optional[float] = None
    alerts: list[str] = Field(default_factory=list)

    @field_validator("ip_address", mode="before")
    @classmethod
    def _v_ip(cls, v: Any) -> str:
        return _clean_ip(v)

    @field_validator("mac_address", mode="before")
    @classmethod
    def _v_mac(cls, v: Any) -> Optional[str]:
        return _clean_mac(v)

    @field_validator("serial_number", mode="before")
    @classmethod
    def _v_serial(cls, v: Any) -> Optional[str]:
        return _clean_str(v, max_len=100)

    @field_validator("model", mode="before")
    @classmethod
    def _v_model(cls, v: Any) -> Optional[str]:
        return _clean_str(v, max_len=200)

    @field_validator("manufacturer", mode="before")
    @classmethod
    def _v_manufacturer(cls, v: Any) -> Optional[str]:
        return _clean_str(v, max_len=100)

    @field_validator("status", mode="before")
    @classmethod
    def _v_status(cls, v: Any) -> str:
        cleaned = _clean_str(v, max_len=50)
        return cleaned or "unknown"

    @field_validator("alerts", mode="before")
    @classmethod
    def _v_alerts(cls, v: Any) -> list[str]:
        if not isinstance(v, list):
            return []
        cleaned: list[str] = []
        for item in v:
            if item is None:
                continue
            s = _clean_str(item, max_len=200)
            if s:
                cleaned.append(s)
        return cleaned


class AgentReport(BaseModel):
    agent_version: Optional[str] = None
    readings: list[PrinterReading]

    @field_validator("agent_version", mode="before")
    @classmethod
    def _v_agent_version(cls, v: Any) -> Optional[str]:
        return _clean_str(v, max_len=50)


class DashboardStats(BaseModel):
    total_clients: int
    total_printers: int
    online_printers: int
    offline_printers: int
    active_alerts: int
    low_toner_count: int


class BrandingOut(BaseModel):
    display_name: str
    logo_src: Optional[str] = None
    tagline: str
    partner_id: Optional[int] = None
    partner_name: Optional[str] = None
    client_id: Optional[int] = None
    client_name: Optional[str] = None
    role_label: str


class UserBase(BaseModel):
    email: str


class UserCreate(UserBase):
    password: str
    role: str = "client_viewer"
    client_id: Optional[int] = None
    partner_id: Optional[int] = None
    username: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    client_id: Optional[int] = None
    partner_id: Optional[int] = None
    active: Optional[bool] = None


class UserOut(UserBase):
    id: int
    role: str
    client_id: Optional[int] = None
    partner_id: Optional[int] = None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangeOwnPasswordRequest(BaseModel):
    current_password: str
    new_password: str
