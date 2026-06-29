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
    created_at: datetime

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


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
    username: str
    email: str


class UserCreate(UserBase):
    password: str


class UserOut(UserBase):
    id: int
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
