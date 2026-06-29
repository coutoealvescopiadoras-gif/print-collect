-- Adiciona tabela de usuarios para autenticacao
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(200) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Cria usuario admin padrao (senha: admin123)
-- Nota: Em producao, altere a senha imediatamente!
INSERT INTO users (username, email, hashed_password)
SELECT 
    'admin', 
    'admin@printcollect.com', 
    '$2b$12$XTXwCTcJ6eJXb0UZWKp8ZuX2apZDP9/x415oX/vuI7c6LU0hSRdNm'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'admin');
