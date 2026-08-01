import requests
import sys

BASE_URL = "http://localhost:8000"

print("🔍 Testando login na API...")
print(f"1. Fazendo login com admin/admin123...")

# Testar login
login_response = requests.post(
    f"{BASE_URL}/api/token",
    data={"username": "admin", "password": "admin123"}
)

print(f"   Status: {login_response.status_code}")
if login_response.status_code != 200:
    print(f"❌ Erro no login! {login_response.text}")
    sys.exit(1)

token_data = login_response.json()
token = token_data.get("access_token")
print(f"✅ Login realizado com sucesso! Token obtido: {token[:20]}...")

print(f"\n2. Testando /api/users/me com o token...")
me_response = requests.get(
    f"{BASE_URL}/api/users/me",
    headers={"Authorization": f"Bearer {token}"}
)

print(f"   Status: {me_response.status_code}")
if me_response.status_code != 200:
    print(f"❌ Erro ao acessar dados do usuário! {me_response.text}")
    sys.exit(1)

user_data = me_response.json()
print(f"✅ Dados do usuário obtidos com sucesso!")
print(f"   ID: {user_data['id']}")
print(f"   Username: {user_data['username']}")
print(f"   Email: {user_data['email']}")
print(f"   Active: {user_data['active']}")
print(f"   Created At: {user_data['created_at']}")

print("\n🎉 Tudo funcionando perfeitamente!")
