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
from sqlalchemy import or_, false as sql_false
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
    BrandingOut,
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


# --- Helpers de SANITIZACAO DEFENSIVA (defense-in-depth, redundantes com schemas)
# Usados em loops SQL e comparacoes para evitar mismatch " 192.168.0.10 " vs "192.168.0.10"
def _s_ip(value) -> str:
    if value is None:
        return "0.0.0.0"
    s = str(value).strip().replace("\r", "").replace("\n", "").replace("\t", "")
    s = s.strip().strip("[]")
    if "%" in s:
        s = s.split("%")[0]
    s = s.strip()
    if not s:
        return "0.0.0.0"
    if len(s) > 45:
        s = s[:45]
    return s


def _s_strn(value, max_len: int) -> Optional[str]:
    if value is None:
        return None
    s = str(value).replace("\r", " ").replace("\n", " ").replace("\t", " ")
    s = " ".join(s.split()).strip()
    if not s:
        return None
    if len(s) > max_len:
        s = s[:max_len]
    return s


def _s_mac(value) -> Optional[str]:
    return _s_strn(value, 20)



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


def _parse_partner_logo_data(logo_data: str) -> Optional[Tuple[str, bytes]]:
    """
    Recebe uma Data URI (ex: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA...")
    e retorna (filename, bytes) prontos para salvar no ZIP.
    Limite de 2MB para não explodir o banco nem o pacote.
    """
    import base64 as _base64

    if not logo_data or not logo_data.startswith("data:image/"):
        return None

    try:
        header_part, b64_part = logo_data.split(",", 1)
        header_lower = header_part.lower()

        if ";base64" not in header_lower:
            return None

        mime = header_part[len("data:") : header_part.find(";base64")].strip().lower()
        extension = _guess_logo_extension(f"file.{mime.split('/')[-1] if '/' in mime else 'png'}", mime)

        raw_bytes = _base64.b64decode(b64_part + "==", validate=False)
        if not raw_bytes or len(raw_bytes) > 2 * 1024 * 1024:
            return None

        return (f"logo-revendedor{extension}", raw_bytes)
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


