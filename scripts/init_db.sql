-- Initialize the om_memory database schema.
-- Run: psql -U jg -d om_memory -f scripts/init_db.sql
-- Or:  docker exec local_db psql -U jg -d om_memory -f /scripts/init_db.sql

CREATE TABLE IF NOT EXISTS observations (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id TEXT NOT NULL,
    project TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('global', 'project')),
    type TEXT NOT NULL CHECK (type IN ('preference', 'correction', 'pattern', 'decision')),
    content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interaction_styles (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    session_id TEXT NOT NULL,
    project TEXT NOT NULL,
    domain TEXT NOT NULL,
    expert REAL NOT NULL DEFAULT 0,
    inquisitive REAL NOT NULL DEFAULT 0,
    architectural REAL NOT NULL DEFAULT 0,
    precise REAL NOT NULL DEFAULT 0,
    scope_aware REAL NOT NULL DEFAULT 0,
    risk_conscious REAL NOT NULL DEFAULT 0,
    ai_led REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_observations_project ON observations(project);
CREATE INDEX IF NOT EXISTS idx_observations_scope ON observations(scope);
CREATE INDEX IF NOT EXISTS idx_observations_type ON observations(type);
CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_styles_project ON interaction_styles(project);
CREATE INDEX IF NOT EXISTS idx_styles_domain ON interaction_styles(domain);
CREATE INDEX IF NOT EXISTS idx_styles_session ON interaction_styles(session_id);
