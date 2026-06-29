from app.config import settings
from app.database import User, SessionLocal
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_admin_user():
    db = SessionLocal()
    try:
        # Verifica se o usuário admin já existe
        existing_admin = db.query(User).filter(User.username == "admin").first()
        if existing_admin:
            print("Usuário admin já existe!")
            return

        # Cria o usuário admin com senha admin123
        hashed_password = pwd_context.hash("admin123")
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
