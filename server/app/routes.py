import secrets
import asyncio
import io
import os
import zipfile
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
import bcrypt
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Agent, Alert, Client, Location, Partner, Printer, Reading, User, get_db
# # # from app.email import send_alert_email (temporarily disabled)
from app.schemas import (
    AgentCreate,
    AgentOut,
    AgentPairingGenerateRequest,
    AgentPairingCodeOut,
    AgentPairingRequest,
    AgentPairingResponse,
    AgentClientCodeExchangeRequest,
    AgentClientCodeExchangeResponse,
    AgentReport,
    AlertOut,
    PartnerBillingStats,
    ClientCreate,
    ClientOut,
    ClientUpdate,
    ChangeOwnPasswordRequest,
    DashboardStats,
    LocationCreate,
    LocationOut,
    PartnerCreate,
    PartnerOut,
    PartnerUpdate,
    PrinterCreate,
    PrinterOut,
    PrinterUpdate,
    Token,
    UserCreate,
    UserOut,
    UserUpdate,
)

router = APIRouter(prefix="/api", tags=["api"])

# Configuracao JWT
# (usando bcrypt diretamente em vez de passlib para compatibilidade com bcrypt 5.x)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 43200
ROLE_SUPERADMIN = "superadmin"
ROLE_PARTNER_ADMIN = "partner_admin"
ROLE_CLIENT_MANAGER = "client_manager"
ROLE_CLIENT_VIEWER = "client_viewer"
MANAGE_ROLES = {ROLE_SUPERADMIN, ROLE_PARTNER_ADMIN, ROLE_CLIENT_MANAGER}
VALID_ROLES = {ROLE_SUPERADMIN, ROLE_PARTNER_ADMIN, ROLE_CLIENT_MANAGER, ROLE_CLIENT_VIEWER}


# #region debug-point A:agent-package-report
def _report_agent_package_debug(hypothesis_id: str, location: str, msg: str, data: Optional[dict] = None) -> None:
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                "http://127.0.0.1:7777/event",
                data=json.dumps({
                    "sessionId": "agent-install-yaml",
                    "runId": "pre-fix",
                    "hypothesisId": hypothesis_id,
                    "location": location,
                    "msg": f"[DEBUG] {msg}",
                    "data": data or {},
                }).encode(),
                headers={"Content-Type": "application/json"},
            ),
            timeout=0.5,
        ).read()
    except Exception:
        pass
# #endregion


def _resolve_windows_setup_path(project_root: str) -> str:
    configured_path = os.getenv("PRINT_COLLECT_WINDOWS_SETUP_PATH", "").strip()
    candidates = []
    if configured_path:
        candidates.append(configured_path)
    candidates.append(os.path.join(project_root, "agent", "dist", "windows", "PrintCollectSetup.exe"))

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate

    return configured_path


def _guess_logo_extension(logo_url: str, content_type: Optional[str]) -> str:
    lowered_url = logo_url.lower().split("?", 1)[0]
    lowered_type = (content_type or "").lower()

    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"):
        if lowered_url.endswith(ext):
            return ext

    if "svg" in lowered_type:
        return ".svg"
    if "webp" in lowered_type:
        return ".webp"
    if "gif" in lowered_type:
        return ".gif"
    if "jpeg" in lowered_type or "jpg" in lowered_type:
        return ".jpg"
    return ".png"


def _download_partner_logo(logo_url: str) -> Optional[Tuple[str, bytes]]:
    if not logo_url or not logo_url.startswith(("http://", "https://")):
        return None

    try:
        with urllib.request.urlopen(logo_url, timeout=5) as response:
            content_type = response.headers.get("Content-Type")
            data = response.read(2 * 1024 * 1024 + 1)
        if not data or len(data) > 2 * 1024 * 1024:
            return None
        extension = _guess_logo_extension(logo_url, content_type)
        return (f"logo-revendedor{extension}", data)
    except Exception:
        return None


def verify_password(plain_password, hashed_password):
    try:
        if isinstance(hashed_password, str):
            hashed = hashed_password.encode("utf-8")
        else:
            hashed = hashed_password
        if isinstance(plain_password, str):
            plain = plain_password.encode("utf-8")[:72]
        else:
            plain = plain_password[:72]
        return bcrypt.checkpw(plain, hashed)
    except Exception:
        return False


def hash_password(plain_password) -> str:
    if isinstance(plain_password, str):
        plain = plain_password.encode("utf-8")[:72]
    else:
        plain = plain_password[:72]
    return bcrypt.hashpw(plain, bcrypt.gensalt()).decode("utf-8")


def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()


