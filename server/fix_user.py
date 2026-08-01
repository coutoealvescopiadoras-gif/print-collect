from app.database import SessionLocal, User
from app.config import settings
from passlib.context import CryptContext

# Testar conexão com banco de dados
try:
    print("🔍 Verificando usuário admin no banco...")
    db = SessionLocal()
    
    # Verificar se o usuário admin existe
    user = db.query(User).filter(User.username == "admin").first()
    if user:
        print(f"✅ Usuário admin encontrado!")
        print(f"  ID: {user.id}")
        print(f"  Username: {user.username}")
        print(f"  Email: {user.email}")
        print(f"  Active: {user.active}")
        
        # Se o email estiver vazio ou None, definimos um email padrão
        if not user.email:
            print("\n⚠️ Email do usuário admin está faltando! Vamos corrigir...")
            user.email = "admin@ca-solucoes.com.br"
            db.commit()
            print("✅ Email atualizado com sucesso!")
        
    else:
        print("❌ Usuário admin não encontrado! Vamos criar...")
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        hashed_password = pwd_context.hash("admin123")
        admin_user = User(
            username="admin",
            email="admin@ca-solucoes.com.br",
            hashed_password=hashed_password
        )
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        print(f"✅ Usuário admin criado com sucesso! ID: {admin_user.id}")
    
    db.close()
    
    print("\n✅ Verificação concluída!")

except Exception as e:
    print(f"❌ Erro: {e}")
    import traceback
    traceback.print_exc()
