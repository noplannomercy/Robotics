-- schema.sql
-- Reverse-Doc Service DB schema (rdoc_ prefix)

CREATE TABLE IF NOT EXISTS rdoc_job (
    job_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_type   TEXT NOT NULL,
    file_name    TEXT NOT NULL,
    file_size    BIGINT,
    source_hash  TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'queued',
    result       TEXT,
    error        TEXT,
    attempts     INT NOT NULL DEFAULT 0,
    callback_url TEXT,
    requested_by TEXT,
    created_at   TIMESTAMPTZ DEFAULT now(),
    started_at   TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rdoc_job_source_hash ON rdoc_job(source_hash);
CREATE INDEX IF NOT EXISTS idx_rdoc_job_status ON rdoc_job(status);
CREATE INDEX IF NOT EXISTS idx_rdoc_job_created ON rdoc_job(created_at DESC);

CREATE TABLE IF NOT EXISTS rdoc_prompt (
    id          SERIAL PRIMARY KEY,
    asset_type  TEXT NOT NULL,
    version     INT NOT NULL,
    text        TEXT NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rdoc_prompt_active
    ON rdoc_prompt(asset_type) WHERE is_active = TRUE;
