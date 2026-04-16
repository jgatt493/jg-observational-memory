"""Database layer for observational memory — SQLite."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone

DATA_DIR = os.path.expanduser("~/.observational-memory")
DB_PATH = os.path.join(DATA_DIR, "memory.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    session_id TEXT NOT NULL,
    project TEXT NOT NULL,
    scope TEXT NOT NULL CHECK (scope IN ('global', 'project')),
    type TEXT NOT NULL CHECK (type IN ('preference', 'correction', 'pattern', 'decision')),
    content TEXT NOT NULL,
    durability TEXT CHECK (durability IN ('durable', 'contextual', 'incident')),
    trigger_summary TEXT
);

CREATE TABLE IF NOT EXISTS interaction_styles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
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

CREATE TABLE IF NOT EXISTS observed_sessions (
    session_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    had_observations INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reflections (
    slug TEXT PRIMARY KEY,
    prose TEXT NOT NULL,
    char_count INTEGER NOT NULL DEFAULT 0,
    observation_count INTEGER NOT NULL DEFAULT 0,
    last_observation_id INTEGER NOT NULL DEFAULT 0,
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    context_prose TEXT
);

CREATE INDEX IF NOT EXISTS idx_observations_project ON observations(project);
CREATE INDEX IF NOT EXISTS idx_observations_scope ON observations(scope);
CREATE INDEX IF NOT EXISTS idx_observations_type ON observations(type);
CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_styles_project ON interaction_styles(project);
CREATE INDEX IF NOT EXISTS idx_styles_domain ON interaction_styles(domain);
CREATE INDEX IF NOT EXISTS idx_styles_session ON interaction_styles(session_id);
CREATE INDEX IF NOT EXISTS idx_observed_sessions_project ON observed_sessions(project);
CREATE INDEX IF NOT EXISTS idx_observations_durability ON observations(durability);
"""


def init_db():
    """Create the database and tables if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    conn.close()


def get_connection() -> sqlite3.Connection:
    """Get a connection to the SQLite database. Lazily creates DB if needed."""
    if not os.path.exists(DB_PATH):
        init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def insert_observations(observations: list[dict], session_id: str, project: str):
    """Insert observation records into SQLite."""
    if not observations:
        return
    conn = get_connection()
    try:
        ts = datetime.now(timezone.utc).isoformat()
        for obs in observations:
            conn.execute(
                """INSERT INTO observations (ts, session_id, project, scope, type, content, durability, trigger_summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, session_id, project, obs["scope"], obs["type"], obs["content"],
                 obs.get("durability"), obs.get("trigger")),
            )
        conn.commit()
    finally:
        conn.close()


def insert_interaction_style(style: dict, session_id: str, project: str):
    """Insert an interaction style record into SQLite."""
    if not style:
        return
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO interaction_styles
               (ts, session_id, project, domain, expert, inquisitive, architectural,
                precise, scope_aware, risk_conscious, ai_led)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).isoformat(),
                session_id,
                project,
                style.get("domain", "unknown"),
                style.get("expert", 0),
                style.get("inquisitive", 0),
                style.get("architectural", 0),
                style.get("precise", 0),
                style.get("scope_aware", 0),
                style.get("risk_conscious", 0),
                style.get("ai_led", 0),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def mark_session_observed(session_id: str, project: str, had_observations: bool):
    """Record that a session has been processed."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO observed_sessions (session_id, project, ts, had_observations)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (session_id) DO NOTHING""",
            (session_id, project, datetime.now(timezone.utc).isoformat(), int(had_observations)),
        )
        conn.commit()
    finally:
        conn.close()


def is_session_observed(session_id: str) -> bool:
    """Check if a session has already been attempted."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM observed_sessions WHERE session_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_observations_for_project(project: str) -> list[dict]:
    """Get all observations for a project."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT scope, type, content, durability, trigger_summary FROM observations WHERE project = ? ORDER BY ts",
            (project,),
        ).fetchall()
        return [{"scope": r[0], "type": r[1], "content": r[2], "durability": r[3], "trigger_summary": r[4]} for r in rows]
    finally:
        conn.close()


def get_global_observations() -> list[dict]:
    """Get all global-scoped observations across all projects."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT scope, type, content, durability, trigger_summary FROM observations WHERE scope = 'global' ORDER BY ts",
        ).fetchall()
        return [{"scope": r[0], "type": r[1], "content": r[2], "durability": r[3], "trigger_summary": r[4]} for r in rows]
    finally:
        conn.close()


def get_all_projects() -> list[str]:
    """Get all project slugs that have observations."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT DISTINCT project FROM observations ORDER BY project"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def upsert_reflection(slug: str, prose: str, observation_count: int, last_observation_id: int, context_prose: str | None = None):
    """Store or update the synthesized prose for a project/global slug."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO reflections (slug, prose, char_count, observation_count, last_observation_id, ts, context_prose)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (slug) DO UPDATE SET
                 prose = EXCLUDED.prose,
                 char_count = EXCLUDED.char_count,
                 observation_count = EXCLUDED.observation_count,
                 last_observation_id = EXCLUDED.last_observation_id,
                 ts = EXCLUDED.ts,
                 context_prose = EXCLUDED.context_prose""",
            (slug, prose, len(prose), observation_count, last_observation_id, datetime.now(timezone.utc).isoformat(), context_prose),
        )
        conn.commit()
    finally:
        conn.close()


def has_reflection(slug: str) -> bool:
    """Check if a reflection exists for a slug."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM reflections WHERE slug = ? LIMIT 1", (slug,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_unprocessed_count(slug: str) -> int:
    """Count observations newer than the last reflection for a slug."""
    conn = get_connection()
    try:
        if slug == "global":
            row = conn.execute(
                """SELECT COUNT(*) FROM observations
                   WHERE scope = 'global'
                   AND id > (SELECT COALESCE(MAX(last_observation_id), 0) FROM reflections WHERE slug = 'global')""",
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT COUNT(*) FROM observations
                   WHERE project = ?
                   AND id > (SELECT COALESCE(MAX(last_observation_id), 0) FROM reflections WHERE slug = ?)""",
                (slug, slug),
            ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()
