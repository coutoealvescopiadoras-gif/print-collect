from app.database import SessionLocal, User, init_db
from app.config import settings
from passlib.context import CryptContext
import sys

# Testar conexão com banco de dados
try:
    print("🔍 Iniciando diagnóstico do sistema Print Collect...")
    db = SessionLocal()
    print("✅ Conexão com banco de dados OK!")
    
    # Verificar se o usuário admin existe
    user = db.query(User).filter(User.username == "admin").first()
    if user:
        print(f"✅ Usuário admin existe no banco! ID: {user.id}")
        print(f"   Username: {user.username}")
        print(f"   Hashed password presente: {bool(user.hashed_password is not None)}")
    else:
        print("❌ Usuário admin NÃO existe! Vamos criar...")
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed_password = pwd_context.hash("admin123")
        admin_user = User(username="admin", hashed_password=hashed_password)
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        print(f"✅ Usuário admin criado com sucesso! ID: {admin_user.id}")
    
    db.close()
    
    print("✅ Diagnóstico completo!")

except Exception as e:
    print(f"❌ Erro durante diagnóstico: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