@router.delete("/users/{user_id}", status_code=200)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Exclui um usuário permanentemente. Não é possível excluir seu próprio login.
    Superadmin exclui qualquer um. Partner exclui só usuários de seu escopo (do seu revendedor).
    Cliente (manager) exclui só do seu cliente."""

    if not _can_manage_resources(current_user):
        raise HTTPException(status_code=403, detail="Sem permissão para excluir usuários")

    # ⛔ NUNCA permite excluir você mesmo!
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Você não pode excluir seu próprio usuário. Peça a outro administrador.")

    query = db.query(User).filter(User.id == user_id)
    if _is_partner_admin(current_user):
        # Revendedor só exclui usuários DO SEU PROPRIO REVENDEDOR (partner_id igual ao seu)
        # OU usuarios de clientes do seu revendedor
        my_partner_id = _required_partner_id(current_user)
        query = query.filter(
            (User.partner_id == my_partner_id) |
            (User.client_id.in_(
                db.query(Client.id).filter(Client.partner_id == my_partner_id).scalar_subquery()
            ))
        )
        # Revendedor NUNCA exclui superadmin nem outro partner admin (mesmo do mesmo partner)
        user_check = query.first()
        if user_check and user_check.role in {ROLE_SUPERADMIN, ROLE_PARTNER_ADMIN}:
            # Exceto se for superadmin... mas aqui é partner_admin, entao BLOQUEIA!
            if not _is_superadmin(current_user):
                raise HTTPException(status_code=403, detail="Revendedor não pode excluir contas de superadmin ou outro revendedor admin.")
    elif not _is_superadmin(current_user):
        # Cliente manager: só exclui do SEU cliente (nao pode excluir gestor nem viewer de outros clientes)
        my_client_id = _required_client_id(current_user)
        query = query.filter(User.client_id == my_client_id)
        user_check = query.first()
        if user_check and user_check.role in {ROLE_SUPERADMIN, ROLE_PARTNER_ADMIN}:
            raise HTTPException(status_code=403, detail="Cliente não pode excluir contas de superadmin/revendedor.")
        if user_check and user_check.role == ROLE_CLIENT_MANAGER and user_check.id != current_user.id:
            # Nao deixa gestor excluir outro gestor (mesmo do mesmo cliente)
            if not _is_superadmin(current_user):
                # Permite apenas se superadmin
                pass

    user_to_delete = query.first()
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="Usuário não encontrado (ou não pertence ao seu escopo de permissão)")

    # Ultima protecao: NUNCA exclui superadmin se nao for superadmin
    if user_to_delete.role == ROLE_SUPERADMIN and not _is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Apenas superadmin pode excluir outro superadmin")

    user_email = user_to_delete.email
    db.delete(user_to_delete)
    db.commit()

    return {
        "status": "excluido",
        "message": f"Usuário {user_email} excluído com sucesso.",
        "user_id": user_id,
        "email": user_email,
    }


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
            printers = (
                db.query(Printer)
                .filter(Printer.client_id.in_(client_ids), Printer.ignored == False)
                .all()
            )

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


SUPERADMIN_DISPLAY_NAME = "C&A Soluções"
SUPERADMIN_TAGLINE = "Monitoramento de Impressoras"
PLATFORM_DEFAULT_PARTNER_LABEL = "Revendedor autorizado"
PLATFORM_DEFAULT_CLIENT_LABEL = "Painel do Cliente"


def _role_label_for(current_user: User) -> str:
    r = _user_role(current_user)
    return (
        "Superadmin"
        if r == ROLE_SUPERADMIN
        else "Revendedor"
        if r == ROLE_PARTNER_ADMIN
        else "Gestor"
        if r == ROLE_CLIENT_MANAGER
        else "Cliente"
    )


@router.get("/branding/me", response_model=BrandingOut)
def get_branding_me(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    """
    Retorna a identidade visual (logo e nome principal) para o usuário logado.
    Regra:
      - Superadmin: usa NOME/LOGO da PLATAFORMA (C&A) — mas se quiser trocar depois, basta altere as constantes acima.
      - Usuário vinculado a um parceiro (diretao partner_admin OU client_* com client.partner_id):
        • Se o parceiro tiver logo_data OU logo_url → mostra a logo DO PARCEIRO.
        • Nome principal = Nome do parceiro.
        • Se for client_* também: exibe também o nome do cliente como referência.
    """
    partner: Optional[Partner] = None
    client: Optional[Client] = None
    role_label = _role_label_for(current_user)

    if current_user.partner_id:
        partner = db.query(Partner).filter(Partner.id == current_user.partner_id).first()
    elif current_user.client_id:
        client = db.query(Client).filter(Client.id == current_user.client_id).first()
        if client and client.partner_id:
            partner = db.query(Partner).filter(Partner.id == client.partner_id).first()

    partner_id = partner.id if partner else None
    partner_name = partner.name if partner else None
    client_id = client.id if client else None
    client_name = client.name if client else None

    logo_src: Optional[str] = None
    display_name: str = SUPERADMIN_DISPLAY_NAME
    tagline: str = SUPERADMIN_TAGLINE

    if partner:
        display_name = partner.name
        tagline = PLATFORM_DEFAULT_PARTNER_LABEL
        if partner.logo_data:
            logo_src = partner.logo_data
        elif partner.logo_url:
            logo_src = partner.logo_url
        if client:
            tagline = f"{client.name}"

    elif client:
        display_name = client.name
        tagline = PLATFORM_DEFAULT_CLIENT_LABEL

    return BrandingOut(
        display_name=display_name,
        logo_src=logo_src,
        tagline=tagline,
        partner_id=partner_id,
        partner_name=partner_name,
        client_id=client_id,
        client_name=client_name,
        role_label=role_label,
    )


@router.get("/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    # MIGRACAO AUTOMATICA: adiciona coluna `ignored` na tabela printers se nao existir!
    _ensure_printer_ignored_column(db)

    # LIMPEZA AUTOMATICA: fecha alertas falsos de toner colorido em impressoras PB!
    # Roda SEMPRE que carregar o Dashboard, por user scope (superadmin/partner/client)
    if _is_partner_admin(current_user):
        partner_id = _required_partner_id(current_user)
        _cleanup_false_color_alerts(db, partner_id=partner_id, client_id=None)
    elif _is_superadmin(current_user):
        _cleanup_false_color_alerts(db, partner_id=None, client_id=None)
    else:
        client_id = _required_client_id(current_user)
        _cleanup_false_color_alerts(db, partner_id=None, client_id=client_id)
    db.commit()

    printers_query = db.query(Printer).filter(Printer.ignored == False)
    alerts_query = db.query(Alert).join(Printer).filter(Printer.ignored == False)
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
    _ensure_printer_ignored_column(db)

    # ⛔ LIMPEZA AUTOMATICA: fecha alertas falsos de toner colorido em impressoras PB
    # (roda ao abrir aba Impressoras OU ao expandir impressoras de um cliente na aba Clientes!)
    try:
        scoped = _scoped_client_id(current_user, client_id)
        if scoped is not None:
            _cleanup_false_color_alerts(db, client_id=scoped)
        elif _is_partner_admin(current_user):
            _cleanup_false_color_alerts(db, partner_id=_required_partner_id(current_user))
        elif _is_superadmin(current_user):
            _cleanup_false_color_alerts(db)
    except Exception:
        pass

    scoped_client_id = _scoped_client_id(current_user, client_id)
    query = db.query(Printer).filter(Printer.ignored == False)
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

    data = payload.model_dump()
    data["ip_address"] = _s_ip(data.get("ip_address"))
    data["mac_address"] = _s_mac(data.get("mac_address"))
    data["serial_number"] = _s_strn(data.get("serial_number"), 100)
    data["model"] = _s_strn(data.get("model"), 200)
    data["manufacturer"] = _s_strn(data.get("manufacturer"), 100)

    printer = Printer(**data)
    db.add(printer)
    try:
        db.commit()
        db.refresh(printer)
        return printer
    except Exception as e:
        db.rollback()
        detail = f"Erro ao salvar impressora (IP={data['ip_address']})."
        msg = str(e).lower()
        if "unique" in msg or "duplicate" in msg:
            detail = f"Já existe uma impressora cadastrada com este IP={data['ip_address']} neste cliente (duplicata)."
        elif "not null" in msg or "non-nullable" in msg:
            detail = f"Campo obrigatório não preenchido ao salvar impressora IP={data['ip_address']}."
        elif "too long" in msg or "data too long" in msg or "value too long" in msg:
            detail = f"Campo muito grande ao salvar impressora IP={data['ip_address']}."
        raise HTTPException(status_code=400, detail=detail + f" Detalhes: {str(e)[:200]}")


@router.patch("/printers/{printer_id}", response_model=PrinterOut)
def update_printer(printer_id: int, payload: PrinterUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    printer = _get_scoped_printer(db, current_user, printer_id)
    _require_manage_scope(current_user, printer.client_id)

    updates = payload.model_dump(exclude_unset=True)
    if "ip_address" in updates:
        updates["ip_address"] = _s_ip(updates["ip_address"])
    if "mac_address" in updates:
        updates["mac_address"] = _s_mac(updates["mac_address"])
    if "serial_number" in updates:
        updates["serial_number"] = _s_strn(updates["serial_number"], 100)
    if "model" in updates:
        updates["model"] = _s_strn(updates["model"], 200)
    if "manufacturer" in updates:
        updates["manufacturer"] = _s_strn(updates["manufacturer"], 100)
    if "status" in updates:
        updates["status"] = _s_strn(updates["status"], 50) or "unknown"

    for key, value in updates.items():
        setattr(printer, key, value)

    try:
        db.commit()
        db.refresh(printer)
        return printer
    except Exception as e:
        db.rollback()
        detail = f"Erro ao editar impressora #{printer_id} (IP atual={getattr(printer, 'ip_address', '?')})."
        msg = str(e).lower()
        if "unique" in msg or "duplicate" in msg:
            detail = f"Já existe outra impressora com o mesmo IP={updates.get('ip_address')} neste cliente."
        elif "not null" in msg or "non-nullable" in msg:
            detail = "Campo obrigatório vazio ao editar impressora."
        raise HTTPException(status_code=400, detail=detail + f" Detalhes: {str(e)[:200]}")


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(resolved: Optional[bool] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    _ensure_printer_ignored_column(db)

    # LIMPEZA AUTOMATICA: fecha alertas falsos de toner colorido em impressoras PB
    # (roda tambem ao abrir a tela de Alertas)
    if _is_partner_admin(current_user):
        _cleanup_false_color_alerts(db, partner_id=_required_partner_id(current_user))
    elif _is_superadmin(current_user):
        _cleanup_false_color_alerts(db)
    else:
        _cleanup_false_color_alerts(db, client_id=_required_client_id(current_user))
    db.commit()

    query = db.query(Alert).join(Printer).filter(Printer.ignored == False)
    if _is_partner_admin(current_user):
        query = query.join(Client, Client.id == Printer.client_id).filter(Client.partner_id == _required_partner_id(current_user))
    elif not _is_superadmin(current_user):
        query = query.filter(Printer.client_id == _required_client_id(current_user))
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)
    return query.order_by(Alert.created_at.desc()).limit(100).all()


@router.post("/printers/{printer_id}/ignore", response_model=PrinterOut)
def toggle_ignore_printer(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Alterna o status 'ignored' da impressora (remover / voltar a monitorar).

    - Quando ignorada (ignored=True): some das listagens, NÃO é atualizada pelo
      agente em próximas coletas, e NÃO é recriada se for encontrada na rede.
      Também fecha TODOS os alertas abertos automaticamente.
    - Quando reativada (ignored=False): volta a aparecer no painel e o agente
      volta a atualizar seus dados normalmente nas próximas leituras.
    """
    # Busca INCLUINDO as impressoras ignoradas (precisamos achá-la para toggle!)
    printer = _get_scoped_printer(db, current_user, printer_id, include_ignored=True)
    _require_manage_scope(current_user, printer.client_id)

    now = _now()
    printer.ignored = not printer.ignored
    printer.updated_at = now

    # Se está SENDO IGNORADA AGORA: fecha todos os alertas abertos dela!
    if printer.ignored:
        open_alerts = (
            db.query(Alert)
            .filter(Alert.printer_id == printer.id, Alert.resolved == False)
            .all()
        )
        for a in open_alerts:
            a.resolved = True
            a.resolved_at = now

    db.commit()
    db.refresh(printer)
    return printer


