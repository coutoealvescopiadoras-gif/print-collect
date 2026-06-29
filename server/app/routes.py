import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Agent, Alert, Client, Location, Printer, Reading, User, get_db
from app.schemas import (
    AgentCreate,
    AgentOut,
    AgentReport,
    AlertOut,
    ClientCreate,
    ClientOut,
    ClientUpdate,
    DashboardStats,
    LocationCreate,
    LocationOut,
    PrinterCreate,
    PrinterOut,
    PrinterUpdate,
    Token,
    UserOut,
)

router = APIRouter(prefix="/api", tags=["api"])

# Configuracao JWT
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_user(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()


def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user(db, username=username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.active:
        raise HTTPException(status_code=400, detail="Usuário inativo")
    return current_user


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    printers = db.query(Printer).all()
    online = sum(1 for p in printers if p.status == "online")
    offline = sum(1 for p in printers if p.status == "offline")
    active_alerts = db.query(Alert).filter(Alert.resolved == False).count()
    low_toner = sum(
        1
        for p in printers
        if p.toner_black is not None and p.toner_black < 15
    )

    return DashboardStats(
        total_clients=db.query(Client).filter(Client.active == True).count(),
        total_printers=len(printers),
        online_printers=online,
        offline_printers=offline,
        active_alerts=active_alerts,
        low_toner_count=low_toner,
    )


@router.get("/clients", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return db.query(Client).order_by(Client.name).all()


@router.post("/clients", response_model=ClientOut, status_code=201)
def create_client(payload: ClientCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    client = Client(**payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("/clients/{client_id}", response_model=ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


@router.patch("/clients/{client_id}", response_model=ClientOut)
def update_client(client_id: int, payload: ClientUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, key, value)

    db.commit()
    db.refresh(client)
    return client


@router.get("/clients/{client_id}/locations", response_model=list[LocationOut])
def list_locations(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return db.query(Location).filter(Location.client_id == client_id).all()


@router.post("/locations", response_model=LocationOut, status_code=201)
def create_location(payload: LocationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    client = db.query(Client).filter(Client.id == payload.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    location = Location(**payload.model_dump())
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.get("/printers", response_model=list[PrinterOut])
def list_printers(client_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    query = db.query(Printer)
    if client_id:
        query = query.filter(Printer.client_id == client_id)
    return query.order_by(Printer.model).all()


@router.post("/printers", response_model=PrinterOut, status_code=201)
def create_printer(payload: PrinterCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    client = db.query(Client).filter(Client.id == payload.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    printer = Printer(**payload.model_dump())
    db.add(printer)
    db.commit()
    db.refresh(printer)
    return printer


@router.patch("/printers/{printer_id}", response_model=PrinterOut)
def update_printer(printer_id: int, payload: PrinterUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(printer, key, value)

    db.commit()
    db.refresh(printer)
    return printer


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(resolved: Optional[bool] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    query = db.query(Alert)
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)
    return query.order_by(Alert.created_at.desc()).limit(100).all()


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")

    alert.resolved = True
    alert.resolved_at = _now()
    db.commit()
    db.refresh(alert)
    return alert


@router.get("/agents", response_model=list[AgentOut])
def list_agents(client_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    query = db.query(Agent)
    if client_id:
        query = query.filter(Agent.client_id == client_id)
    return query.all()


@router.post("/agents", response_model=AgentOut, status_code=201)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    client = db.query(Client).filter(Client.id == payload.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    agent = Agent(
        client_id=payload.client_id,
        name=payload.name,
        api_token=secrets.token_urlsafe(32),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def _get_agent(x_agent_token: str, db: Session) -> Agent:
    agent = db.query(Agent).filter(Agent.api_token == x_agent_token, Agent.active == True).first()
    if not agent:
        raise HTTPException(status_code=401, detail="Token de agente inválido")
    return agent


def _sync_alerts(db: Session, printer: Printer, alert_messages: list[str]) -> None:
    existing = {
        a.message: a
        for a in db.query(Alert).filter(Alert.printer_id == printer.id, Alert.resolved == False).all()
    }

    for message in alert_messages:
        if message not in existing:
            severity = "critical" if "vazio" in message.lower() or "empty" in message.lower() else "warning"
            db.add(
                Alert(
                    printer_id=printer.id,
                    alert_type="supply" if "toner" in message.lower() else "device",
                    message=message,
                    severity=severity,
                )
            )


@router.post("/agent/report")
def agent_report(
    payload: AgentReport,
    x_agent_token: str = Header(...),
    db: Session = Depends(get_db),
):
    agent = _get_agent(x_agent_token, db)
    agent.last_heartbeat = _now()
    agent.version = payload.agent_version
    now = _now()

    for reading in payload.readings:
        printer = (
            db.query(Printer)
            .filter(
                Printer.client_id == agent.client_id,
                Printer.ip_address == reading.ip_address,
            )
            .first()
        )

        if not printer and reading.serial_number:
            printer = (
                db.query(Printer)
                .filter(
                    Printer.client_id == agent.client_id,
                    Printer.serial_number == reading.serial_number,
                )
                .first()
            )

        if not printer:
            printer = Printer(
                client_id=agent.client_id,
                ip_address=reading.ip_address,
            )
            db.add(printer)

        printer.mac_address = reading.mac_address or printer.mac_address
        printer.serial_number = reading.serial_number or printer.serial_number
        printer.model = reading.model or printer.model
        printer.manufacturer = reading.manufacturer or printer.manufacturer
        printer.status = reading.status
        printer.pages_total = reading.pages_total
        printer.pages_bw = reading.pages_bw
        printer.pages_color = reading.pages_color
        printer.toner_black = reading.toner_black
        printer.toner_cyan = reading.toner_cyan
        printer.toner_magenta = reading.toner_magenta
        printer.toner_yellow = reading.toner_yellow
        printer.last_seen = now
        printer.updated_at = now

        db.flush()

        db.add(
            Reading(
                printer_id=printer.id,
                pages_total=reading.pages_total,
                pages_bw=reading.pages_bw,
                pages_color=reading.pages_color,
                toner_black=reading.toner_black,
                toner_cyan=reading.toner_cyan,
                toner_magenta=reading.toner_magenta,
                toner_yellow=reading.toner_yellow,
                status=reading.status,
                collected_at=now,
            )
        )

        _sync_alerts(db, printer, reading.alerts)

    db.commit()
    return {"status": "ok", "readings_received": len(payload.readings)}


@router.post("/agent/heartbeat")
def agent_heartbeat(
    x_agent_token: str = Header(...),
    db: Session = Depends(get_db),
):
    agent = _get_agent(x_agent_token, db)
    agent.last_heartbeat = _now()
    db.commit()
    return {"status": "ok"}