def authenticate_user(db: Session, email: str, password: str):
    user = get_user_by_email(db, email.strip().lower())
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
        expire = datetime.now(timezone.utc) + timedelta(days=30)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def _user_role(user: User) -> str:
    return user.role or ROLE_SUPERADMIN


def _is_superadmin(user: User) -> bool:
    return _user_role(user) == ROLE_SUPERADMIN


def _is_partner_admin(user: User) -> bool:
    return _user_role(user) == ROLE_PARTNER_ADMIN


def _can_manage_resources(user: User) -> bool:
    return _user_role(user) in MANAGE_ROLES


def _can_create_clients(user: User) -> bool:
    return _is_superadmin(user) or _is_partner_admin(user)


def _required_client_id(user: User) -> int:
    if user.client_id is None:
        raise HTTPException(status_code=403, detail="Usuário sem cliente vinculado")
    return user.client_id


def _required_partner_id(user: User) -> int:
    if user.partner_id is None:
        raise HTTPException(status_code=403, detail="Usuário sem revendedor vinculado")
    return user.partner_id


def _scoped_client_id(current_user: User, requested_client_id: Optional[int] = None) -> Optional[int]:
    if _is_superadmin(current_user):
        return requested_client_id

    if _is_partner_admin(current_user):
        return requested_client_id

    client_id = _required_client_id(current_user)
    if requested_client_id is not None and requested_client_id != client_id:
        raise HTTPException(status_code=403, detail="Acesso negado a este cliente")
    return client_id