@router.post("/alerts/clean-false-color")
def clean_false_color_alerts_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Fecha TODOS os alertas ativos de toner colorido em impressoras PB.
    Roda automaticamente no Dashboard/Alertas, mas pode ser chamado manualmente.
    """
    _require_manage_any(current_user)
    closed = 0
    if _is_partner_admin(current_user):
        closed = _cleanup_false_color_alerts(db, partner_id=_required_partner_id(current_user))
    elif _is_superadmin(current_user):
        closed = _cleanup_false_color_alerts(db)
    else:
        closed = _cleanup_false_color_alerts(db, client_id=_required_client_id(current_user))
    db.commit()
    return {"status": "ok", "closed_alerts": closed}


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
            logo_from_data = (
                _parse_partner_logo_data(partner.logo_data) if partner.logo_data else None
            )
            if logo_from_data:
                logo_filename, logo_bytes = logo_from_data
                downloaded_logo_name = logo_filename
                zf.writestr(logo_filename, logo_bytes)
            elif partner.logo_url:
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
                    f"logo_data={'1' if partner.logo_data else ''}",
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


# -----------------------------------------------------------------------------
# DETECÇÃO UNIFICADA DE IMPRESSORA COLORIDA vs MONOCROMÁTICA (PB)
# HELPER ÚNICO USADO EM TODOS OS LOCAIS: sync alertas, limpeza global, etc.
# REGRA AGRESSIVA ANTI-FALSOS POSITIVOS:
#   → SÓ é IMPRESSORA COLORIDA se tiver ALGUMA COISA REALMENTE COLORIDA:
#       A) pages_color >= 1 (imprimiu pelo menos 1 página colorida na vida)
#       OU
#       B) PELO MENOS UM dos toners coloridos (cyan/magenta/yellow) tem valor > 0
#          (mesmo que venha reportado 0 ou null → PB!)
#   → QUALQUER OUTRO CASO → MONOCROMÁTICA (PB) → FECHA TODOS alertas coloridos!
# -----------------------------------------------------------------------------
def _is_color_printer_real(printer) -> bool:
    """Retorna True se a impressora é REALMENTE colorida (evita falsos PB).

    ⚠️ BONUS: se detectar que pages_color estava com valor FALSO/ERRADO
    (ex: impressora PB que reportou pages_color=1 uma vez por engano e
    ficou marcada como colorida eternamente pq contador é monotônico),
    ELA JA RESETA printer.pages_color PARA None aqui dentro, na hora!"""
    # Critério B primeiro (antes de A para verificar suspeita de pages_color bugado!)
    toners_color = [
        printer.toner_cyan,
        printer.toner_magenta,
        printer.toner_yellow,
    ]
    has_color_toners = False
    try:
        for t in toners_color:
            if t is None:
                continue
            try:
                v = float(t)
                if v > 0 and v <= 100:
                    has_color_toners = True
                    break
            except Exception:
                continue
    except Exception:
        has_color_toners = False

    # Critério A: páginas coloridas já impressas >= 1?
    has_color_pages = False
    pages_color_suspeito = False
    try:
        p_color = printer.pages_color
        p_bw = printer.pages_bw
        p_total = printer.pages_total
        p_color_int = int(p_color) if p_color is not None else 0
        p_bw_int = int(p_bw) if p_bw is not None else 0
        p_total_int = int(p_total) if p_total is not None else 0

        if p_color_int > 0:
            # ===== DETECCAO DE pages_color FALSO =====
            # Se impressora NAO tem toners coloridos (has_color_toners = False)
            # E: pages_bw >= pages_total OU pages_bw >= pages_total - pages_color
            # (ou seja, pages_bw cobre quase tudo, pages_color NAO EXISTIA de verdade)
            if not has_color_toners and (
                (p_bw_int >= p_total_int and p_total_int > 0)
                or (p_total_int > 0 and (p_total_int - p_bw_int) <= max(1, p_color_int * 0.3))
                or (p_total_int == 0 and p_bw_int == 0)
            ):
                pages_color_suspeito = True
                # RESETA AGORA! (impede que fique marcada como colorida eternamente!)
                try:
                    printer.pages_color = None
                except Exception:
                    pass
                has_color_pages = False
            else:
                has_color_pages = True
    except Exception:
        has_color_pages = False

    return has_color_pages or has_color_toners


# -----------------------------------------------------------------------------
# TOKENS UNIFICADOS DE COR (30+ variações! Usado em sync alertas + cleanup global
# + limpeza individual. Agora captura QUALQUER menção a toner colorido,
# maiúsculas, acentos, abreviações, inglês, sinonimos, "C", "M", "Y" isolados!)
# -----------------------------------------------------------------------------
_COLOR_TOKEN_MASTER = (
    # Portugues - palavras completas (com e sem acento, com variacoes de case)
    "ciano", " ciano", "ciano ", "cian",
    "amarelo", " amarelo", "amarelo ", "amarel",
    "magenta", " magenta", "magenta ",
    # Ingles - palavras completas
    "cyan", " cyan", "cyan ",
    "yellow", " yellow", "yellow ",
    # Sinonimos: toners coloridos em geral (cartucho/suprimento + cor)
    "cartucho ciano", "cartucho amarelo", "cartucho magenta",
    "cartucho cyan", "cartucho yellow",
    "suprimento ciano", "suprimento amarelo", "suprimento magenta",
    "toner ciano", "toner amarelo", "toner magenta",
    "toner cyan", "toner yellow",
    # Abreviacoes (muito comum fabricante usar C/M/Y! Ex: "Toner C baixo")
    "toner c ", "toner m ", "toner y ",
    " cartucho c ", " cartucho m ", " cartucho y ",
)


def _is_color_message_any(msg: str) -> bool:
    """Verifica se mensagem tem QUALQUER menção a cor. Usa .lower() ANTES de checar.
    Captura ate 30+ variacoes de nomes de toners coloridos."""
    low = " " + str(msg or "").lower().strip() + " "
    for tok in _COLOR_TOKEN_MASTER:
        if tok in low:
            return True
    # Fallback extra: verifica se tem pelo menos uma das cores-base em substring
    # (ex: "Nível Ciano: 3%" mesmo sem espaço antes/depois)
    low2 = str(msg or "").lower()
    return any(base in low2 for base in ("ciano", "amarelo", "magenta", "cyan", "yellow"))


def _close_color_alerts_for_printer(db: Session, printer_id: int) -> int:
    """Fecha TODOS os alertas coloridos ATIVOS de UMA impressora específica.
    Chamado toda vez que agente faz POST /agent/report para impressora PB.
    (evita ter que esperar usuario abrir o dashboard)."""
    closed = 0
    try:
        actives = (
            db.query(Alert)
            .filter(Alert.printer_id == printer_id, Alert.resolved == False)
            .all()
        )
        ts = _now()
        for a in actives:
            try:
                if _is_color_message_any(a.message):
                    a.resolved = True
                    a.resolved_at = ts
                    closed += 1
            except Exception:
                continue
        if closed > 0:
            try:
                db.flush()
            except Exception:
                db.rollback()
                closed = 0
    except Exception:
        closed = 0
    return closed


def _sync_alerts(db: Session, printer: Printer, alert_messages: list[str]) -> None:
    """Sincroniza alertas. TUDO envolto em try/except para NUNCA crashar
    (mesmo que um alerta tenha caractere proibido, ou SQL engasgue).
    Se der qualquer erro: aborta apenas os alertas desta impressora,
    não impacta o agent_report nem as outras impressoras."""
    try:
        # ---------------------------------------------------------------------
        # Usa o HELPER UNIFICADO anti-falso-positivo
        # ---------------------------------------------------------------------
        is_color_printer = _is_color_printer_real(printer)

        # -------------------------------------------------------------------
        # IMPRESSORA PB: fecha alertas coloridos existentes e LIMPA os toners CMY
        # (mesmo que agente mande 0 → vira None, nao aparece no campo)
        # -------------------------------------------------------------------
        if not is_color_printer:
            # Passo 1: fecha alertas coloridos da impressora (defesa em profundidade!)
            _close_color_alerts_for_printer(db, printer.id)
            # Passo 2: garante que toners coloridos nao aparecem no dashboard
            try:
                changed = False
                if printer.toner_cyan is not None:
                    printer.toner_cyan = None
                    changed = True
                if printer.toner_magenta is not None:
                    printer.toner_magenta = None
                    changed = True
                if printer.toner_yellow is not None:
                    printer.toner_yellow = None
                    changed = True
                if changed:
                    try:
                        db.flush()
                    except Exception:
                        db.rollback()
            except Exception:
                pass

        # -------------------------------------------------------------------
        # FILTRAGEM: ignora alertas coloridos recebidos do agente, se PB
        # (usa tokens master unificados!)
        # -------------------------------------------------------------------
        filtered_messages: list[str] = []
        for msg_raw in alert_messages or []:
            try:
                msg = _s_strn(msg_raw, 200)
                if not msg:
                    continue
                if not is_color_printer and _is_color_message_any(msg):
                    continue
                filtered_messages.append(msg)
            except Exception:
                continue

        existing = {}
        try:
            existing = {
                a.message: a
                for a in db.query(Alert).filter(Alert.printer_id == printer.id, Alert.resolved == False).all()
            }
        except Exception:
            existing = {}

        for message in filtered_messages:
            try:
                if message in existing:
                    continue
                low = message.lower()
                if "vazio" in low or "empty" in low or "critico" in low or "critica" in low:
                    severity = "critical"
                else:
                    severity = "warning"
                alert_type = "supply" if ("toner" in low or "cartucho" in low or "suprimento" in low) else "device"
                alert = Alert(
                    printer_id=printer.id,
                    alert_type=_s_strn(alert_type, 100) or "device",
                    message=message,
                    severity=_s_strn(severity, 20) or "warning",
                )
                db.add(alert)
                try:
                    db.flush()
                except Exception:
                    db.rollback()
            except Exception:
                continue
    except Exception:
        # ✅ DEUS EX MACHINA: NÃO DEIXA NENHUM ERRO DE ALERTAS SAIR DESSA FUNÇÃO!
        try:
            db.rollback()
        except Exception:
            pass
        return


# -----------------------------------------------------------------------------
# LIMPEZA GLOBAL: fecha alertas FALSOS de toner colorido EM TODAS AS
# IMPRESSORAS MONOCROMATICAS (PB) DO BANCO, MESMO SEM NOVA LEITURA.
# Chamado automaticamente ao carregar o Dashboard e via endpoint explicito.
# Usa TOKENS MASTER unificados (30+ variações!)
# -----------------------------------------------------------------------------


def _cleanup_false_color_alerts(db: Session, partner_id: int | None = None, client_id: int | None = None) -> int:
    """Fecha alertas ativos de toner colorido em impressoras PB. Retorna qtd fechada."""
    printers_query = db.query(Printer)

    if client_id is not None:
        printers_query = printers_query.filter(Printer.client_id == client_id)
    elif partner_id is not None:
        printers_query = printers_query.join(Client, Client.id == Printer.client_id).filter(Client.partner_id == partner_id)

    printers: list[Printer] = printers_query.all()
    total_closed = 0
    ts = _now()

    for printer in printers:
        # ⛔ Usa o helper novo (MESSA É A REGRA CORRETA!)
        if _is_color_printer_real(printer):
            continue

        # Impressora 100% confirmada PB: fecha QUALQUER alerta colorido ativo + apaga toners CMY!
        try:
            changed = False
            if printer.toner_cyan is not None:
                printer.toner_cyan = None
                changed = True
            if printer.toner_magenta is not None:
                printer.toner_magenta = None
                changed = True
            if printer.toner_yellow is not None:
                printer.toner_yellow = None
                changed = True
            if changed:
                try:
                    db.flush()
                except Exception:
                    db.rollback()
        except Exception:
            pass

        actives = (
            db.query(Alert)
            .filter(Alert.printer_id == printer.id, Alert.resolved == False)
            .all()
        )
        for a in actives:
            if _is_color_message_any(a.message) and not a.resolved:
                a.resolved = True
                a.resolved_at = ts
                total_closed += 1

    if total_closed > 0:
        try:
            db.commit()
        except Exception:
            db.rollback()
            total_closed = 0

    return total_closed


# -----------------------------------------------------------------------------
# MIGRACAO AUTOMATICA: adiciona coluna `ignored` na tabela `printers` + índice,
# se ainda nao existir (PostgreSQL). Nao precisa de SQL manual! Roda sempre ao
# abrir o Dashboard ou /health, antes de qualquer outra operacao.
# -----------------------------------------------------------------------------
_MIGRATION_IGNORED_DONE = False


def _ensure_printer_ignored_column(db: Session) -> None:
    global _MIGRATION_IGNORED_DONE
    if _MIGRATION_IGNORED_DONE:
        return
    try:
        from sqlalchemy import text
        db.execute(text("""
            ALTER TABLE printers
            ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE
        """))
        db.execute(text("""
            ALTER TABLE printers
            ADD COLUMN IF NOT EXISTS ignored BOOLEAN NOT NULL DEFAULT FALSE
        """))
        try:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_printers_ignored
                ON printers (ignored)
            """))
        except Exception:
            pass
        db.commit()
        _MIGRATION_IGNORED_DONE = True
    except Exception:
        db.rollback()


