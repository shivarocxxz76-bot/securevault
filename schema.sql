-- =============================================================
-- SecureVault — Full PostgreSQL Schema
-- Run once against your database: psql -d securevault -f schema.sql
-- =============================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================
-- MODULE 1 — USER AUTHENTICATION
-- =============================================================

CREATE TABLE IF NOT EXISTS roles (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(50) UNIQUE NOT NULL,
    description TEXT
);

INSERT INTO roles (name, description) VALUES
    ('admin', 'Full system access'),
    ('user',  'Standard access')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS users (
    id                     SERIAL PRIMARY KEY,
    username               VARCHAR(80)  UNIQUE NOT NULL,
    email                  VARCHAR(255) UNIQUE NOT NULL,
    password_hash          VARCHAR(255) NOT NULL,              -- bcrypt
    role_id                INTEGER NOT NULL DEFAULT 2 REFERENCES roles(id) ON DELETE RESTRICT,
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    storage_limit_bytes    BIGINT  NOT NULL DEFAULT 1073741824, -- 1 GB
    storage_used_bytes     BIGINT  NOT NULL DEFAULT 0,
    current_plan           VARCHAR(50) NOT NULL DEFAULT 'free',
    failed_login_attempts  SMALLINT NOT NULL DEFAULT 0,
    locked_until           TIMESTAMP WITH TIME ZONE,
    last_login             TIMESTAMP WITH TIME ZONE,
    created_at             TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email    ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE TABLE IF NOT EXISTS user_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ip_address  INET,
    user_agent  TEXT,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    is_revoked  BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) NOT NULL,
    expires_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at     TIMESTAMP WITH TIME ZONE,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- =============================================================
-- MODULE 2 — FILE MANAGEMENT
-- =============================================================

CREATE TABLE IF NOT EXISTS files (
    id              SERIAL PRIMARY KEY,
    owner_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    folder_id       INTEGER,                                   -- FK added after folders table
    original_name   VARCHAR(255) NOT NULL,
    stored_name     VARCHAR(255) NOT NULL UNIQUE,              -- UUID filename on disk
    mime_type       VARCHAR(100),
    size_bytes      BIGINT NOT NULL DEFAULT 0,
    is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,            -- soft delete (recycle bin)
    deleted_at      TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_files_owner   ON files(owner_id);
CREATE INDEX IF NOT EXISTS idx_files_folder  ON files(folder_id);
CREATE INDEX IF NOT EXISTS idx_files_deleted ON files(is_deleted);

-- =============================================================
-- MODULE 3 — FOLDER MANAGEMENT
-- =============================================================

CREATE TABLE IF NOT EXISTS folders (
    id          SERIAL PRIMARY KEY,
    owner_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parent_id   INTEGER REFERENCES folders(id) ON DELETE CASCADE,  -- NULL = root
    name        VARCHAR(255) NOT NULL,
    is_deleted  BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at  TIMESTAMP WITH TIME ZONE,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(owner_id, parent_id, name)   -- no duplicate names in same location
);
CREATE INDEX IF NOT EXISTS idx_folders_owner  ON folders(owner_id);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);

-- Now add FK from files -> folders
ALTER TABLE files
    ADD CONSTRAINT fk_files_folder
    FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE SET NULL;

-- =============================================================
-- MODULE 4 — FILE & FOLDER SHARING
-- =============================================================

CREATE TABLE IF NOT EXISTS file_shares (
    id              SERIAL PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    shared_by       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    shared_with     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission      VARCHAR(20) NOT NULL DEFAULT 'view',       -- 'view' | 'download'
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(file_id, shared_with)
);
CREATE INDEX IF NOT EXISTS idx_file_shares_with ON file_shares(shared_with);
CREATE INDEX IF NOT EXISTS idx_file_shares_file ON file_shares(file_id);

CREATE TABLE IF NOT EXISTS folder_shares (
    id              SERIAL PRIMARY KEY,
    folder_id       INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
    shared_by       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    shared_with     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission      VARCHAR(20) NOT NULL DEFAULT 'view',
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(folder_id, shared_with)
);
CREATE INDEX IF NOT EXISTS idx_folder_shares_with ON folder_shares(shared_with);

-- =============================================================
-- MODULE 5 — STORAGE PLANS & DEMO PAYMENT
-- =============================================================

CREATE TABLE IF NOT EXISTS plans (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(50) UNIQUE NOT NULL,               -- 'free','basic','pro','enterprise'
    storage_bytes   BIGINT NOT NULL,
    price_usd       NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    description     TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO plans (name, storage_bytes, price_usd, description) VALUES
    ('free',       1073741824,    0.00, '1 GB storage — Free forever'),
    ('basic',      10737418240,   4.99, '10 GB storage — Perfect for individuals'),
    ('pro',        53687091200,  12.99, '50 GB storage — For power users'),
    ('enterprise', 214748364800, 29.99, '200 GB storage — For teams and businesses')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS payments (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id         INTEGER NOT NULL REFERENCES plans(id),
    amount_usd      NUMERIC(10,2) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',    -- 'pending','completed','failed'
    transaction_ref VARCHAR(100),                              -- fake reference for demo
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);

-- =============================================================
-- MODULE 6 — RECYCLE BIN (uses is_deleted + deleted_at on files/folders)
-- No extra table needed — soft-delete columns already on files and folders
-- =============================================================

-- =============================================================
-- MODULE 7 — NOTIFICATIONS & SUPPORT
-- =============================================================

CREATE TABLE IF NOT EXISTS notifications (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type        VARCHAR(50) NOT NULL,                          -- 'share','system','payment'
    message     TEXT NOT NULL,
    is_read     BOOLEAN NOT NULL DEFAULT FALSE,
    link        VARCHAR(500),                                  -- optional deep-link URL
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_notif_user   ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notif_unread ON notifications(user_id, is_read);

CREATE TABLE IF NOT EXISTS support_tickets (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject         VARCHAR(255) NOT NULL,
    message         TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'open',       -- 'open','in_progress','closed'
    priority        VARCHAR(20) NOT NULL DEFAULT 'normal',     -- 'low','normal','high'
    admin_reply     TEXT,
    replied_by      INTEGER REFERENCES users(id),
    replied_at      TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tickets_user   ON support_tickets(user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status);

-- =============================================================
-- MODULE 8 — ACTIVITY LOGS (admin monitoring)
-- =============================================================

CREATE TABLE IF NOT EXISTS activity_logs (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(100) NOT NULL,                         -- e.g. 'upload','login','share'
    target_type VARCHAR(50),                                   -- 'file','folder','user', etc.
    target_id   INTEGER,
    details     TEXT,
    ip_address  INET,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_logs_user   ON activity_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_action ON activity_logs(action);
CREATE INDEX IF NOT EXISTS idx_logs_time   ON activity_logs(created_at DESC);

-- =============================================================
-- TRIGGERS — auto-update updated_at
-- =============================================================

CREATE OR REPLACE FUNCTION fn_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['users','files','folders','support_tickets'] LOOP
    EXECUTE format(
      'DROP TRIGGER IF EXISTS trg_%1$s_updated ON %1$s;
       CREATE TRIGGER trg_%1$s_updated
         BEFORE UPDATE ON %1$s
         FOR EACH ROW EXECUTE FUNCTION fn_updated_at();', t);
  END LOOP;
END;
$$;
