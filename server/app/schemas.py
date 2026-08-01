from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


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
    client_code: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PartnerBase(BaseModel):
    name: str
    logo_url: Optional[str] = None
    active: bool = True


class PartnerCreate(PartnerBase):
    pass


class PartnerUpdate(BaseModel):
    name: Optional[str] = None
    logo_url: Optional[str] = None
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


class AgentReport(BaseModel):
    agent_version: Optional[str] = None
    readings: list[PrinterReading]


class DashboardStats(BaseModel):
    total_clients: int
    total_printers: int
    online_printers: int
    offline_printers: int
    active_alerts: int
    low_toner_count: int


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
