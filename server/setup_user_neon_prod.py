import os
import sys
import ssl
from pathlib import Path

SERVER_DIR = Path(__file__).parent
sys.path.insert(0, str(SERVER_DIR))

# 1) ANTES de importar app.database, engana o modulo dummy para NAO crashar
#    (nao usaremos esse engine dummy para NADA!)
os.environ["DATABASE_URL"] = "sqlite:///./dummy_temp_ignore.db"

# 2) Agora sim importa os modelos (Base e User sao necessarios)
from app.database import Base, User  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
import bcrypt  # noqa: E402


def hash_password(plain_password: str) -> str:
    plain = plain_password.encode("utf-8")[:72]
    return bcrypt.hashpw(plain, bcrypt.gensalt()).decode("utf-8")


# 3) Dados do banco Neon producao (Sao Paulo)
PG_USER = "neondb_owner"
PG_PASS = "npg_U9JHqTsc3LPu"
PG_HOST = "ep-round-base-ac7ofzqr.sa-east-1.aws.neon.tech"
PG_DB = "neondb"
URL_NO_PARAMS = (
    f"postgresql+pg8000://{PG_USER}:{PG_PASS}@{PG_HOST}:5432/{PG_DB}"
)

# pg8000 usa ssl_context em vez de sslmode=require. create_default_context()
# ja faz validacao de certificado = mesmo que sslmode=verify-ca, melhor ainda.
ssl_ctx = ssl.create_default_context()

print("[DEBUG] Criando engine para Neon PostgreSQL (pg8000 pure-python)...")
engine = create_engine(
    URL_NO_PARAMS,
    connect_args={"ssl_context": ssl_ctx},
    pool_pre_ping=True,
)

# 4) Testa conexao antes de qualquer coisa
print("[DEBUG] Conectando (SELECT 1)...")
with engine.connect() as conn:
    r = conn.execute(text("SELECT current_database(), inet_server_addr()")).fetchone()
    print(f"[OK] conectado! database={r[0]}, server_ip={r[1]}")
    r2 = conn.execute(text("SELECT version()")).scalar()
    print(f"[INFO] PostgreSQL: {r2[:80]}")

# 5) Cria todas as tabelas (partners, clients, locations, printers, alerts,
#    agents, readings, users) se NAO existirem
print("\n[INFO] Rodando create_all (tabelas)...")
Base.metadata.create_all(bind=engine)
print("[OK] Tabelas garantidas.")

# 6) Cria / atualiza usuario Julio
TARGET_EMAIL = "julio@ceacopiadoras.com.br"
TARGET_PASSWORD = "admin123"

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()
try:
    print("\n" + "=" * 60)
    print("VERIFICACAO E CRIACAO DE USUARIO - PRODUCAO NEON SP")
    print("=" * 60)

    users = db.query(User).all()
    print(f"\nTotal de usuarios no banco: {len(users)}")
    for u in users:
        print(
            f"  [{u.id}] username={u.username} | email={u.email} | "
            f"role={u.role} | active={u.active}"
        )

    existing = db.query(User).filter(User.email == TARGET_EMAIL).first()

    if existing:
        print(f"\n[OK] Usuario {TARGET_EMAIL} JA EXISTE (ID={existing.id})")
        print(f"   username: {existing.username}")
        print(f"   role: {existing.role}")
        print(f"   active: {existing.active}")
        print("\n   Atualizando senha para 'admin123' para garantir...")
        existing.hashed_password = hash_password(TARGET_PASSWORD)
        db.commit()
        print("   [OK] Senha atualizada com sucesso!")
    else:
        print(f"\n[WARN] Usuario {TARGET_EMAIL} NAO EXISTE")
        print("   Criando usuario com senha 'admin123'...")
        hashed = hash_password(TARGET_PASSWORD)
        new_user = User(
            username=TARGET_EMAIL.lower(),
            email=TARGET_EMAIL.lower(),
            hashed_password=hashed,
            role="superadmin",
            client_id=None,
            partner_id=None,
            active=True,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        print(f"\n[OK] Usuario criado com sucesso! (ID={new_user.id})")
        print(f"   username: {new_user.username}")
        print(f"   email: {new_user.email}")
        print(f"   role: {new_user.role}")

    print("\n" + "=" * 60)
    print("LOGIN DE PRODUCAO (Vercel):  https://print-collect.vercel.app/")
    print(f"  Email : {TARGET_EMAIL}")
    print(f"  Senha : {TARGET_PASSWORD}")
    print("=" * 60)

finally:
    db.close()
