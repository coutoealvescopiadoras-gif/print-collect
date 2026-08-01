import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import User, SessionLocal, init_db
import bcrypt

def hash_password(plain_password: str) -> str:
    plain = plain_password.encode("utf-8")[:72]
    return bcrypt.hashpw(plain, bcrypt.gensalt()).decode("utf-8")


TARGET_EMAIL = "julio@ceacopiadoras.com.br"
TARGET_PASSWORD = "admin123"

init_db()
db = SessionLocal()
try:
    print("=" * 60)
    print("VERIFICACAO E CRIACAO DE USUARIO")
    print("=" * 60)

    users = db.query(User).all()
    print(f"\nTotal de usuarios no banco: {len(users)}")
    for u in users:
        print(f"  [{u.id}] username={u.username} | email={u.email} | role={u.role} | active={u.active}")

    existing = db.query(User).filter(User.email == TARGET_EMAIL).first()

    if existing:
        print(f"\n[OK] Usuario {TARGET_EMAIL} JA EXISTE (ID={existing.id})")
        print(f"   username: {existing.username}")
        print(f"   role: {existing.role}")
        print(f"   active: {existing.active}")
        print("\n   Atualizando senha para 'admin123' para o teste...")
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
    print("DADOS PARA TESTE DE LOGIN:")
    print(f"  Email: {TARGET_EMAIL}")
    print(f"  Senha: {TARGET_PASSWORD}")
    print("=" * 60)

finally:
    db.close()
