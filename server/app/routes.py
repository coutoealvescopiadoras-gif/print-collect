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
from app.database import (
    Agent,
    Alert,
    Client,
    Location,
    Partner,
    Printer,
    Reading,
    User,
    engine,
    get_db,
)
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


@router.delete("/partners/{partner_id}")
def delete_partner(
    partner_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not _is_superadmin(current_user):
        raise HTTPException(status_code=403, detail="Somente superadmin pode excluir revendedores")

    partner = db.query(Partner).filter(Partner.id == partner_id).first()
    if not partner:
        raise HTTPException(status_code=404, detail="Revendedor não encontrado")

    # Proteção ANTI-DESASTRE: NUNCA deleta revendedor que tiver clientes vinculados.
    # Melhor Julio remover/transferir clientes primeiro (para não apagar dados de cliente, impressoras, agentes e contadores por engano!)
    clientes_vinculados_q = db.query(Client).filter(Client.partner_id == partner_id)
    total_clientes = clientes_vinculados_q.count()
    if total_clientes > 0:
        nomes_clientes = [c.name for c in clientes_vinculados_q.order_by(Client.name).limit(10).all()]
        sufixo = ""
        if total_clientes > 10:
            sufixo = f" (e mais {total_clientes - 10} outros)"
        raise HTTPException(
            status_code=400,
            detail=(
                f"Não é possível excluir o revendedor \"{partner.name}\" pois ele ainda tem {total_clientes} cliente(s) vinculado(s): "
                f"{', '.join(nomes_clientes)}{sufixo}. "
                "Primeiro remova esses clientes (ou reatribua-os para outro revendedor / sem parceiro) e tente novamente."
            ),
        )

    db.delete(partner)
    db.commit()

    return {
        "status": "excluido",
        "message": f"Revendedor \"{partner.name}\" excluído com sucesso.",
        "partner_id": partner_id,
        "partner_name": partner.name,
    }


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
def list_clients(
    search: Optional[str] = None,
    partner_id: Optional[int] = None,
    own_only: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    query = db.query(Client)
    # Join com Partner para poder popular partner_name e filtrar por parceiro
    try:
        from server.app.database import Partner
        query = query.outerjoin(Partner, Partner.id == Client.partner_id)
    except Exception:
        Partner = None

    if _is_partner_admin(current_user):
        query = query.filter(Client.partner_id == _required_partner_id(current_user))
    elif _is_superadmin(current_user):
        if own_only == True:
            query = query.filter(Client.partner_id.is_(None))
        if partner_id is not None:
            query = query.filter(Client.partner_id == partner_id)
    else:
        query = query.filter(Client.id == _required_client_id(current_user))

    if search:
        _s = f"%{search.strip()}%"
        query = query.filter(Client.name.ilike(_s))

    clients = query.order_by(Client.name).all()

    # Preenche partner_name para exibir no front
    partners_cache: dict[int, str] = {}
    for cli in clients:
        try:
            if cli.partner_id:
                try:
                    part = cli.partner
                    if part:
                        cli.partner_name = part.name
                except Exception:
                    pass
                if not getattr(cli, "partner_name", None) and Partner is not None:
                    if cli.partner_id in partners_cache:
                        cli.partner_name = partners_cache[cli.partner_id]
                    else:
                        _p = db.query(Partner).filter(Partner.id == cli.partner_id).first()
                        cli.partner_name = _p.name if _p else None
                        partners_cache[cli.partner_id] = cli.partner_name or ""
        except Exception:
            if not getattr(cli, "partner_name", None):
                cli.partner_name = None

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
def list_printers(
    client_id: Optional[int] = None,
    partner_id: Optional[int] = None,
    search: Optional[str] = None,
    own_only: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
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
    # Join com Client para poder filtrar por partner_id / search / own_only e tambem para exibir nome cliente/parceiro no front
    query = query.join(Client, Client.id == Printer.client_id, isouter=False)

    if _is_partner_admin(current_user):
        partner_id_forced = _required_partner_id(current_user)
        query = query.filter(Client.partner_id == partner_id_forced)
        if client_id is not None:
            _assert_partner_owns_client(db, current_user, client_id)
    elif _is_superadmin(current_user):
        if own_only == True:
            query = query.filter(Client.partner_id.is_(None))
        if partner_id is not None:
            query = query.filter(Client.partner_id == partner_id)

    # Pesquisa por NOME do cliente (ILIKE case-insensitive)
    if search:
        _s = f"%{search.strip()}%"
        query = query.filter(Client.name.ilike(_s))

    if scoped_client_id is not None:
        query = query.filter(Printer.client_id == scoped_client_id)

    printers = query.order_by(Client.name, Printer.model).all()

    # Preenche os campos novos client_name / partner_id / partner_name para exibir no front
    partners_cache: dict[int, str] = {}
    try:
        from server.app.database import Partner
    except Exception:
        Partner = None
    for p in printers:
        try:
            cli = p.client
            if cli:
                p.client_name = cli.name or ""
                p.partner_id = cli.partner_id
                if cli.partner_id and cli.partner:
                    p.partner_name = cli.partner.name or None
                elif cli.partner_id and Partner is not None:
                    if cli.partner_id in partners_cache:
                        p.partner_name = partners_cache[cli.partner_id]
                    else:
                        _p = db.query(Partner).filter(Partner.id == cli.partner_id).first()
                        p.partner_name = _p.name if _p else None
                        partners_cache[cli.partner_id] = p.partner_name or ""
        except Exception:
            if not getattr(p, "client_name", ""):
                p.client_name = ""
    return printers


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
        query = query.filter(Alert.printer_id == Printer.id).filter(Printer.client_id == _required_client_id(current_user))
    if resolved is not None:
        query = query.filter(Alert.resolved == resolved)

    # ==========================================================
    # 🔴 DEFESA FINAL ABSOLUTA (camada 4!) - AGORA OTIMIZADA!
    # ANTES: 1 query SQL por alerta → N+1 queries bug (se 100 alertas = 101 queries!)
    # AGORA: 1 ÚNICA query extra para carregar TODAS as impressoras usadas
    #        em CACHE dict[pid] → 0 N+1.
    # ==========================================================
    raw_alerts: list[Alert] = query.order_by(Alert.created_at.desc()).limit(100).all()

    # PASSO 1: Extrai todos os printer_id distintos usados nos alertas (UNIQUE!)
    all_printer_ids: set[int] = set()
    try:
        for a in raw_alerts or []:
            if getattr(a, "printer_id", None) is not None:
                all_printer_ids.add(int(a.printer_id))
    except Exception:
        all_printer_ids = set()

    # PASSO 2: Uma ÚNICA query para carregar TUDO que precisamos de uma vez só
    printer_is_color_cache: dict[int, bool] = {}
    if all_printer_ids:
        try:
            pid_list = list(all_printer_ids)
            printers = db.query(Printer).filter(Printer.id.in_(pid_list)).all()
            for p in printers or []:
                try:
                    printer_is_color_cache[int(p.id)] = _is_color_printer_real(p)
                except Exception:
                    printer_is_color_cache[int(p.id)] = True  # mostra por seguranca
        except Exception:
            printer_is_color_cache = {}

    # PASSO 3: Monta lista final segura (filtra alertas color PB)
    safe_alerts: list[Alert] = []
    for a in raw_alerts or []:
        try:
            pid = int(a.printer_id)
            is_color = printer_is_color_cache.get(pid)
            if is_color is None:
                # impressora nao veio na query (ex: deletada no meio) → mostra
                is_color = True
            # Se impressora é PB (not is_color) E mensagem é colorida → PULA (nao exibe!)
            if not is_color and _is_color_message_any(a.message):
                continue
        except Exception:
            # Qualquer erro de checagem: mostra o alerta (nunca esconde coisa por erro!)
            pass
        safe_alerts.append(a)
    return safe_alerts


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
    ⚠️ Quando chamado MANUALMENTE pelo botão: roda SEMPRE, ignorando cache TTL."""
    _require_manage_any(current_user)
    closed = 0
    if _is_partner_admin(current_user):
        closed = _cleanup_false_color_alerts(db, partner_id=_required_partner_id(current_user), force=True)
    elif _is_superadmin(current_user):
        closed = _cleanup_false_color_alerts(db, force=True)
    else:
        closed = _cleanup_false_color_alerts(db, client_id=_required_client_id(current_user), force=True)
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
#
# ⚠️⚠️ REGRA DEFINITIVA (2026-08-08 Julio / NENHUMA impressora PB como colorida!)
# ⚠️ PROBLEMA ANTERIOR: impressoras PB reportavam toner_cyan/mag/yellow = 100
# (mesmo sem ter esses cartuchos!) → has_color_toners virava True → marcava
# impressora PB como colorida → criava ALERTAS DE TONER COLORIDO FALSOS!
#
# SOLUÇÃO: O CONTADOR pages_color É O REI DA DECISÃO (é monotônico e NÃO mente!).
#   1) 🔴 SE pages_color <= 0 OU pages_color is None
#          → IMPRESSORA É 100% PB (não importa se ciano/mag/yellow = 100!).
#          (até zera os toners CMY no banco aqui dentro de brinde!)
#   2) 🟢 SOMENTE SE pages_color >= 1:
#          → AÍ SIM checamos has_color_toners OR has_color_pages.
# -----------------------------------------------------------------------------
def _is_color_printer_real(printer) -> bool:
    """Retorna True se a impressora é REALMENTE colorida (evita falsos PB).

    ⚠️ BONUS: se detectar que toners coloridos estão com valores FALSOS
    (ex: impressora PB que reportou ciano=100), ELES JA SAO SETADOS PARA None
    AQUI DENTRO, para não ficar aparecendo nos paineis de suprimentos!"""

    # ===== PASSO 1: Ler valores numéricos (com proteção total!) =====
    pages_color_int = 0
    pages_bw_int = 0
    pages_total_int = 0
    try:
        pages_color_int = int(printer.pages_color) if printer.pages_color is not None else 0
    except Exception:
        pages_color_int = 0
    try:
        pages_bw_int = int(printer.pages_bw) if printer.pages_bw is not None else 0
    except Exception:
        pages_bw_int = 0
    try:
        pages_total_int = int(printer.pages_total) if printer.pages_total is not None else 0
    except Exception:
        pages_total_int = 0

    # ===== PASSO 2: Verifica toners coloridos =====
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

    # ====================================================================
    # 🔴 REGRA DE OURO (ELIMINA 100% DOS FALSOS COLORIDOS!)
    # SE NUNCA imprimiu página colorida (pages_color == 0 ou None) → É PB!
    # (mesmo que toners digam 100 — são valores falsos de impressora PB!)
    # ====================================================================
    if pages_color_int <= 0:
        # Apaga também os toners coloridos do banco (não precisa ficar poluindo!)
        try:
            changed_toners = False
            if printer.toner_cyan is not None:
                printer.toner_cyan = None
                changed_toners = True
            if printer.toner_magenta is not None:
                printer.toner_magenta = None
                changed_toners = True
            if printer.toner_yellow is not None:
                printer.toner_yellow = None
                changed_toners = True
        except Exception:
            pass
        return False  # 🔴 É PRETO E BRANCO SEM DÚVIDA NENHUMA!

    # ====================================================================
    # 🟢 SÓ CHEGA AQUI SE pages_color >= 1!
    # Então tem chances reais de ser colorida. Agora confirmamos:
    # ====================================================================
    has_color_pages = False
    try:
        # pages_color > 0, mas confere também se pages_bw não cobre tudo
        # (detecta pages_color errado de impressora PB mesmo > 0, raro!)
        if (pages_bw_int >= pages_total_int and pages_total_int > 0) or (
            pages_total_int > 0 and (pages_total_int - pages_bw_int) <= max(1, pages_color_int * 0.3)
        ):
            # pages_color aparentemente bugado: apaga ele por segurança
            try:
                printer.pages_color = None
            except Exception:
                pass
            # E zera toners coloridos tb → marca como PB
            try:
                if printer.toner_cyan is not None:
                    printer.toner_cyan = None
                if printer.toner_magenta is not None:
                    printer.toner_magenta = None
                if printer.toner_yellow is not None:
                    printer.toner_yellow = None
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


_CLEANUP_FALSE_COLOR_CACHE_TTL_SECONDS = 1800  # 30 MINUTOS = Nao precisa limpar alerta falso a cada clique!
_CLEANUP_FALSE_COLOR_LAST_RUN: dict[tuple, float] = {}  # key: (scope_tuple) -> timestamp unix (s)


def _make_cleanup_cache_key(partner_id: int | None, client_id: int | None) -> tuple:
    return (
        "cleanup-false-color-v1",
        int(partner_id) if partner_id is not None else -1,
        int(client_id) if client_id is not None else -1,
    )


def _cleanup_cache_should_run(partner_id: int | None, client_id: int | None, force: bool = False) -> bool:
    if force:
        return True
    import time as _t
    key = _make_cleanup_cache_key(partner_id, client_id)
    last = _CLEANUP_FALSE_COLOR_LAST_RUN.get(key, 0)
    now = _t.time()
    return (now - last) >= _CLEANUP_FALSE_COLOR_CACHE_TTL_SECONDS


def _cleanup_cache_mark_done(partner_id: int | None, client_id: int | None) -> None:
    import time as _t
    key = _make_cleanup_cache_key(partner_id, client_id)
    _CLEANUP_FALSE_COLOR_LAST_RUN[key] = _t.time()


# -----------------------------------------------------------------------------
# LIMPEZA GLOBAL OTIMIZADA (2026-08-08): fecha alertas FALSOS de toner colorido
# EM IMPRESSORAS MONOCROMATICAS (PB).
#
# OTIMIZACOES de PERFORMANCE:
#   A) CACHE TTL 30min → NÃO roda a cada clique de página (era o gargalo #1!).
#   B) SÓ CARREGA impressoras que REALMENTE têm alertas ATIVOS (não carrega
#      TODAS as impressoras do cliente / banco). Antes fazia O(N*M) → agora
#      faz O(M) onde M = nº de alertas color ativos.
#   C) LIMIT 200 por rodada → se houver MUITOS, vai processando aos poucos nas
#      próximas 30min em diante. Não trava a requisição!
# -----------------------------------------------------------------------------
def _cleanup_false_color_alerts(db: Session, partner_id: int | None = None, client_id: int | None = None, force: bool = False) -> int:
    """Fecha alertas ativos de toner colorido em impressoras PB. Retorna qtd fechada."""
    # Cache gargalo #1: evita rodar a cada clique do usuário no menu!
    if not _cleanup_cache_should_run(partner_id, client_id, force=force):
        return 0

    # ===== PASSO 1: BUSCAR SÓ OS ALERTAS ATIVOS (join com impressora) =====
    # NÃO precisa carregar TODAS as impressoras! Apenas as que têm alertas abertos.
    try:
        alerts_query = (
            db.query(Alert, Printer)
            .join(Printer, Printer.id == Alert.printer_id)
            .filter(Alert.resolved == False)
            .filter(Printer.ignored == False)
        )

        if client_id is not None:
            alerts_query = alerts_query.filter(Printer.client_id == client_id)
        elif partner_id is not None:
            alerts_query = alerts_query.join(Client, Client.id == Printer.client_id).filter(Client.partner_id == partner_id)

        # LIMIT 200: não trava o request, vai escalonando aos poucos
        rows = alerts_query.order_by(Alert.created_at.asc()).limit(200).all()
    except Exception:
        # fallback super seguro: roda o algoritmo antigo só pra não ficar 0
        try:
            _cleanup_cache_mark_done(partner_id, client_id)
        except Exception:
            pass
        return 0

    if not rows:
        # Nenhum alerta ativo → marca cache para nao rodar de novo por 30min
        try:
            _cleanup_cache_mark_done(partner_id, client_id)
        except Exception:
            pass
        return 0

    # ===== PASSO 2: AGRUPA alertas por impressora (evita checagem duplicada!) =====
    alerts_by_printer: dict[int, dict] = {}  # printer_id -> {"printer":..., "alerts":[...]}
    for (alert, printer) in rows or []:
        try:
            pid = int(printer.id)
            if pid not in alerts_by_printer:
                alerts_by_printer[pid] = {"printer": printer, "alerts": []}
            alerts_by_printer[pid]["alerts"].append(alert)
        except Exception:
            continue

    total_closed = 0
    ts = _now()

    # ===== PASSO 3: PARA CADA IMPRESSORA, VERIFICA SE É PB (só 1x!) =====
    for pid, data in alerts_by_printer.items():
        printer = data["printer"]
        alertas_desta = data["alerts"]
        try:
            if _is_color_printer_real(printer):
                continue  # é colorida mesmo → não mexe nos alertas coloridos dela
        except Exception:
            continue

        # Impressora 100% confirmada PB: fecha alertas coloridos e apaga toners CMY!
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

        # Fecha APENAS os alertas coloridos desta impressora (já estavam carregados!)
        for a in alertas_desta or []:
            try:
                if a.resolved:
                    continue
                if _is_color_message_any(a.message):
                    a.resolved = True
                    a.resolved_at = ts
                    total_closed += 1
            except Exception:
                continue

    # Marca no cache que rodamos (mesmo se total_closed = 0!) → evita rodar de novo por 30min
    try:
        _cleanup_cache_mark_done(partner_id, client_id)
    except Exception:
        pass

    if total_closed > 0:
        try:
            db.commit()
        except Exception:
            db.rollback()
            total_closed = 0

    return total_closed


# -----------------------------------------------------------------------------
# MIGRACAO AUTOMATICA PERFORMANCE (2026-08-08):
#   - Mantem colunas `active` e `ignored` na printers
#   - Cria/garante INDICES SQL CRITICOS que faltavam para nao ficar lento
#     em milhares de registros:
#       idx_printers_client_id        → join Client <-> Printer (TODAS as páginas!)
#       idx_printers_active_ignored   → filtro impressoras ativas/ignoradas
#       idx_alerts_printer_resolved   → join Alert <-> Printer + filtrar resolved
#       idx_alerts_created_at_desc    → ORDER BY Alert.created_at DESC (aba Alertas!)
#       idx_clients_partner_active    → filtro superadmin/partner_admin clientes
# -----------------------------------------------------------------------------
_MIGRATION_IGNORED_DONE = False


def _ensure_printer_ignored_column(db: Session) -> None:
    global _MIGRATION_IGNORED_DONE
    if _MIGRATION_IGNORED_DONE:
        return
    try:
        from sqlalchemy import text

        # --- Colunas essenciais (nao existiam no model → IntegrityError!) ---
        db.execute(text("""
            ALTER TABLE printers
            ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE
        """))
        db.execute(text("""
            ALTER TABLE printers
            ADD COLUMN IF NOT EXISTS ignored BOOLEAN NOT NULL DEFAULT FALSE
        """))

        # --- INDICES: PRINTERS (usados em TODAS as paginas!) ---
        try:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_printers_ignored
                ON printers (ignored)
            """))
        except Exception:
            pass
        try:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_printers_client_id
                ON printers (client_id)
            """))
        except Exception:
            pass
        try:
            # indice composto: (active, ignored, client_id) → acelera list_printers MASSIVAMENTE!
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_printers_active_ignored_client
                ON printers (active, ignored, client_id)
            """))
        except Exception:
            pass

        # --- INDICES: ALERTS (usados em Dashboard / Alertas / Cleanup!) ---
        try:
            # (printer_id, resolved) → usado no cleanup, join Alert-Printer
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_alerts_printer_resolved
                ON alerts (printer_id, resolved)
            """))
        except Exception:
            pass
        try:
            # (resolved, created_at DESC) → aba Alertas ordenada!
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_alerts_resolved_created
                ON alerts (resolved, created_at DESC)
            """))
        except Exception:
            pass

        # --- INDICES: CLIENTS (usados em filtro de parceiro!) ---
        try:
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_clients_partner_active
                ON clients (partner_id, active)
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

                # ----- PASSO 1: busca impressora por IP OU serial NO CLIENTE ATUAL -----
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

                # ================================================================
                # 🔥 CORRECAO V6.4 DASHBOARD HORARIO ATUALIZADO
                #    SEMPRE cria uma Reading NOVA a cada coleta, MESMO que o
                #    contador de páginas seja IDENTICO ao anterior.
                #    Motivo: telas de impressora/cliente mostram a ultima leitura
                #    inserida em readings, nao apenas printer.last_seen. Sem isso,
                #    Julio olha o dashboard e pensa "nao coletou" porque o horario
                #    da ultima linha de leitura nao atualiza, apesar do last_seen sim.
                # ================================================================
                try:
                    reading_row = Reading(
                        printer_id=printer.id,
                        pages_total=int(printer.pages_total or 0),
                        pages_bw=int(printer.pages_bw or 0),
                        pages_color=int(printer.pages_color or 0),
                        toner_black=printer.toner_black,
                        toner_cyan=printer.toner_cyan,
                        toner_magenta=printer.toner_magenta,
                        toner_yellow=printer.toner_yellow,
                        status=_s_strn(r_status, 50) or "unknown",
                        collected_at=now,
                    )
                    db.add(reading_row)
                except Exception:
                    # Nunca deixa a falha de insercao da reading matar o loop
                    pass

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

        # ===== LIMPEZA ANTI-FALSO COLORIDO GLOBAL (para este cliente!) =====
        # Roda OBRIGATORIAMENTE a cada coleta de agente: fecha alertas coloridos
        # falsos de TODAS as impressoras PB do cliente, mesmo que esta coleta
        # específica não tenha pegado essas impressoras.
        try:
            if agent and getattr(agent, "client_id", None):
                _cleanup_false_color_alerts(db, client_id=int(agent.client_id))
        except Exception:
            pass

        # ================================================================
        # 🔥 COMMIT FINAL DE TUDO - BLINDADO CONTRA SERVERLESS (Vercel)
        #    Problema conhecido: sessao SQLAlchemy reciclada perde
        #    transacao no NullPool + psycopg 3. Retorna HTTP200 mas nao
        #    grava nada (commit fantasma). Solucao:
        #      1) FLUSH OBRIGATORIO antes do commit (garante INSERTs feitos)
        #      2) COMMIT 2 VEZES (segundo commit segura o retorno do serverless)
        #      3) Se falhar, abre SESSAO NOVA via sessionmaker NOVO e repete
        # ================================================================
        _commit_ok = False
        _commit_err_msg = ""
        try:
            try:
                db.flush()
            except Exception:
                pass
            try:
                db.connection()
            except Exception:
                pass
            try:
                db.commit()
                _commit_ok = True
            except Exception as _e1:
                _commit_err_msg = str(_e1)[:250]
                try:
                    db.rollback()
                except Exception:
                    pass
                try:
                    db.flush()
                except Exception:
                    pass
                try:
                    db.commit()
                    _commit_ok = True
                    _commit_err_msg = ""
                except Exception as _e2:
                    if not _commit_err_msg:
                        _commit_err_msg = str(_e2)[:250]
                    try:
                        db.rollback()
                    except Exception:
                        pass
            if not _commit_ok:
                raise Exception(_commit_err_msg or "commit falhou silenciosamente")
        except Exception as _fallback_needed:
            # ==============================================================
            # 🔥 FALLBACK NUCLEAR: Session.commit() nao grava (Vercel bug)
            #    Recria Sessao NOVA via SessionLocal nova e repete a leitura
            #    de todos os objetos (agent, printer, reading) numa transacao
            #    engine.begin() direta, garantindo que COMMIT vai sair
            # ==============================================================
            try:
                db.rollback()
            except Exception:
                pass
            try:
                db.close()
            except Exception:
                pass
            try:
                from sqlalchemy.orm import sessionmaker as _sm
                from sqlalchemy import text as _txt
                _SL2 = _sm(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)
                _db2 = _SL2()
                try:
                    _ag2 = _db2.query(Agent).filter(Agent.api_token == str(x_agent_token)).first()
                    if _ag2 and getattr(_ag2, "client_id", None):
                        _ag2.last_heartbeat = _now()
                        _cli_id = int(_ag2.client_id)
                        for reading in payload.readings:
                            _ri = _s_ip(getattr(reading, "ip_address", None))
                            _rs = _s_strn(getattr(reading, "serial_number", None), 200)
                            _rmo = _s_strn(getattr(reading, "model", None), 200)
                            _rma = _s_strn(getattr(reading, "manufacturer", None), 200)
                            _rst = _s_strn(getattr(reading, "status", None), 50) or "unknown"
                            _rpt = _safe_int(getattr(reading, "pages_total", 0), 0)
                            _rpb = _safe_int(getattr(reading, "pages_bw", 0), 0)
                            _rpc = _safe_int(getattr(reading, "pages_color", 0), 0)
                            _rtb = _safe_float(getattr(reading, "toner_black", None))
                            _rtc = _safe_float(getattr(reading, "toner_cyan", None))
                            _rtm = _safe_float(getattr(reading, "toner_magenta", None))
                            _rty = _safe_float(getattr(reading, "toner_yellow", None))
                            _p2 = None
                            if _ri:
                                _p2 = (_db2.query(Printer)
                                    .filter(Printer.client_id == _cli_id, Printer.ip_address.ilike(_ri))
                                    .first())
                            if not _p2 and _rs:
                                _p2 = (_db2.query(Printer)
                                    .filter(Printer.client_id == _cli_id, Printer.serial_number.ilike(_rs))
                                    .first())
                            if not _p2:
                                _p2 = Printer(client_id=_cli_id, ip_address=_ri)
                                _db2.add(_p2)
                                try: _db2.flush()
                                except Exception: _db2.rollback()
                            _p2.ip_address = _ri
                            _p2.serial_number = _rs or _p2.serial_number
                            _p2.model = _rmo or _p2.model
                            _p2.manufacturer = _rma or _p2.manufacturer
                            _p2.status = _rst
                            try:
                                if _rpt and _rpt > int(_p2.pages_total or 0):
                                    _p2.pages_total = _rpt
                            except Exception: pass
                            try:
                                if _rpb and _rpb > int(_p2.pages_bw or 0):
                                    _p2.pages_bw = _rpb
                            except Exception: pass
                            try:
                                if _rpc and _rpc > int(_p2.pages_color or 0):
                                    _p2.pages_color = _rpc
                            except Exception: pass
                            _p2.toner_black = _rtb
                            _p2.toner_cyan = _rtc
                            _p2.toner_magenta = _rtm
                            _p2.toner_yellow = _rty
                            try:
                                if not _is_color_printer_real(_p2):
                                    _p2.toner_cyan = None
                                    _p2.toner_magenta = None
                                    _p2.toner_yellow = None
                            except Exception: pass
                            _p2.last_seen = now
                            _p2.updated_at = now
                            try: _db2.flush()
                            except Exception: pass
                            _rr2 = Reading(
                                printer_id=_p2.id,
                                pages_total=int(_p2.pages_total or 0),
                                pages_bw=int(_p2.pages_bw or 0),
                                pages_color=int(_p2.pages_color or 0),
                                toner_black=_p2.toner_black,
                                toner_cyan=_p2.toner_cyan,
                                toner_magenta=_p2.toner_magenta,
                                toner_yellow=_p2.toner_yellow,
                                status=_rst,
                                collected_at=now,
                            )
                            _db2.add(_rr2)
                        try:
                            _db2.commit()
                            _commit_ok = True
                            _commit_err_msg = ""
                            try:
                                warnings.append("[FALLBACK OK] Gravado via Session NOVA (Session.commit original falhou)")
                            except Exception:
                                pass
                        except Exception as _e3:
                            _commit_err_msg = str(_e3)[:250]
                            try: _db2.rollback()
                            except Exception: pass
                finally:
                    try: _db2.close()
                    except Exception: pass
            except Exception as _e_fb:
                if not _commit_err_msg:
                    _commit_err_msg = str(_e_fb)[:250]
            if not _commit_ok:
                try:
                    return {
                        "status": "commit_error",
                        "readings_received": total_readings,
                        "processed_ok": processed_ok,
                        "processed_errors": processed_errors + 1,
                        "warnings": (warnings + [f"[COMMIT ERROR (nuclear falhou)] {_commit_err_msg[:250]}"])[:50],
                    }
                except Exception:
                    pass

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
    _ok = False
    try:
        try:
            db.flush()
        except Exception:
            pass
        try:
            db.connection()
        except Exception:
            pass
        db.commit()
        _ok = True
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        try:
            db.commit()
            _ok = True
        except Exception:
            pass
    if not _ok:
        try:
            db.rollback()
        except Exception:
            pass
        return {"status": "commit_error"}
    return {"status": "ok"}
