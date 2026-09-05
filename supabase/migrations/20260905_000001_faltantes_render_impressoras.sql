-- =====================================================================
-- MIGRACAO URGENTE: Render PostgreSQL 16
-- Adiciona colunas que podem faltar em bancos criados ANTES do update de
-- exclusao logica de impressoras (deleted_at, ignored, etc)
-- COMO USAR:
-- 1. Acesse Render -> seu servico print-collect -> aba "Shell" (SQL Shell)
--    OU use pgAdmin / DBeaver conectado ao PostgreSQL do Render
-- 2. Copie TODO esse arquivo e execute
-- 3. Depois valide: SELECT column_name FROM information_schema.columns WHERE table_name = 'printers' ORDER BY ordinal_position;
-- =====================================================================

-- 1) Garantir colunas da tabela printers (usando IF NOT EXISTS para ser idempotente)
ALTER TABLE printers ADD COLUMN IF NOT EXISTS ignored BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE printers ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE printers ADD COLUMN IF NOT EXISTS deleted_by_user_id INTEGER NULL;
ALTER TABLE printers ADD COLUMN IF NOT EXISTS delete_reason VARCHAR(200) NULL;
ALTER TABLE printers ADD COLUMN IF NOT EXISTS mac_address VARCHAR(20) NULL;

-- 2) Garantir FK deleted_by_user_id -> users.id (se existir a tabela users)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') AND
       EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'printers' AND column_name = 'deleted_by_user_id') AND
       NOT EXISTS (
           SELECT 1 FROM information_schema.table_constraints tc
           JOIN information_schema.key_column_usage kcu
             ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
           WHERE tc.constraint_type = 'FOREIGN KEY'
             AND tc.table_name = 'printers'
             AND kcu.column_name = 'deleted_by_user_id'
       ) THEN
        BEGIN
            ALTER TABLE printers
                ADD CONSTRAINT fk_printers_deleted_by_user_id
                FOREIGN KEY (deleted_by_user_id) REFERENCES users(id)
                ON DELETE SET NULL;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'FK deleted_by_user_id ja existe ou erro: %', SQLERRM;
        END;
    END IF;
END $$;

-- 3) Garantir valores default corretos para colunas boolean (caso linhas existentes tenham NULL)
UPDATE printers SET ignored = FALSE WHERE ignored IS NULL;
UPDATE printers SET active  = TRUE  WHERE active  IS NULL;

-- 4) Garantir indice UNIQUE em serial_number (nao-nulos) e indice em ignored
CREATE UNIQUE INDEX IF NOT EXISTS uq_printers_serial_number_nonnull
    ON printers(serial_number) WHERE serial_number IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_printers_ignored     ON printers(ignored);
CREATE INDEX IF NOT EXISTS ix_printers_active      ON printers(active);
CREATE INDEX IF NOT EXISTS ix_printers_serial      ON printers(serial_number);
CREATE INDEX IF NOT EXISTS ix_printers_client_id   ON printers(client_id);
CREATE INDEX IF NOT EXISTS ix_printers_location_id ON printers(location_id);

-- 5) Colunas que podem faltar em users (multitenancy precoce)
ALTER TABLE users    ADD COLUMN IF NOT EXISTS role       VARCHAR(50) DEFAULT 'superadmin';
ALTER TABLE users    ADD COLUMN IF NOT EXISTS client_id  INTEGER NULL;
ALTER TABLE users    ADD COLUMN IF NOT EXISTS partner_id INTEGER NULL;
UPDATE users SET role = 'superadmin' WHERE role IS NULL;

-- 6) Colunas que podem faltar em clients / partners
ALTER TABLE clients  ADD COLUMN IF NOT EXISTS partner_id  INTEGER NULL;
ALTER TABLE clients  ADD COLUMN IF NOT EXISTS client_code VARCHAR(16) NULL;
ALTER TABLE partners ADD COLUMN IF NOT EXISTS logo_url    VARCHAR(500) NULL;
ALTER TABLE partners ADD COLUMN IF NOT EXISTS logo_data   TEXT NULL;
ALTER TABLE agents   ADD COLUMN IF NOT EXISTS hostname            VARCHAR(200) NULL;
ALTER TABLE agents   ADD COLUMN IF NOT EXISTS remote_ip           VARCHAR(45)  NULL;
ALTER TABLE agents   ADD COLUMN IF NOT EXISTS pairing_code        VARCHAR(16)  NULL;
ALTER TABLE agents   ADD COLUMN IF NOT EXISTS pairing_expires_at  TIMESTAMP WITH TIME ZONE NULL;
ALTER TABLE agents   ADD COLUMN IF NOT EXISTS paired_at           TIMESTAMP WITH TIME ZONE NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ix_clients_client_code
    ON clients(client_code) WHERE client_code IS NOT NULL;

-- 7) Indices da tabela historico_coletas (performance)
CREATE INDEX IF NOT EXISTS ix_historico_coletas_data_registro ON historico_coletas(data_registro);
CREATE INDEX IF NOT EXISTS ix_historico_coletas_printer_id    ON historico_coletas(printer_id);
CREATE INDEX IF NOT EXISTS ix_historico_coletas_cliente_id    ON historico_coletas(cliente_id);
CREATE INDEX IF NOT EXISTS ix_historico_coletas_ip_impressora ON historico_coletas(ip_impressora);
CREATE INDEX IF NOT EXISTS ix_historico_coletas_status_coleta ON historico_coletas(status_coleta);
CREATE INDEX IF NOT EXISTS ix_historico_coletas_tipo_contador ON historico_coletas(tipo_contador);