def _assert_partner_owns_client(db: Session, current_user: User, client_id: int) -> None:
    if not _is_partner_admin(current_user):
        return
    partner_id = _required_partner_id(current_user)
    exists = (
        db.query(Client.id)
        .filter(Client.id == client_id, Client.partner_id == partner_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=403, detail="Acesso negado a este cliente")


def _require_manage_scope(current_user: User, client_id: Optional[int] = None) -> Optional[int]:
    if not _can_manage_resources(current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para executar esta ação")
    return _scoped_client_id(current_user, client_id)


def _get_scoped_client(db: Session, current_user: User, client_id: int) -> Client:
    scoped_client_id = _scoped_client_id(current_user, client_id)
    query = db.query(Client).filter(Client.id == client_id)
    if scoped_client_id is not None:
        query = query.filter(Client.id == scoped_client_id)
    if _is_partner_admin(current_user):
        query = query.filter(Client.partner_id == _required_partner_id(current_user))
    client = query.first()
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return client


def _get_scoped_printer(db: Session, current_user: User, printer_id: int) -> Printer:
    query = db.query(Printer).filter(Printer.id == printer_id)
    if _is_partner_admin(current_user):
        query = query.join(Client).filter(Client.partner_id == _required_partner_id(current_user))
    elif not _is_superadmin(current_user):
        query = query.filter(Printer.client_id == _required_client_id(current_user))
    printer = query.first()
    if not printer:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")
    return printer


def _get_scoped_agent(db: Session, current_user: User, agent_id: int) -> Agent:
    query = db.query(Agent).filter(Agent.id == agent_id)
    if _is_partner_admin(current_user):
        query = query.join(Client).filter(Client.partner_id == _required_partner_id(current_user))
    elif not _is_superadmin(current_user):
        query = query.filter(Agent.client_id == _required_client_id(current_user))
    agent = query.first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agente não encontrado")
    return agent


def _get_scoped_alert(db: Session, current_user: User, alert_id: int) -> Alert:
    query = db.query(Alert).join(Printer).filter(Alert.id == alert_id)
    if _is_partner_admin(current_user):
        query = query.join(Client, Client.id == Printer.client_id).filter(Client.partner_id == _required_partner_id(current_user))
    elif not _is_superadmin(current_user):
        query = query.filter(Printer.client_id == _required_client_id(current_user))
    alert = query.first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return alert


async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if not current_user.active:
        raise HTTPException(status_code=400, detail="Usuário inativo")
    return current_user


def _now() -> datetime:
    return datetime.utcnow()


def _is_expired(dt: datetime | None) -> bool:
    if dt is None:
        return False
    val = dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
    return val < _now()


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    login_email = (form_data.username or "").strip().lower()
    user = authenticate_user(db, login_email, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=UserOut)
async def read_users_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.post("/users/me/change-password")
def change_own_password(
    payload: ChangeOwnPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="A nova senha deve ter pelo menos 6 caracteres")

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"status": "ok"}


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    if not _can_manage_resources(current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para listar usuários")

    query = db.query(User)
    if _is_partner_admin(current_user):
        query = query.filter(User.partner_id == _required_partner_id(current_user))
    elif not _is_superadmin(current_user):
        query = query.filter(User.client_id == _required_client_id(current_user))
    return query.order_by(User.username).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    if not _can_manage_resources(current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para criar usuários")

    role = (payload.role or ROLE_CLIENT_VIEWER).strip().lower()
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Perfil de usuário inválido")

    normalized_email = payload.email.strip().lower()
    login_name = (payload.username or normalized_email).strip().lower()

    if db.query(User).filter(User.email == normalized_email).first():
        raise HTTPException(status_code=400, detail="E-mail já cadastrado")
    if db.query(User).filter(User.username == login_name).first():
        raise HTTPException(status_code=400, detail="Login já cadastrado")

    client_id = payload.client_id
    partner_id: Optional[int] = payload.partner_id

    if _is_superadmin(current_user):
        if role == ROLE_SUPERADMIN:
            client_id = None
            partner_id = None
        elif role == ROLE_PARTNER_ADMIN:
            if partner_id is None:
                raise HTTPException(status_code=400, detail="partner_id é obrigatório para usuários revendedores")
            client_id = None
        else:
            if client_id is None:
                raise HTTPException(status_code=400, detail="client_id é obrigatório para usuários de cliente")
            client = db.query(Client).filter(Client.id == client_id).first()
            if not client:
                raise HTTPException(status_code=404, detail="Cliente não encontrado")
            partner_id = client.partner_id
    elif _is_partner_admin(current_user):
        if role == ROLE_SUPERADMIN:
            raise HTTPException(status_code=403, detail="Revendedor não pode criar superadmin")
        partner_id = _required_partner_id(current_user)
        if role == ROLE_PARTNER_ADMIN:
            client_id = None
        else:
            if client_id is None:
                raise HTTPException(status_code=400, detail="client_id é obrigatório para usuários de cliente")
            _assert_partner_owns_client(db, current_user, client_id)
    else:
        if role in {ROLE_SUPERADMIN, ROLE_PARTNER_ADMIN}:
            raise HTTPException(status_code=403, detail="Cliente não pode criar superadmin/revendedor")
        client_id = _required_client_id(current_user)
        client = db.query(Client).filter(Client.id == client_id).first()
        partner_id = client.partner_id if client else None

    user = User(
        username=login_name,
        email=normalized_email,
        hashed_password=hash_password(payload.password),
        role=role,
        client_id=client_id,
        partner_id=partner_id,
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _can_manage_resources(current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para editar usuários")

    query = db.query(User).filter(User.id == user_id)
    if _is_partner_admin(current_user):
        query = query.filter(User.partner_id == _required_partner_id(current_user))
    elif not _is_superadmin(current_user):
        query = query.filter(User.client_id == _required_client_id(current_user))
    user = query.first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    updates = payload.model_dump(exclude_unset=True)
    if "role" in updates:
        updates["role"] = str(updates["role"]).strip().lower()
        if updates["role"] not in VALID_ROLES:
            raise HTTPException(status_code=400, detail="Perfil de usuário inválido")
        if not _is_superadmin(current_user) and updates["role"] == ROLE_SUPERADMIN:
            raise HTTPException(status_code=403, detail="Cliente não pode promover para superadmin")
        if not _is_superadmin(current_user) and updates["role"] == ROLE_PARTNER_ADMIN:
            raise HTTPException(status_code=403, detail="Apenas superadmin pode promover para revendedor")

    if "client_id" in updates:
        if _is_superadmin(current_user):
            if updates.get("role", user.role) == ROLE_SUPERADMIN:
                updates["client_id"] = None
                updates["partner_id"] = None
            elif updates.get("role", user.role) == ROLE_PARTNER_ADMIN:
                updates["client_id"] = None
            elif updates["client_id"] is not None:
                client = db.query(Client).filter(Client.id == updates["client_id"]).first()
                if not client:
                    raise HTTPException(status_code=404, detail="Cliente não encontrado")
                updates["partner_id"] = client.partner_id
        elif _is_partner_admin(current_user):
            if updates["client_id"] is None:
                raise HTTPException(status_code=400, detail="client_id é obrigatório para usuários de cliente")
            _assert_partner_owns_client(db, current_user, updates["client_id"])
            updates["partner_id"] = _required_partner_id(current_user)
        else:
            updates["client_id"] = _required_client_id(current_user)
            client = db.query(Client).filter(Client.id == updates["client_id"]).first()
            updates["partner_id"] = client.partner_id if client else None

    if "partner_id" in updates:
        if _is_superadmin(current_user):
            if updates.get("role", user.role) == ROLE_SUPERADMIN:
                updates["partner_id"] = None
        elif _is_partner_admin(current_user):
            updates["partner_id"] = _required_partner_id(current_user)
        else:
            updates.pop("partner_id", None)

    if "password" in updates:
        if not _is_superadmin(current_user):
            raise HTTPException(status_code=403, detail="Somente superadmin pode redefinir a senha de outro usuário")
        user.hashed_password = hash_password(str(updates.pop("password")))

    if "email" in updates:
        normalized_email = str(updates["email"]).strip().lower()
        existing_user = db.query(User).filter(User.email == normalized_email, User.id != user.id).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="E-mail já cadastrado")
        updates["email"] = normalized_email
        updates["username"] = normalized_email

    for key, value in updates.items():
        setattr(user, key, value)

    if user.role in {ROLE_CLIENT_MANAGER, ROLE_CLIENT_VIEWER} and user.client_id is None:
        raise HTTPException(status_code=400, detail="Usuários de cliente precisam de client_id")
    if user.role == ROLE_PARTNER_ADMIN and user.partner_id is None:
        raise HTTPException(status_code=400, detail="Usuários revendedores precisam de partner_id")

    db.commit()
    db.refresh(user)
    return user


@router.get("/partners", response_model=list[PartnerOut])
def list_partners(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    if not _is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Somente superadmin pode listar revendedores")
    return db.query(Partner).order_by(Partner.name).all()


@router.post("/partners", response_model=PartnerOut, status_code=201)
def create_partner(payload: PartnerCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    if not _is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Somente superadmin pode criar revendedores")
    partner = Partner(**payload.model_dump())
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner


@router.patch("/partners/{partner_id}", response_model=PartnerOut)
def update_partner(
    partner_id: int,
    payload: PartnerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Somente superadmin pode editar revendedores")
    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Revendedor não encontrado")

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(partner, key, value)

    db.commit()
    db.refresh(partner)
    return partner


@router.get("/partners/stats", response_model=list[PartnerBillingStats])
def list_partner_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    if not _is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Somente superadmin pode ver a contagem comercial por revendedor")

    partners = db.query(Partner).order_by(Partner.name).all()
    billing_cutoff = _now() - timedelta(days=30)
    stats: list[PartnerBillingStats] = []

    for partner in partners:
        clients = db.query(Client).filter(Client.partner_id == partner.id).all()
        client_ids = [client.id for client in clients]

        printers: list[Printer] = []
        if client_ids:
            printers = db.query(Printer).filter(Printer.client_id.in_(client_ids)).all()

        stats.append(
            PartnerBillingStats(
                partner_id=partner.id,
                partner_name=partner.name,
                total_clients=len(clients),
                total_printers=len(printers),
                billable_printers=sum(
                    1 for printer in printers if printer.last_seen and printer.last_seen >= billing_cutoff
                ),
                online_printers=sum(1 for printer in printers if printer.status == "online"),
                offline_printers=sum(1 for printer in printers if printer.status == "offline"),
            )
        )

    return stats


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    printers_query = db.query(Printer)
    alerts_query = db.query(Alert).join(Printer)
    clients_query = db.query(Client).filter(Client.active == True)

    if _is_partner_admin(current_user):
        partner_id = _required_partner_id(current_user)
        printers_query = printers_query.join(Client).filter(Client.partner_id == partner_id)
        alerts_query = alerts_query.join(Client, Client.id == Printer.client_id).filter(Client.partner_id == partner_id)
        clients_query = clients_query.filter(Client.partner_id == partner_id)
    elif not _is_superadmin(current_user):
        client_id = _required_client_id(current_user)
        printers_query = printers_query.filter(Printer.client_id == client_id)
        alerts_query = alerts_query.filter(Printer.client_id == client_id)
        clients_query = clients_query.filter(Client.id == client_id)

    printers = printers_query.all()
    online = sum(1 for p in printers if p.status == "online")
    offline = sum(1 for p in printers if p.status == "offline")
    active_alerts = alerts_query.filter(Alert.resolved == False).count()
    low_toner = sum(
        1
        for p in printers
        if p.toner_black is not None and p.toner_black < 15
    )

    return DashboardStats(
        total_clients=clients_query.count(),
        total_printers=len(printers),
        online_printers=online,
        offline_printers=offline,
        active_alerts=active_alerts,
        low_toner_count=low_toner,
    )


@router.get("/clients", response_model=list[ClientOut])
def list_clients(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    query = db.query(Client)
    if _is_partner_admin(current_user):
        query = query.filter(Client.partner_id == _required_partner_id(current_user))
    elif not _is_superadmin(current_user):
        query = query.filter(Client.id == _required_client_id(current_user))
    clients = query.order_by(Client.name).all()
    _ensure_client_codes_for_all(db)
    return clients


@router.post("/clients", response_model=ClientOut, status_code=201)
def create_client(payload: ClientCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    if not _can_create_clients(current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para criar clientes")
    data = payload.model_dump()
    if _is_partner_admin(current_user):
        data["partner_id"] = _required_partner_id(current_user)
    data["client_code"] = _generate_client_code(db)
    client = Client(**data)
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("/clients/{client_id}", response_model=ClientOut)
def get_client(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    return _get_scoped_client(db, current_user, client_id)


@router.patch("/clients/{client_id}", response_model=ClientOut)
def update_client(client_id: int, payload: ClientUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _require_manage_scope(current_user, client_id)
    client = _get_scoped_client(db, current_user, client_id)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, key, value)

    db.commit()
    db.refresh(client)
    return client


@router.delete("/clients/{client_id}")
def delete_client(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    if not _can_create_clients(current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para excluir clientes")
    client = _get_scoped_client(db, current_user, client_id)
    db.delete(client)
    db.commit()
    return {"status": "ok"}


@router.get("/clients/{client_id}/locations", response_model=list[LocationOut])
def list_locations(client_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    scoped_client_id = _scoped_client_id(current_user, client_id)
    if _is_partner_admin(current_user):
        _assert_partner_owns_client(db, current_user, client_id)
    query = db.query(Location).filter(Location.client_id == client_id)
    if scoped_client_id is not None:
        query = query.filter(Location.client_id == scoped_client_id)
    return query.all()


@router.post("/locations", response_model=LocationOut, status_code=201)
def create_location(payload: LocationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _require_manage_scope(current_user, payload.client_id)
    client = _get_scoped_client(db, current_user, payload.client_id)

    location = Location(**payload.model_dump())
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


@router.get("/printers", response_model=list[PrinterOut])
def list_printers(client_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    scoped_client_id = _scoped_client_id(current_user, client_id)
    query = db.query(Printer)
    if _is_partner_admin(current_user):
        partner_id = _required_partner_id(current_user)
        query = query.join(Client).filter(Client.partner_id == partner_id)
        if client_id is not None:
            _assert_partner_owns_client(db, current_user, client_id)
    if scoped_client_id is not None:
        query = query.filter(Printer.client_id == scoped_client_id)
    return query.order_by(Printer.model).all()


@router.post("/printers", response_model=PrinterOut, status_code=201)
def create_printer(payload: PrinterCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _require_manage_scope(current_user, payload.client_id)
    client = _get_scoped_client(db, current_user, payload.client_id)

    printer = Printer(**payload.model_dump())
    db.add(printer)
    db.commit()
    db.refresh(printer)
    return printer


@router.patch("/printers/{printer_id}", response_model=PrinterOut)
def update_printer(printer_id: int, payload: PrinterUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    printer = _get_scoped_printer(db, current_user, printer_id)
    _require_manage_scope(current_user, printer.client_id)

    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(printer, key, value)

    db.commit()
    db.refresh(printer)
    return printer


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(resolved: Optional[bool] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    query = db.query(Alert).join(Printer)
    if _is_partner_admin(current_user):
        query = query.join(Client, Client.id == Printer.client_id).filter(Client.partner_id == _required_partner_id(current_user))
    elif not _is_superadmin(current_user):
        query = query.filter(Printer.client_id == _required_client_id(current_user))
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)
    return query.order_by(Alert.created_at.desc()).limit(100).all()


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(alert_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    alert = _get_scoped_alert(db, current_user, alert_id)
    _require_manage_scope(current_user, alert.printer.client_id)

    alert.resolved = True
    alert.resolved_at = _now()
    db.commit()
    db.refresh(alert)
    return alert


@router.get("/agents", response_model=list[AgentOut])
def list_agents(client_id: Optional[int] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    scoped_client_id = _scoped_client_id(current_user, client_id)
    query = db.query(Agent)
    if _is_partner_admin(current_user):
        partner_id = _required_partner_id(current_user)
        query = query.join(Client).filter(Client.partner_id == partner_id)
        if client_id is not None:
            _assert_partner_owns_client(db, current_user, client_id)
    if scoped_client_id is not None:
        query = query.filter(Agent.client_id == scoped_client_id)
    return query.all()


@router.post("/agents", response_model=AgentOut, status_code=201)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _require_manage_scope(current_user, payload.client_id)
    client = _get_scoped_client(db, current_user, payload.client_id)

    agent = Agent(
        client_id=payload.client_id,
        name=payload.name,
        api_token=secrets.token_urlsafe(32),
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def _generate_pairing_code(db: Session, length: int = 8) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(10):
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        existing = db.query(Agent).filter(Agent.pairing_code == code).first()
        if not existing:
            return code
    raise HTTPException(status_code=500, detail="Nao foi possivel gerar um codigo de pareamento unico.")


def _generate_client_code(db: Session, length: int = 8) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(30):
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        existing = db.query(Client).filter(Client.client_code == code).first()
        if not existing:
            return code
    raise HTTPException(status_code=500, detail="Nao foi possivel gerar um codigo unico de cliente.")


def _ensure_client_codes_for_all(db: Session) -> None:
    """Preenche client_code nulo para clientes ja existentes no banco."""
    try:
        missing = db.query(Client).filter(Client.client_code.is_(None)).all()
        for c in missing:
            if not c.client_code:
                c.client_code = _generate_client_code(db)
        db.commit()
    except Exception:
        db.rollback()
        pass


@router.post("/agents/pairing/generate", response_model=AgentPairingCodeOut)
def generate_pairing_code(
    payload: AgentPairingGenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Gera um codigo de pareamento curto (ex: 8 digitos) que o cliente pode digitar no agente.
    O agente ainda e criado PENDENTE (sem pareamento executado) e expira em ttl_minutes."""
    _require_manage_scope(current_user, payload.client_id)
    client = _get_scoped_client(db, current_user, payload.client_id)

    # Garante TTL razoavel (1 minuto minimo, 30 dias maximo)
    ttl = max(1, min(payload.ttl_minutes, 60 * 24 * 30))
    expires_at = _now() + timedelta(minutes=ttl)

    name = (payload.name or f"Agente {client.name}").strip()[:180]
    if not name:
        name = f"Agente cliente {client.id}"

    agent = Agent(
        client_id=payload.client_id,
        name=name,
        api_token=secrets.token_urlsafe(32),
        pairing_code=_generate_pairing_code(db),
        pairing_expires_at=expires_at,
        active=False,  # so ativa apos pareamento
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    return AgentPairingCodeOut(
        agent_id=agent.id,
        client_id=agent.client_id,
        name=agent.name,
        pairing_code=agent.pairing_code or "",
        pairing_expires_at=agent.pairing_expires_at or _now(),
        server_url=str(request.base_url).rstrip("/"),
    )


@router.post("/agents/pairing/exchange", response_model=AgentPairingResponse)
def exchange_pairing_code(
    payload: AgentPairingRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Endpoint PUBLICO (sem login). O agente instalado na rede do cliente envia o
    codigo de pareamento e recebe de volta o api_token e informacoes do cliente.
    Nao pode ser chamado por usuario web — apenas pelo agente."""
    code = (payload.pairing_code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Codigo de pareamento invalido")

    agent = db.query(Agent).filter(Agent.pairing_code == code).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Codigo de pareamento nao encontrado")

    if agent.paired_at is not None:
        raise HTTPException(status_code=409, detail="Este codigo ja foi utilizado")

    if _is_expired(agent.pairing_expires_at):
        raise HTTPException(status_code=410, detail="Codigo de pareamento expirado")

    # Finaliza pareamento
    agent.active = True
    agent.paired_at = _now()
    agent.hostname = (payload.hostname or "")[:200] or None
    agent.version = (payload.version or "")[:50] or agent.version
    # Remote IP
    try:
        if hasattr(request, "client") and request.client:
            agent.remote_ip = str(request.client.host)[:45]
    except Exception:
        pass

    db.commit()
    db.refresh(agent)

    client = db.query(Client).filter(Client.id == agent.client_id).first()
    client_name = client.name if client else f"Cliente #{agent.client_id}"

    return AgentPairingResponse(
        agent_token=agent.api_token,
        agent_id=agent.id,
        client_id=agent.client_id,
        client_name=client_name,
        server_url=str(request.base_url).rstrip("/"),
    )


@router.post("/agents/client-code/exchange", response_model=AgentClientCodeExchangeResponse)
def exchange_client_code(
    payload: AgentClientCodeExchangeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Endpoint PUBLICO (sem login). O agente instalado na rede do cliente envia o
    CODIGO DO CLIENTE (8 digitos, fixo, nao expira) e recebe um agent_token novo ou
    existente. Esse endpoint pode ser chamado multiplas vezes (reinstalações,
    filiais diferentes etc.) — sempre retorna um agent_token válido para o cliente.
    Nao pode ser chamado por usuario web — apenas pelo agente."""
    code = (payload.client_code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Codigo do cliente invalido")

    # Garante que clientes existentes tenham codigo
    _ensure_client_codes_for_all(db)

    client = db.query(Client).filter(Client.client_code == code).first()
    if not client:
        raise HTTPException(status_code=404, detail="Codigo do cliente nao encontrado")
    if not client.active:
        raise HTTPException(status_code=410, detail="Cliente esta inativo")

    # Tenta encontrar um agente existente ativo para este cliente+hostname, se existir reutiliza
    hostname = (payload.hostname or "")[:200] or None
    version = (payload.version or "")[:50] or None
    remote_ip = None
    try:
        if hasattr(request, "client") and request.client:
            remote_ip = str(request.client.host)[:45]
    except Exception:
        remote_ip = None

    existing = None
    if hostname:
        existing = (
            db.query(Agent)
            .filter(Agent.client_id == client.id, Agent.hostname == hostname)
            .order_by(Agent.id.desc())
            .first()
        )
    if existing is None:
        # Cria um agente NOVO para este cliente (suporta multiplas filiais / maquinas)
        sanitized_hostname = hostname[:150] if hostname else ""
        agent_name = f"Agente {client.name}" + (f" ({sanitized_hostname})" if sanitized_hostname else "")
        new_agent = Agent(
            client_id=client.id,
            name=agent_name[:200] or f"Agente cliente {client.id}",
            api_token=secrets.token_urlsafe(32),
            active=True,
            hostname=hostname,
            remote_ip=remote_ip,
            paired_at=_now(),
            version=version,
        )
        db.add(new_agent)
        db.commit()
        db.refresh(new_agent)
        agent = new_agent
    else:
        # Reutiliza — atualiza heartbeat e versao
        existing.active = True
        existing.paired_at = _now()
        existing.hostname = hostname
        existing.version = version or existing.version
        if remote_ip:
            existing.remote_ip = remote_ip
        db.commit()
        db.refresh(existing)
        agent = existing

    return AgentClientCodeExchangeResponse(
        agent_token=agent.api_token,
        agent_id=agent.id,
        client_id=client.id,
        client_name=client.name,
        client_code=code,
        server_url=str(request.base_url).rstrip("/"),
    )


@router.delete("/agents/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    agent = _get_scoped_agent(db, current_user, agent_id)
    _require_manage_scope(current_user, agent.client_id)
    db.delete(agent)
    db.commit()
    return {"status": "ok"}


@router.get("/agents/{agent_id}/windows-package")
def download_agent_windows_package(
    agent_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    agent = _get_scoped_agent(db, current_user, agent_id)
    _require_manage_scope(current_user, agent.client_id)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    agent_root = os.path.join(project_root, "agent")
    client = db.query(Client).filter(Client.id == agent.client_id).first()
    partner = db.query(Partner).filter(Partner.id == client.partner_id).first() if client and client.partner_id else None

    server_url = str(request.base_url).rstrip("/")
    agent_version = os.getenv("PRINT_COLLECT_AGENT_VERSION", "0.2.0")

    config_yaml = "\n".join(
        [
            'server_url: "%s"' % server_url,
            'agent_token: "%s"' % agent.api_token,
            'agent_version: "%s"' % agent_version,
            "interval_minutes: 15",
            "snmp:",
            '  community: "public"',
            "  timeout: 2",
            "  subnets: []",
            "  ips: []",
            "",
        ]
    ).encode("utf-8")

    installer_path = _resolve_windows_setup_path(project_root)
    included_files = ["config.yaml"]
    installer_exists = bool(installer_path and os.path.isfile(installer_path))
    if installer_exists:
        included_files.append("PrintCollectSetup.exe")
    else:
        included_files.extend(
            [
                "install.ps1",
                "pyproject.toml",
                "requirements.txt",
                "print_collect/",
            ]
        )

    # #region debug-point A:agent-package-contents
    _report_agent_package_debug("A", "routes.py:download_agent_windows_package", "building windows package", {
        "agent_id": agent_id,
        "installer_path": installer_path,
        "installer_exists": installer_exists,
        "included_files": included_files,
        "server_url": server_url,
        "agent_root_exists": os.path.isdir(agent_root),
    })
    # #endregion

    readme_lines = [
        "Print Collect Agent - Pacote Windows",
        "",
        "Este pacote inclui o config.yaml ja preenchido com a URL da API e o token do agente.",
        "",
    ]
    if partner:
        readme_lines.extend(
            [
                f"Revendedor responsavel: {partner.name}",
                "O nome do programa continua Print Collect Agent, mas o pacote pode levar a identidade visual do revendedor.",
                "",
            ]
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.yaml", config_yaml)
        downloaded_logo_name: Optional[str] = None
        if partner:
            if partner.logo_url:
                downloaded_logo = _download_partner_logo(partner.logo_url)
                if downloaded_logo:
                    logo_filename, logo_bytes = downloaded_logo
                    downloaded_logo_name = logo_filename
                    zf.writestr(logo_filename, logo_bytes)
            branding_ini = "\n".join(
                [
                    "[partner]",
                    f"name={partner.name}",
                    f"logo_url={partner.logo_url or ''}",
                    f"logo_file={downloaded_logo_name or ''}",
                    "",
                ]
            )
            zf.writestr("branding.ini", branding_ini.encode("utf-8"))
        if installer_exists:
            zf.write(installer_path, arcname="PrintCollectSetup.exe")
            installer_files = [
                "Arquivos:",
                "- config.yaml",
                "- PrintCollectSetup.exe",
            ]
            if partner:
                installer_files.append("- branding.ini")
            readme_lines.extend(
                installer_files
                + [
                    "",
                    "Como instalar:",
                    "1. Extraia todo o ZIP em uma pasta.",
                    "2. Clique duas vezes em PrintCollectSetup.exe.",
                    "3. Clique em Proximo ate concluir.",
                    "4. O instalador copia o config.yaml ja preenchido com a URL da API e o token do agente.",
                    "5. O agente inicia automaticamente e tenta descobrir a sub-rede local quando nenhuma rede for informada.",
                    "6. So edite C:\\Program Files\\PrintCollect\\config.yaml se quiser forcar IPs, sub-redes ou community SNMP.",
                    "7. Opcional: para personalizar a instalacao, coloque branding.ini e/ou logo-revendedor.bmp na mesma pasta do PrintCollectSetup.exe antes de enviar ao cliente.",
                    "",
                    "Observacao: o instalador cria inicializacao automatica no Windows e inicia o agente ao concluir.",
                    "Se houver branding.ini no ZIP, o instalador mostra o nome do revendedor.",
                    "Se existir logo-revendedor.bmp ao lado do instalador, a janela do setup tambem exibe a marca sem alterar o nome do programa.",
                    "",
                ]
            )
        else:
            for relative_path in ["install.ps1", "pyproject.toml", "requirements.txt"]:
                source_path = os.path.join(agent_root, relative_path)
                if os.path.isfile(source_path):
                    zf.write(source_path, arcname=relative_path)

            fallback_launcher = "\r\n".join(
                [
                    "@echo off",
                    "setlocal",
                    'cd /d "%~dp0"',
                    'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"',
                    "",
                    "pause",
                ]
            ).encode("utf-8")
            zf.writestr("1-CLIQUE-AQUI-PARA-INSTALAR.bat", fallback_launcher)

            package_root = os.path.join(agent_root, "print_collect")
            if os.path.isdir(package_root):
                for current_root, _, files in os.walk(package_root):
                    for file_name in files:
                        source_path = os.path.join(current_root, file_name)
                        arcname = os.path.relpath(source_path, agent_root)
                        zf.write(source_path, arcname=arcname)

            fallback_files = [
                "Arquivos:",
                "- 1-CLIQUE-AQUI-PARA-INSTALAR.bat",
                "- config.yaml",
                "- install.ps1",
                "- codigo do agente em Python",
            ]
            if partner:
                fallback_files.append("- branding.ini")
            readme_lines.extend(
                fallback_files
                + [
                    "",
                    "Como instalar:",
                    "1. Extraia todo o ZIP em uma pasta.",
                    "2. Clique duas vezes em 1-CLIQUE-AQUI-PARA-INSTALAR.bat.",
                    "3. Se necessario, ajuste o config.yaml em C:\\PrintCollect\\config.yaml",
                    "4. Teste com: C:\\PrintCollect\\.venv\\Scripts\\print-collect.exe --test",
                    "5. Execute uma coleta com: C:\\PrintCollect\\.venv\\Scripts\\print-collect.exe --once",
                    "",
                    "Observacao: este fallback exige Python 3.10+ instalado no Windows.",
                    "Quando o instalador standalone estiver configurado, o pacote incluira PrintCollectSetup.exe.",
                    "",
                ]
            )

        zf.writestr("LEIA-ME-WINDOWS.txt", "\r\n".join(readme_lines).encode("utf-8"))

    buf.seek(0)
    filename = f"print-collect-agent-windows-{agent_id}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
            alert = Alert(
                printer_id=printer.id,
                alert_type="supply" if "toner" in message.lower() else "device",
                message=message,
                severity=severity,
            )
            db.add(alert)
            db.flush()
            


@router.post("/agent/report")
async def agent_report(
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

        # ---------------------------------------------------------------------
        # JULIO PEDIU: NÃO SALVAR HISTÓRICO!
        # (Sempre sobrescreve apenas o ÚLTIMO contador na tabela `printers`.
        # Linhas comentadas = antigamente gravava Reading (tabela readings).
        # ---------------------------------------------------------------------
        # db.add(
        #     Reading(
        #         printer_id=printer.id,
        #         pages_total=reading.pages_total,
        #         pages_bw=reading.pages_bw,
        #         pages_color=reading.pages_color,
        #         toner_black=reading.toner_black,
        #         toner_cyan=reading.toner_cyan,
        #         toner_magenta=reading.toner_magenta,
        #         toner_yellow=reading.toner_yellow,
        #         status=reading.status,
        #         collected_at=now,
        #     )
        # )
        # ---------------------------------------------------------------------

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
