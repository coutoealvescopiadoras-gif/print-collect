from app.config import settings
from app.database import User, SessionLocal, init_db
import bcrypt


def hash_password(plain_password: str) -> str:
    plain = plain_password.encode("utf-8")[:72]
    return bcrypt.hashpw(plain, bcrypt.gensalt()).decode("utf-8")


def create_admin_user():
    init_db()
    db = SessionLocal()
    try:
        existing_admin = db.query(User).filter(User.username == "admin").first()
        if existing_admin:
            print("Usuário admin já existe!")
            return

        hashed_password = hash_password("admin123")
        admin_user = User(
            username="admin",
            email="admin@printcollect.com.br",
            hashed_password=hashed_password,
            active=True,
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        print(f"Usuário admin criado com sucesso! (ID: {admin_user.id})")
        print("Login: admin / admin123")
    finally:
        db.close()


if __name__ == "__main__":
    create_admin_user()
