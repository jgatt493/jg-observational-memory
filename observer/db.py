"""Database layer for observational memory — writes to Postgres."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import psycopg2

DB_HOST = os.environ.get("OM_DB_HOST", "localhost")
DB_PORT = os.environ.get("OM_DB_PORT", "5432")
DB_NAME = os.environ.get("JG_MEMORY_DB_NAME", "om_memory")
DB_USER = os.environ.get("OM_DB_USER")
DB_PASS = os.environ.get("JG_MEMORY_DB_PASS", "REDACTED")


def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
    )


def insert_observations(observations: list[dict], session_id: str, project: str):
    """Insert observation records into Postgres."""
    if not observations:
        return
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for obs in observations:
                cur.execute(
                    """INSERT INTO observations (ts, session_id, project, scope, type, content)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        datetime.now(timezone.utc),
                        session_id,
                        project,
                        obs["scope"],
                        obs["type"],
                        obs["content"],
                    ),
                )
        conn.commit()
    finally:
        conn.close()


def insert_interaction_style(style: dict, session_id: str, project: str):
    """Insert an interaction style record into Postgres."""
    if not style:
        return
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO interaction_styles
                   (ts, session_id, project, domain, expert, inquisitive, architectural,
                    precise, scope_aware, risk_conscious, ai_led)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    datetime.now(timezone.utc),
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
    """Record that a session has been processed (even if no observations were extracted)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO observed_sessions (session_id, project, ts, had_observations)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (session_id) DO NOTHING""",
                (session_id, project, datetime.now(timezone.utc), had_observations),
            )
        conn.commit()
    finally:
        conn.close()


def get_observations_for_project(project: str) -> list[dict]:
    """Get all observations for a project."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT scope, type, content FROM observations WHERE project = %s ORDER BY ts",
                (project,),
            )
            return [{"scope": r[0], "type": r[1], "content": r[2]} for r in cur.fetchall()]
    finally:
        conn.close()


def get_global_observations() -> list[dict]:
    """Get all global-scoped observations across all projects."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT scope, type, content FROM observations WHERE scope = 'global' ORDER BY ts",
            )
            return [{"scope": r[0], "type": r[1], "content": r[2]} for r in cur.fetchall()]
    finally:
        conn.close()


def get_all_projects() -> list[str]:
    """Get all project slugs that have observations."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT project FROM observations ORDER BY project")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def is_session_observed(session_id: str) -> bool:
    """Check if a session has already been attempted."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM observed_sessions WHERE session_id = %s LIMIT 1",
                (session_id,),
            )
            return cur.fetchone() is not None
    finally:
        conn.close()
