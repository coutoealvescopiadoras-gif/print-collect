-- Print Collect - schema para Supabase (PostgreSQL)
-- Execute no Supabase: SQL Editor > New query > Run

-- Clientes (empresas que alugam impressoras)
CREATE TABLE IF NOT EXISTS clients (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(200) NOT NULL,
    cnpj          VARCHAR(20) UNIQUE,
    contact_name  VARCHAR(200),
    contact_email VARCHAR(200),
    contact_phone VARCHAR(50),
    address       TEXT,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Locais dentro de cada cliente
CREATE TABLE IF NOT EXISTS locations (
    id          SERIAL PRIMARY KEY,
    client_id   INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name        VARCHAR(200) NOT NULL,
    sector      VARCHAR(200),
    responsible VARCHAR(200),
    address     TEXT
);

CREATE INDEX IF NOT EXISTS idx_locations_client ON locations(client_id);

-- Impressoras
CREATE TABLE IF NOT EXISTS printers (
    id            SERIAL PRIMARY KEY,
    client_id     INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    location_id   INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    ip_address    VARCHAR(45) NOT NULL,
    mac_address   VARCHAR(20),
    serial_number VARCHAR(100),
    model         VARCHAR(200),
    manufacturer  VARCHAR(100),
    status        VARCHAR(50) NOT NULL DEFAULT 'unknown',
    pages_total   INTEGER NOT NULL DEFAULT 0,
    pages_bw      INTEGER NOT NULL DEFAULT 0,
    pages_color   INTEGER NOT NULL DEFAULT 0,
    toner_black   DOUBLE PRECISION,
    toner_cyan    DOUBLE PRECISION,
    toner_magenta DOUBLE PRECISION,
    toner_yellow  DOUBLE PRECISION,
    last_seen     TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_printers_client ON printers(client_id);
CREATE INDEX IF NOT EXISTS idx_printers_serial ON printers(serial_number);
CREATE UNIQUE INDEX IF NOT EXISTS idx_printers_client_ip ON printers(client_id, ip_address);

-- Historico de leituras (contadores e toner ao longo do tempo)
CREATE TABLE IF NOT EXISTS readings (
    id            SERIAL PRIMARY KEY,
    printer_id    INTEGER NOT NULL REFERENCES printers(id) ON DELETE CASCADE,
    pages_total   INTEGER NOT NULL DEFAULT 0,
    pages_bw      INTEGER NOT NULL DEFAULT 0,
    pages_color   INTEGER NOT NULL DEFAULT 0,
    toner_black   DOUBLE PRECISION,
    toner_cyan    DOUBLE PRECISION,
    toner_magenta DOUBLE PRECISION,
    toner_yellow  DOUBLE PRECISION,
    status        VARCHAR(50) NOT NULL DEFAULT 'online',
    collected_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_readings_printer ON readings(printer_id);
CREATE INDEX IF NOT EXISTS idx_readings_collected ON readings(collected_at DESC);

-- Alertas (toner baixo, offline, etc.)
CREATE TABLE IF NOT EXISTS alerts (
    id          SERIAL PRIMARY KEY,
    printer_id  INTEGER NOT NULL REFERENCES printers(id) ON DELETE CASCADE,
    alert_type  VARCHAR(100) NOT NULL,
    message     TEXT NOT NULL,
    severity    VARCHAR(20) NOT NULL DEFAULT 'warning',
    resolved    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_alerts_printer ON alerts(printer_id);
CREATE INDEX IF NOT EXISTS idx_alerts_open ON alerts(resolved) WHERE resolved = FALSE;

-- Agentes instalados nos clientes
CREATE TABLE IF NOT EXISTS agents (
    id             SERIAL PRIMARY KEY,
    client_id      INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    name           VARCHAR(200) NOT NULL,
    api_token      VARCHAR(100) NOT NULL UNIQUE,
    last_heartbeat TIMESTAMPTZ,
    version        VARCHAR(50),
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agents_client ON agents(client_id);
CREATE INDEX IF NOT EXISTS idx_agents_token ON agents(api_token);

-- Dados de demonstracao (opcional - remova em producao)
INSERT INTO clients (name, cnpj, contact_name, contact_email, contact_phone, address)
SELECT
    'Empresa Exemplo Ltda',
    '12.345.678/0001-90',
    'Joao Silva',
    'joao@empresa.com',
    '(11) 99999-0000',
    'Av. Paulista, 1000 - Sao Paulo/SP'
WHERE NOT EXISTS (
    SELECT 1 FROM clients WHERE cnpj = '12.345.678/0001-90'
);

INSERT INTO locations (client_id, name, sector, responsible)
SELECT
    c.id,
    'Matriz',
    'Administrativo',
    'Maria Santos'
FROM clients c
WHERE c.cnpj = '12.345.678/0001-90'
  AND NOT EXISTS (
    SELECT 1 FROM locations l WHERE l.client_id = c.id AND l.name = 'Matriz'
  );

INSERT INTO printers (
    client_id,
    location_id,
    ip_address,
    serial_number,
    model,
    manufacturer,
    status,
    pages_total,
    pages_bw,
    toner_black,
    last_seen
)
SELECT
    c.id,
    l.id,
    '192.168.1.100',
    'DEMO001',
    'HP LaserJet Pro M404dn',
    'HP',
    'online',
    15420,
    15420,
    45.0,
    NOW()
FROM clients c
INNER JOIN locations l ON l.client_id = c.id AND l.name = 'Matriz'
WHERE c.cnpj = '12.345.678/0001-90'
  AND NOT EXISTS (
    SELECT 1 FROM printers p WHERE p.client_id = c.id AND p.ip_address = '192.168.1.100'
  );

INSERT INTO agents (client_id, name, api_token)
SELECT
    c.id,
    'Agente Matriz',
    'agent-dev-key'
FROM clients c
WHERE c.cnpj = '12.345.678/0001-90'
  AND NOT EXISTS (
    SELECT 1 FROM agents a WHERE a.api_token = 'agent-dev-key'
  );