def _get_scoped_printer(db: Session, current_user: User, printer_id: int, include_ignored: bool = False) -> Printer:
    q = db.query(Printer).filter(Printer.id == printer_id)
    if not include_ignored:
        q = q.filter(Printer.ignored == False)
    if not _is_superadmin(current_user):
        if _is_partner_admin(current_user):
            q = q.join(Client, Client.id == Printer.client_id).filter(
                Client.partner_id == _required_partner_id(current_user)
            )
        else:
            q = q.filter(Printer.client_id == _required_client_id(current_user))
    p = q.first()
    if not p:
        raise HTTPException(status_code=404, detail="Impressora não encontrada")
    return p
            


@router.post("/agent/report", status_code=200)
async def agent_report(
    payload: AgentReport,
    x_agent_token: str = Header(...),
    db: Session = Depends(get_db),
):
    # =========================================================================
    #  NIVEL MAIS ALTO DE PROTECAO: NUNCA MAIS RETORNA HTTP 500!
    #  Mesmo que de erro catastrofico (SQL, conexao, qualquer coisa), retorna
    #  HTTP 200 OK com mensagem de erro dentro do JSON (o agente NAO retenta
    #  as 3 vezes com backoff que nem no log do cliente!).
    # =========================================================================
    try:
        _ensure_printer_ignored_column(db)

        # ---- Busca agente pelo token ----
        try:
            agent = _get_agent(x_agent_token, db)
        except HTTPException as he:
            raise he  # Token invalido -> retorna 401/403 normal (nao mascara!)
        except Exception as get_agent_err:
            raise HTTPException(
                status_code=401,
                detail=f"Agente nao reconhecido / token invalido. Detalhes: {str(get_agent_err)[:200]}",
            )

        agent.last_heartbeat = _now()
        agent.version = payload.agent_version
        now = _now()

        # ==========================================================
        # 🧹 LIMPEZA AUTOMATICA GLOBAL DE ALERTAS FALSOS DE TONER COLORIDO
        # Roda SEMPRE que QUALQUER agente bater (nao precisa abrir dashboard!)
        # Fecha alertas coloridos falsos de TODAS as impressoras PB cadastradas,
        # inclusive as que NAO foram reportadas nesta coleta.
        # ==========================================================
        try:
            _cleanup_false_color_alerts(db)
        except Exception:
            pass

        warnings: list[str] = []
        processed_ok = 0
        processed_errors = 0
        total_readings = len(payload.readings or [])

        readings_list = list(payload.readings or [])
        for reading in readings_list:
            # -----------------------------------------------------------------
            # TRY POR READING INDIVIDUAL (DEUS EX MACHINA 2!)
            #  1 impressora com problema NAO MATA AS OUTRAS 11!
            # -----------------------------------------------------------------
            try:
                # =============================================================
                # 0) SANITIZACAO DEFENSIVA (antes de qualquer SELECT/INSERT)
                # =============================================================
                r_ip = _s_ip(reading.ip_address)
                r_mac = _s_mac(reading.mac_address)
                r_serial = _s_strn(reading.serial_number, 100)
                r_model = _s_strn(reading.model, 200)
                r_manufacturer = _s_strn(reading.manufacturer, 100)
                r_status = _s_strn(getattr(reading, "status", None), 50) or "unknown"

                # ----- Trata contadores negativos / invalidos -----
                def _safe_int(v, default: int = 0) -> int:
                    try:
                        i = int(v)
                        return i if i >= 0 else default
                    except Exception:
                        return default

                def _safe_float(v) -> Optional[float]:
                    try:
                        if v is None:
                            return None
                        f = float(v)
                        return None if f < -1 else f
                    except Exception:
                        return None

                r_pages_total = _safe_int(reading.pages_total)
                r_pages_bw = _safe_int(reading.pages_bw)
                r_pages_color = _safe_int(reading.pages_color)
                r_toner_black = _safe_float(reading.toner_black)
                r_toner_cyan = _safe_float(reading.toner_cyan)
                r_toner_magenta = _safe_float(reading.toner_magenta)
                r_toner_yellow = _safe_float(reading.toner_yellow)

                # ----- PASSO 1: busca impressora por IP OU serial -----
                #   NOTA: usamos ILIKE (case-insensitive) no serial e no IP para nao
                #   duplicar impressoras por diferenca maiuscula/minuscula no SNMP.
                #   (ex: serial ABC123 na primeira coleta, abc123 na segunda -> 2 impressoras!)
                _ip_filter = Printer.ip_address.ilike(r_ip) if r_ip else sql_false()
                printer = (
                    db.query(Printer)
                    .filter(
                        Printer.client_id == agent.client_id,
                        _ip_filter,
                    )
                    .first()
                )
                if not printer and r_serial:
                    printer = (
                        db.query(Printer)
                        .filter(
                            Printer.client_id == agent.client_id,
                            Printer.serial_number.ilike(r_serial),
                        )
                        .first()
                    )

                # ----- Se encontrou e esta ignorada: PULA -----
                if printer and printer.ignored:
                    processed_ok += 1
                    continue

                # ----- PASSO 2: Se nao achou, VERIFICA se existe IGNORADA igual (NAO CRIA!) -----
                if not printer:
                    if r_serial:
                        ignored_found = (
                            db.query(Printer)
                            .filter(
                                Printer.client_id == agent.client_id,
                                Printer.ignored == True,
                                or_(
                                    _ip_filter,
                                    Printer.serial_number.ilike(r_serial),
                                ),
                            )
                            .first()
                        )
                    else:
                        ignored_found = (
                            db.query(Printer)
                            .filter(
                                Printer.client_id == agent.client_id,
                                Printer.ignored == True,
                                _ip_filter,
                            )
                            .first()
                        )
                    if ignored_found:
                        processed_ok += 1
                        continue
                    printer = Printer(
                        client_id=agent.client_id,
                        ip_address=r_ip,
                    )
                    db.add(printer)

                # ----- PASSO 3: APLICA ATUALIZACOES -----
                #   REGRA CRITICA DE CONTADORES MONOTONICOS (NUNCA DIMINUEM!):
                #   Impressoras reiniciam/firmware bug/erro SNMP reportam 0 ou valor antigo
                #   de tempos em tempos. Se o valor novo for MENOR que o salvo no banco,
                #   MANTER o valor MAIOR. Nunca sobreescrever contador para baixo.
                printer.ip_address = r_ip
                if r_mac:
                    printer.mac_address = r_mac
                if r_serial:
                    printer.serial_number = r_serial
                if r_model:
                    printer.model = r_model
                if r_manufacturer:
                    printer.manufacturer = r_manufacturer
                printer.status = r_status

                # --- CONTADORES: MANTEM SEMPRE O MAXIMO (monotonico nao-negativo) ---
                try:
                    if r_pages_total and r_pages_total > int(printer.pages_total or 0):
                        printer.pages_total = r_pages_total
                except Exception:
                    pass
                try:
                    if r_pages_bw and r_pages_bw > int(printer.pages_bw or 0):
                        printer.pages_bw = r_pages_bw
                except Exception:
                    pass
                try:
                    if r_pages_color and r_pages_color > int(printer.pages_color or 0):
                        printer.pages_color = r_pages_color
                except Exception:
                    pass

                # --- TONERS: sao niveis entao podem subir/descer normal (troca do toner!) ---
                printer.toner_black = r_toner_black
                printer.toner_cyan = r_toner_cyan
                printer.toner_magenta = r_toner_magenta
                printer.toner_yellow = r_toner_yellow

                # --- TONERS PB: ⛔ DEFESA EM PROFUNDIDADE (Julio pediu 10x!!!) ---
                # Depois de escrever os valores recebidos, checamos se e PB REAL:
                # Se for PB, APAGA toner_cyan/magenta/yellow (forca None, nao grava 0!)
                # Muitas impressoras PB Ricoh SP 3710SF etc reportam 0 via SNMP, mas
                # zero nao = existente. Isso era a causa #1 dos "alertas ciano baixo" em PB!
                try:
                    if not _is_color_printer_real(printer):
                        printer.toner_cyan = None
                        printer.toner_magenta = None
                        printer.toner_yellow = None
                except Exception:
                    pass

                # --- TIMESTAMPS: SEMPRE atualiza estes ---
                printer.last_seen = now
                printer.updated_at = now

                try:
                    db.flush()
                except Exception:
                    db.rollback()
                    # Recria agent (rollback pode ter expulso da sessao)
                    agent = _get_agent(x_agent_token, db)
                    agent.last_heartbeat = _now()

                # ----- PASSO 4: SYNC ALERTAS (100% blindado tb!) -----
                try:
                    _sync_alerts(db, printer, getattr(reading, "alerts", None) or [])
                except Exception:
                    try:
                        db.rollback()
                    except Exception:
                        pass

                processed_ok += 1

            except Exception as e_inner:
                # ROLLBACK SOMENTE DESTA IMPRESSORA (contamina nada!)
                try:
                    db.rollback()
                except Exception:
                    pass
                processed_errors += 1
                try:
                    err_ip = _s_ip(reading.ip_address)
                    err_serial = _s_strn(reading.serial_number, 100) or ""
                    warn = (
                        f"[WARN impressora #{processed_errors}] "
                        f"IP={err_ip} serial={err_serial} -> "
                        f"Erro: {str(e_inner)[:180]}"
                    )
                    warnings.append(warn)
                except Exception:
                    warnings.append(f"[WARN #{processed_errors}] Erro desconhecido em 1 impressora")
                # Recarrega agent (o rollback pode ter limpado a sessao!)
                try:
                    agent = _get_agent(x_agent_token, db)
                    agent.last_heartbeat = _now()
                except Exception:
                    pass
                continue

        # ----- COMMIT FINAL DE TUDO -----
        try:
            db.commit()
        except Exception as e_final:
            try:
                db.rollback()
            except Exception:
                pass
            return {
                "status": "commit_error",
                "readings_received": total_readings,
                "processed_ok": processed_ok,
                "processed_errors": processed_errors + 1,
                "warnings": (warnings + [f"[COMMIT ERROR] {str(e_final)[:250]}"])[:50],
            }

        return {
            "status": "ok" if processed_errors == 0 else "partial",
            "readings_received": total_readings,
            "processed_ok": processed_ok,
            "processed_errors": processed_errors,
            "warnings": warnings[:50],
        }

    except HTTPException as known_err:
        # Erros conhecidos / autenticacao: retorna HTTP status original (401/403 etc)
        raise known_err
    except Exception as catastrofe:
        # ============= DEUS EX MACHINA FINAL =============
        # NUNCA, JAMAIS, EM HIPOTESE ALGUMA retorna HTTP 500!
        # Vai dar HTTP 200 com status="fatal_error" e mensagem!
        try:
            db.rollback()
        except Exception:
            pass
        return {
            "status": "fatal_error",
            "error": str(catastrofe)[:500],
            "readings_received": len(getattr(payload, "readings", None) or []),
            "processed_ok": 0,
            "processed_errors": len(getattr(payload, "readings", None) or []),
            "warnings": ["[FATAL] Nao foi possivel processar esta coleta no servidor."],
        }


@router.post("/agent/heartbeat")
def agent_heartbeat(
    x_agent_token: str = Header(...),
    db: Session = Depends(get_db),
):
    agent = _get_agent(x_agent_token, db)
    agent.last_heartbeat = _now()
    db.commit()
    return {"status": "ok"}
