# SQLite Migration + Pip Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate from Postgres to SQLite and package as a pip-installable CLI so anyone can run `pip install observational-memory && observational-memory install`.

**Architecture:** Replace psycopg2 with stdlib sqlite3, restructure from `observer/` to `src/observational_memory/`, add CLI entry point via pyproject.toml. Remove all JSONL-based reflection code. SQLite DB lives at `~/.observational-memory/memory.db`.

**Tech Stack:** Python 3.10+, sqlite3 (stdlib), anthropic SDK, hatchling (build)

**Spec:** `docs/superpowers/specs/2026-04-13-sqlite-migration-pip-package.md`

---

### Task 1: Package scaffolding + pyproject.toml

**Files:**
- Create: `pyproject.toml`
- Create: `src/observational_memory/__init__.py`
- Create: `src/observational_memory/__main__.py`

This task creates the package skeleton. No code moves yet — just the build config and entry points.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "observational-memory"
version = "0.1.0"
description = "Automatic behavioral profiling for Claude Code sessions"
requires-python = ">=3.10"
dependencies = ["anthropic>=0.49.0"]
readme = "README.md"

[project.scripts]
observational-memory = "observational_memory.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/observational_memory"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Create `src/observational_memory/__init__.py`**

```python
"""Observational memory system for Claude Code."""
__version__ = "0.1.0"
```

- [ ] **Step 3: Create `src/observational_memory/__main__.py`**

```python
"""Allow `python -m observational_memory` to run the CLI."""
from observational_memory.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify package structure is valid**

Run: `ls src/observational_memory/`
Expected: `__init__.py  __main__.py`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/
git commit -m "feat: package scaffolding with pyproject.toml"
```

---

### Task 2: SQLite db.py

**Files:**
- Create: `src/observational_memory/db.py`
- Create: `tests/test_db.py`

Rewrite the database layer from Postgres to SQLite. Same function signatures (except `upsert_reflection` gains `last_observation_id`). All callers will work unchanged.

- [ ] **Step 1: Write `tests/test_db.py`**

```python
import os
import sqlite3
from unittest.mock import patch

import pytest

from observational_memory.db import (
    init_db,
    insert_observations,
    insert_interaction_style,
    mark_session_observed,
    is_session_observed,
    get_observations_for_project,
    get_global_observations,
    get_all_projects,
    upsert_reflection,
    get_unprocessed_count,
)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    """Patch DB_PATH for all tests in this module."""
    db_path = str(tmp_path / "test.db")
    with patch("observational_memory.db.DB_PATH", db_path):
        init_db()
        yield db_path


def test_init_db_creates_tables(tmp_db):
    conn = sqlite3.connect(tmp_db)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = sorted(r[0] for r in cur.fetchall())
    conn.close()
    assert "interaction_styles" in tables
    assert "observations" in tables
    assert "observed_sessions" in tables
    assert "reflections" in tables


def test_init_db_enables_wal(tmp_db):
    conn = sqlite3.connect(tmp_db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal"


def test_insert_and_get_observations(tmp_db):
    obs = [
        {"scope": "project", "type": "preference", "content": "likes tests"},
        {"scope": "global", "type": "correction", "content": "never mock DB"},
    ]
    insert_observations(obs, "session-1", "myproj")
    result = get_observations_for_project("myproj")
    assert len(result) == 2
    assert result[0]["content"] == "likes tests"


def test_get_global_observations(tmp_db):
    obs = [
        {"scope": "global", "type": "preference", "content": "global rule"},
        {"scope": "project", "type": "preference", "content": "project only"},
    ]
    insert_observations(obs, "session-1", "proj")
    result = get_global_observations()
    assert len(result) == 1
    assert result[0]["content"] == "global rule"


def test_insert_interaction_style(tmp_db):
    style = {
        "domain": "frontend",
        "expert": 0.8, "inquisitive": 0.2, "architectural": 0.5,
        "precise": 0.9, "scope_aware": 0.4, "risk_conscious": 0.3, "ai_led": 0.1,
    }
    insert_interaction_style(style, "session-1", "myproj")
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT domain, expert FROM interaction_styles").fetchone()
    conn.close()
    assert row[0] == "frontend"
    assert row[1] == pytest.approx(0.8)


def test_mark_and_check_session_observed(tmp_db):
    assert is_session_observed("s1") is False
    mark_session_observed("s1", "proj", True)
    assert is_session_observed("s1") is True


def test_mark_session_observed_idempotent(tmp_db):
    mark_session_observed("s1", "proj", True)
    mark_session_observed("s1", "proj", False)  # Should not raise
    assert is_session_observed("s1") is True


def test_upsert_reflection(tmp_db):
    upsert_reflection("myproj", "testing: always write tests", 5, 42)
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT prose, observation_count, last_observation_id FROM reflections WHERE slug = ?", ("myproj",)).fetchone()
    conn.close()
    assert row[0] == "testing: always write tests"
    assert row[1] == 5
    assert row[2] == 42


def test_upsert_reflection_updates(tmp_db):
    upsert_reflection("myproj", "v1", 5, 10)
    upsert_reflection("myproj", "v2", 10, 50)
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT prose, last_observation_id FROM reflections WHERE slug = ?", ("myproj",)).fetchone()
    conn.close()
    assert row[0] == "v2"
    assert row[1] == 50


def test_get_all_projects(tmp_db):
    insert_observations([{"scope": "project", "type": "preference", "content": "a"}], "s1", "proj-a")
    insert_observations([{"scope": "project", "type": "preference", "content": "b"}], "s2", "proj-b")
    projects = get_all_projects()
    assert "proj-a" in projects
    assert "proj-b" in projects


def test_get_unprocessed_count(tmp_db):
    insert_observations([{"scope": "project", "type": "preference", "content": f"obs-{i}"} for i in range(5)], "s1", "myproj")
    assert get_unprocessed_count("myproj") == 5
    upsert_reflection("myproj", "prose", 5, 3)  # last_observation_id=3
    assert get_unprocessed_count("myproj") == 2


def test_get_unprocessed_count_global(tmp_db):
    insert_observations([
        {"scope": "global", "type": "preference", "content": "global-1"},
        {"scope": "global", "type": "preference", "content": "global-2"},
        {"scope": "project", "type": "preference", "content": "project-only"},
    ], "s1", "someproj")
    assert get_unprocessed_count("global") == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL — `observational_memory.db` does not exist yet

- [ ] **Step 3: Write `src/observational_memory/db.py`**

```python
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
    content TEXT NOT NULL
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
    ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_observations_project ON observations(project);
CREATE INDEX IF NOT EXISTS idx_observations_scope ON observations(scope);
CREATE INDEX IF NOT EXISTS idx_observations_type ON observations(type);
CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_styles_project ON interaction_styles(project);
CREATE INDEX IF NOT EXISTS idx_styles_domain ON interaction_styles(domain);
CREATE INDEX IF NOT EXISTS idx_styles_session ON interaction_styles(session_id);
CREATE INDEX IF NOT EXISTS idx_observed_sessions_project ON observed_sessions(project);
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
                """INSERT INTO observations (ts, session_id, project, scope, type, content)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (ts, session_id, project, obs["scope"], obs["type"], obs["content"]),
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
            "SELECT scope, type, content FROM observations WHERE project = ? ORDER BY ts",
            (project,),
        ).fetchall()
        return [{"scope": r[0], "type": r[1], "content": r[2]} for r in rows]
    finally:
        conn.close()


def get_global_observations() -> list[dict]:
    """Get all global-scoped observations across all projects."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT scope, type, content FROM observations WHERE scope = 'global' ORDER BY ts",
        ).fetchall()
        return [{"scope": r[0], "type": r[1], "content": r[2]} for r in rows]
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


def upsert_reflection(slug: str, prose: str, observation_count: int, last_observation_id: int):
    """Store or update the synthesized prose for a project/global slug."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO reflections (slug, prose, char_count, observation_count, last_observation_id, ts)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT (slug) DO UPDATE SET
                 prose = EXCLUDED.prose,
                 char_count = EXCLUDED.char_count,
                 observation_count = EXCLUDED.observation_count,
                 last_observation_id = EXCLUDED.last_observation_id,
                 ts = EXCLUDED.ts""",
            (slug, prose, len(prose), observation_count, last_observation_id, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: All 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/observational_memory/db.py tests/test_db.py
git commit -m "feat: SQLite database layer replacing Postgres"
```

---

### Task 3: Move pure modules (slugs, session_parser, prompts)

**Files:**
- Copy: `observer/slugs.py` → `src/observational_memory/slugs.py`
- Copy: `observer/session_parser.py` → `src/observational_memory/session_parser.py`
- Copy: `observer/prompts.py` → `src/observational_memory/prompts.py`
- Modify: `tests/test_slugs.py` — update imports
- Modify: `tests/test_session_parser.py` — update imports

These three modules have zero dependencies on db.py or each other. Straight copy + import update.

- [ ] **Step 1: Copy the three modules**

```bash
cp observer/slugs.py src/observational_memory/slugs.py
cp observer/session_parser.py src/observational_memory/session_parser.py
cp observer/prompts.py src/observational_memory/prompts.py
```

- [ ] **Step 2: Update test imports in `tests/test_slugs.py`**

Change `from observer.slugs import` to `from observational_memory.slugs import`.

- [ ] **Step 3: Update test imports in `tests/test_session_parser.py`**

Change `from observer.session_parser import` to `from observational_memory.session_parser import`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_slugs.py tests/test_session_parser.py -v`
Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/observational_memory/slugs.py src/observational_memory/session_parser.py src/observational_memory/prompts.py tests/test_slugs.py tests/test_session_parser.py
git commit -m "feat: move slugs, session_parser, prompts to new package"
```

---

### Task 4: Rewrite observe.py

**Files:**
- Create: `src/observational_memory/observe.py`
- Modify: `tests/test_observe.py` — update imports, remove JSONL tests

Key changes from old `observer/observe.py`:
- All imports change to `from observational_memory.xxx`
- Remove `append_observations()` — no more JSONL writing
- Remove `check_and_trigger_reflector()` — replaced by `maybe_trigger_reflection()`
- `MEMORY_ROOT` changes to `~/.observational-memory/memory`
- `log_error` writes to `~/.observational-memory/errors.log`
- `process_session` no longer writes JSONL — only SQLite
- `maybe_trigger_reflection` queries SQLite for unprocessed count

- [ ] **Step 1: Write updated `tests/test_observe.py`**

```python
import json
from unittest.mock import patch, MagicMock

from observational_memory.observe import (
    cwd_from_session_file,
    strip_code_fences,
)


def test_cwd_from_session_file(tmp_path):
    session = tmp_path / "test.jsonl"
    session.write_text(json.dumps({
        "type": "progress",
        "cwd": "/Users/test/Projects/myapp",
        "sessionId": "abc123",
    }) + "\n")
    assert cwd_from_session_file(str(session)) == "/Users/test/Projects/myapp"


def test_cwd_from_session_file_missing():
    assert cwd_from_session_file("/nonexistent/file.jsonl") is None


def test_cwd_from_session_file_no_cwd(tmp_path):
    session = tmp_path / "test.jsonl"
    session.write_text(json.dumps({"type": "system"}) + "\n")
    assert cwd_from_session_file(str(session)) is None


def test_strip_code_fences_json():
    text = '```json\n[{"scope": "global"}]\n```'
    result = strip_code_fences(text)
    assert result == '[{"scope": "global"}]'


def test_strip_code_fences_plain():
    text = '[{"scope": "global"}]'
    assert strip_code_fences(text) == text


def test_maybe_trigger_reflection_below_threshold():
    with patch("observational_memory.observe.get_unprocessed_count", return_value=50):
        with patch("observational_memory.observe.subprocess") as mock_sub:
            from observational_memory.observe import maybe_trigger_reflection
            maybe_trigger_reflection("slug")
            mock_sub.Popen.assert_not_called()


def test_maybe_trigger_reflection_above_threshold():
    with patch("observational_memory.observe.get_unprocessed_count", return_value=101):
        with patch("observational_memory.observe.subprocess") as mock_sub:
            from observational_memory.observe import maybe_trigger_reflection
            maybe_trigger_reflection("slug")
            mock_sub.Popen.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_observe.py -v`
Expected: FAIL — new module not written yet

- [ ] **Step 3: Write `src/observational_memory/observe.py`**

Based on existing `observer/observe.py` with these changes:
- Imports from `observational_memory.*`
- `MEMORY_ROOT = os.path.expanduser("~/.observational-memory/memory")`
- `log_error` writes to `~/.observational-memory/errors.log`
- Remove `append_observations` function
- Remove `check_and_trigger_reflector` function
- Add `maybe_trigger_reflection(slug)` that calls `get_unprocessed_count()` and spawns `python -m observational_memory.reflect {slug}`
- `process_session`: remove all JSONL writing, keep SQLite writes
- `get_existing_observations_summary`: import from `observational_memory.db`
- `extract_observations`: import from `observational_memory.prompts`
- `main()`: same structure but uses new imports and `maybe_trigger_reflection`

```python
"""Observer: extracts observations from CC session transcripts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import anthropic

from observational_memory.slugs import cc_slug, memory_slug
from observational_memory.session_parser import parse_session
from observational_memory.prompts import OBSERVER_SYSTEM_PROMPT, OBSERVER_USER_PROMPT
from observational_memory.db import (
    insert_observations,
    insert_interaction_style,
    is_session_observed,
    mark_session_observed,
    get_observations_for_project,
    get_global_observations,
    get_unprocessed_count,
)

MEMORY_ROOT = os.path.expanduser("~/.observational-memory/memory")
ERROR_LOG = os.path.expanduser("~/.observational-memory/errors.log")
REFLECTION_THRESHOLD = 100
MODEL = "claude-haiku-4-5-20251001"


def log_error(msg: str):
    os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
    with open(ERROR_LOG, "a") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")


def cwd_from_session_file(path: str) -> str | None:
    """Extract the cwd from the first record in a CC session JSONL file."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                cwd = record.get("cwd")
                if cwd:
                    return cwd
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def strip_code_fences(text: str) -> str:
    """Strip markdown code fences from model output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return text


def get_existing_observations_summary(project: str) -> str:
    """Build a summary of existing observations for dedup context."""
    try:
        project_obs = get_observations_for_project(project)
        global_obs = get_global_observations()
    except Exception:
        return ""

    seen = set()
    unique = []
    for obs in project_obs + global_obs:
        if obs["content"] not in seen:
            seen.add(obs["content"])
            unique.append(obs)

    if not unique:
        return ""

    recent = unique[-50:]
    lines = [f"- [{o['type']}] {o['content']}" for o in recent]
    return "\n".join(lines)


def extract_observations(messages: list[dict], project: str) -> tuple[list[dict], dict | None]:
    """Call Haiku to extract observations and interaction style from conversation."""
    if not messages:
        return [], None
    if len(messages) > 60:
        messages = messages[:5] + messages[-50:]
    conversation = "\n".join(
        f"{'USER' if m['role'] == 'user' else 'ASSISTANT'}: {m['content']}"
        for m in messages
    )

    existing_summary = get_existing_observations_summary(project)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=OBSERVER_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": OBSERVER_USER_PROMPT.format(
                project=project,
                conversation=conversation,
                existing_observations=existing_summary,
            )}
        ],
    )
    text = strip_code_fences(response.content[0].text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        log_error(f"Failed to parse observer response as JSON: {text[:500]}")
        return [], None

    if isinstance(parsed, dict) and "observations" in parsed:
        raw_obs = parsed.get("observations", [])
        interaction_style = parsed.get("interaction_style")
    elif isinstance(parsed, list):
        raw_obs = parsed
        interaction_style = None
    else:
        return [], None

    observations = [
        obs for obs in raw_obs
        if isinstance(obs, dict)
        and obs.get("scope") in ("global", "project")
        and obs.get("type") in ("preference", "correction", "pattern", "decision")
        and obs.get("content")
    ]
    return observations, interaction_style


def maybe_trigger_reflection(slug: str):
    """Check if unprocessed observations exceed threshold and trigger reflector."""
    try:
        count = get_unprocessed_count(slug)
    except Exception:
        return
    if count > REFLECTION_THRESHOLD:
        subprocess.Popen(
            [sys.executable, "-m", "observational_memory.reflect", slug],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def process_session(session_path: str, session_id: str, cwd: str) -> str | None:
    """Process a single session transcript. Returns the memory slug if observations were written."""
    slug = memory_slug(cwd)
    messages = parse_session(session_path)
    if not messages:
        return None
    observations, interaction_style = extract_observations(messages, slug)

    has_obs = bool(observations) or bool(interaction_style)

    try:
        if observations:
            insert_observations(observations, session_id, slug)
        if interaction_style and isinstance(interaction_style, dict):
            insert_interaction_style(interaction_style, session_id, slug)
        mark_session_observed(session_id, slug, has_obs)
    except Exception as e:
        log_error(f"DB write failed for session {session_id}: {e}")

    if not has_obs:
        return None
    return slug


def find_all_cc_sessions() -> list[tuple[str, str]]:
    """Scan all CC project directories for session JSONL files."""
    cc_projects_root = os.path.expanduser("~/.claude/projects")
    sessions = []
    try:
        for project_dir_name in os.listdir(cc_projects_root):
            project_dir = os.path.join(cc_projects_root, project_dir_name)
            if not os.path.isdir(project_dir):
                continue
            for fname in os.listdir(project_dir):
                if fname.endswith(".jsonl"):
                    sid = fname.removesuffix(".jsonl")
                    sessions.append((sid, os.path.join(project_dir, fname)))
    except FileNotFoundError:
        pass
    return sessions


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception) as e:
        log_error(f"Failed to read stdin payload: {e}")
        sys.exit(0)

    session_id = payload.get("sessionId", "")
    cwd = payload.get("cwd", "")
    if not session_id or not cwd:
        log_error(f"Missing sessionId or cwd in payload: {payload}")
        sys.exit(0)

    cc_project_slug = cc_slug(cwd)
    cc_project_dir = os.path.expanduser(f"~/.claude/projects/{cc_project_slug}")
    slugs_written = set()

    # Process current session
    session_path = os.path.join(cc_project_dir, f"{session_id}.jsonl")
    if not is_session_observed(session_id):
        slug = process_session(session_path, session_id, cwd)
        if slug:
            slugs_written.add(slug)

    # Catch up missed sessions across ALL projects
    for sid, spath in find_all_cc_sessions():
        if sid == session_id:
            continue
        try:
            if is_session_observed(sid):
                continue
            session_cwd = cwd_from_session_file(spath)
            if not session_cwd:
                continue
            slug = process_session(spath, sid, session_cwd)
            if slug:
                slugs_written.add(slug)
        except Exception as e:
            log_error(f"Error processing missed session {sid}: {e}")

    # Check reflection thresholds per project
    for slug in slugs_written:
        maybe_trigger_reflection(slug)
    if slugs_written:
        maybe_trigger_reflection("global")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error(f"Observer fatal error: {e}")
    sys.exit(0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_observe.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/observational_memory/observe.py tests/test_observe.py
git commit -m "feat: rewrite observer for SQLite, remove JSONL writing"
```

---

### Task 5: Rewrite reflect.py

**Files:**
- Create: `src/observational_memory/reflect.py`
- Modify: `tests/test_reflect.py` — update imports, remove JSONL tests

Key changes: remove all JSONL code paths (`read_cursor`, `get_unprocessed_entries`, `archive_and_truncate`, `resolve_paths`). All reads come from SQLite. `upsert_reflection` now passes `last_observation_id`.

- [ ] **Step 1: Write updated `tests/test_reflect.py`**

```python
from unittest.mock import patch, MagicMock

from observational_memory.reflect import (
    validate_token_length,
    read_synthesized_prose,
)


def test_validate_token_length():
    assert validate_token_length("x" * 100) is True
    assert validate_token_length("x" * 9000) is False


def test_read_synthesized_prose_missing(tmp_path):
    assert read_synthesized_prose(str(tmp_path / "nonexistent.md")) == ""


def test_read_synthesized_prose_existing(tmp_path):
    md_path = tmp_path / "test.md"
    md_path.write_text("testing: always write tests")
    assert read_synthesized_prose(str(md_path)) == "testing: always write tests"


def test_compress_prose_is_callable():
    from observational_memory.reflect import compress_prose
    import inspect
    sig = inspect.signature(compress_prose)
    assert len(sig.parameters) == 1


def test_reflect_slug_writes_prose(tmp_path):
    """Test that reflect_slug writes the synthesized prose to the correct file."""
    md_path = str(tmp_path / "test.md")
    entries = [{"type": "preference", "content": "likes tests"}]

    with patch("observational_memory.reflect.synthesize", return_value="testing: always write tests"):
        with patch("observational_memory.reflect.upsert_reflection"):
            with patch("observational_memory.reflect.get_max_observation_id", return_value=42):
                from observational_memory.reflect import reflect_slug
                reflect_slug("test", entries, md_path)

    with open(md_path) as f:
        assert f.read() == "testing: always write tests"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_reflect.py -v`
Expected: FAIL — new module not written yet

- [ ] **Step 3: Write `src/observational_memory/reflect.py`**

```python
"""Reflector: synthesizes observations into dense compressed prose."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import anthropic

from observational_memory.prompts import REFLECTOR_SYSTEM_PROMPT, REFLECTOR_USER_PROMPT
from observational_memory.db import (
    get_observations_for_project,
    get_global_observations,
    get_all_projects,
    upsert_reflection,
)

MEMORY_ROOT = os.path.expanduser("~/.observational-memory/memory")
ERROR_LOG = os.path.expanduser("~/.observational-memory/errors.log")
MODEL = "claude-haiku-4-5-20251001"
MAX_CHARS = 8000  # ~2000 tokens


def log_error(msg: str):
    os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
    with open(ERROR_LOG, "a") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")


def read_synthesized_prose(md_path: str) -> str:
    try:
        return open(md_path).read()
    except FileNotFoundError:
        return ""


def validate_token_length(text: str) -> bool:
    return len(text) <= MAX_CHARS


def compress_prose(prose: str) -> str:
    """Ask Haiku to compress prose that exceeds the size limit."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system="You are a compression agent. Take the provided text and compress it to fit within 8000 characters while preserving all important behavioral rules. Maintain the dense prose format with topic-prefix labels. Prioritize [CORRECTION] items.",
        messages=[
            {"role": "user", "content": f"Compress this text to under 8000 characters:\n\n{prose}"}
        ],
    )
    return response.content[0].text


def synthesize(existing_prose: str, entries: list[dict]) -> str:
    """Call Haiku to synthesize observations into dense prose."""
    observations_text = "\n".join(
        f"{'[CORRECTION] ' if e.get('type') == 'correction' else ''}{e.get('content', '')}"
        for e in entries
    )
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=REFLECTOR_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": REFLECTOR_USER_PROMPT.format(
                existing_prose=existing_prose or "(no existing rules)",
                observations=observations_text,
            )}
        ],
    )
    return response.content[0].text


def get_max_observation_id(slug: str) -> int:
    """Get the max observation ID for a project (used for last_observation_id tracking)."""
    from observational_memory.db import get_connection
    conn = get_connection()
    try:
        if slug == "global":
            row = conn.execute(
                "SELECT MAX(id) FROM observations WHERE scope = 'global'"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT MAX(id) FROM observations WHERE project = ?", (slug,)
            ).fetchone()
        return row[0] if row and row[0] else 0
    finally:
        conn.close()


def reflect_slug(slug: str, entries: list[dict], md_path: str | None = None):
    """Run reflection for a single slug with given entries."""
    if not entries:
        return

    if md_path is None:
        if slug == "global":
            md_path = os.path.join(MEMORY_ROOT, "global.md")
        else:
            md_path = os.path.join(MEMORY_ROOT, "projects", f"{slug}.md")

    existing_prose = read_synthesized_prose(md_path)
    new_prose = synthesize(existing_prose, entries)

    if not validate_token_length(new_prose):
        log_error(f"Synthesis for {slug} exceeded {MAX_CHARS} chars ({len(new_prose)}), retrying with compression")
        new_prose = compress_prose(new_prose)
        if not validate_token_length(new_prose):
            log_error(f"Synthesis for {slug} still exceeds limit after retry ({len(new_prose)}), writing anyway")

    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w") as f:
        f.write(new_prose)

    try:
        max_id = get_max_observation_id(slug)
        upsert_reflection(slug, new_prose, len(entries), max_id)
    except Exception as e:
        log_error(f"Failed to upsert reflection for {slug}: {e}")

    print(f"  {slug}: {len(entries)} observations -> {len(new_prose)} chars")


def main():
    reflect_all = "--all" in sys.argv
    slug = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            slug = arg
            break

    if reflect_all:
        projects = get_all_projects()
        print(f"Reflecting {len(projects)} projects + global...")
        global_entries = get_global_observations()
        reflect_slug("global", global_entries)
        for project in projects:
            entries = get_observations_for_project(project)
            reflect_slug(project, entries)
        print("Done.")
    elif slug:
        if slug == "global":
            entries = get_global_observations()
        else:
            entries = get_observations_for_project(slug)
        reflect_slug(slug, entries)
    else:
        log_error("reflect.py requires a slug argument or --all")

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error(f"Reflector fatal error: {e}")
    sys.exit(0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_reflect.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/observational_memory/reflect.py tests/test_reflect.py
git commit -m "feat: rewrite reflector for SQLite, remove JSONL code paths"
```

---

### Task 6: CLI (install, uninstall, backfill, reflect, version)

**Files:**
- Create: `src/observational_memory/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write `tests/test_cli.py`**

```python
import json
import os
from unittest.mock import patch

from observational_memory.cli import do_install, do_uninstall


def test_install_creates_dirs(tmp_path):
    config_root = str(tmp_path)
    with patch("observational_memory.cli.DB_PATH", str(tmp_path / "memory.db")):
        with patch("observational_memory.cli.init_db"):
            do_install(config_root=config_root)

    assert (tmp_path / ".observational-memory").is_dir()
    assert (tmp_path / ".observational-memory" / "memory" / "projects").is_dir()


def test_install_creates_settings_with_hook(tmp_path):
    config_root = str(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    settings_path.write_text("{}")

    with patch("observational_memory.cli.DB_PATH", str(tmp_path / "memory.db")):
        with patch("observational_memory.cli.init_db"):
            do_install(config_root=config_root)

    settings = json.loads(settings_path.read_text())
    assert "hooks" in settings
    assert "Stop" in settings["hooks"]
    hook_commands = [
        h["hooks"][0]["command"]
        for h in settings["hooks"]["Stop"]
        if isinstance(h, dict) and h.get("hooks")
    ]
    assert any("observational_memory" in cmd for cmd in hook_commands)


def test_install_skips_duplicate_hook(tmp_path):
    config_root = str(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps({
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python -m observational_memory.observe"}]}]}
    }))

    with patch("observational_memory.cli.DB_PATH", str(tmp_path / "memory.db")):
        with patch("observational_memory.cli.init_db"):
            do_install(config_root=config_root)

    settings = json.loads(settings_path.read_text())
    # Should still have exactly one hook
    assert len(settings["hooks"]["Stop"]) == 1


def test_uninstall_removes_hook(tmp_path):
    config_root = str(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps({
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "command", "command": "some-other-hook"}]},
                {"hooks": [{"type": "command", "command": "python -m observational_memory.observe"}]},
            ]
        }
    }))

    do_uninstall(config_root=config_root)

    settings = json.loads(settings_path.read_text())
    assert len(settings["hooks"]["Stop"]) == 1
    assert "observational_memory" not in settings["hooks"]["Stop"][0]["hooks"][0]["command"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — module not written yet

- [ ] **Step 3: Write `src/observational_memory/cli.py`**

```python
"""CLI entry points for observational-memory."""
from __future__ import annotations

import argparse
import json
import os
import sys

from observational_memory import __version__
from observational_memory.db import DB_PATH, init_db


def do_install(config_root: str | None = None):
    """Install observational memory: create dirs, init DB, wire hook."""
    root = config_root or os.path.expanduser("~")
    om_dir = os.path.join(root, ".observational-memory")
    memory_dir = os.path.join(om_dir, "memory", "projects")
    os.makedirs(memory_dir, exist_ok=True)

    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  ⚠ ANTHROPIC_API_KEY not set. The observer needs it to call Claude Haiku.")
        print("    Set it in your shell profile before using.")

    # Init DB
    init_db()
    print("  ✓ Initialized SQLite database")

    # Wire CC Stop hook
    claude_dir = os.path.join(root, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    settings_path = os.path.join(claude_dir, "settings.json")

    if os.path.exists(settings_path):
        with open(settings_path) as f:
            settings = json.load(f)
    else:
        settings = {}

    hook_command = "python -m observational_memory.observe"
    new_hook = {"hooks": [{"type": "command", "command": hook_command, "timeout": 30}]}

    hooks = settings.setdefault("hooks", {})
    stop_hooks = hooks.setdefault("Stop", [])

    already_wired = any(
        "observational_memory" in h.get("hooks", [{}])[0].get("command", "")
        for h in stop_hooks
        if isinstance(h, dict) and h.get("hooks")
    )

    if already_wired:
        print("  ✓ Stop hook already wired")
    else:
        stop_hooks.append(new_hook)
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
        print("  ✓ Wired Claude Code Stop hook")

    print()
    print("  ✓ Setup complete!")
    print()
    print("  Observations will be extracted automatically after each Claude Code session.")
    print()
    print("  Optional next steps:")
    print("  • Backfill past sessions:    observational-memory backfill")
    print("  • Synthesize all profiles:   observational-memory reflect --all")


def do_uninstall(config_root: str | None = None):
    """Remove the Stop hook. Preserve data."""
    root = config_root or os.path.expanduser("~")
    settings_path = os.path.join(root, ".claude", "settings.json")

    if not os.path.exists(settings_path):
        print("  No settings.json found — nothing to remove.")
        return

    with open(settings_path) as f:
        settings = json.load(f)

    stop_hooks = settings.get("hooks", {}).get("Stop", [])
    filtered = [
        h for h in stop_hooks
        if not (isinstance(h, dict) and h.get("hooks") and
                "observational_memory" in h["hooks"][0].get("command", ""))
    ]
    settings.setdefault("hooks", {})["Stop"] = filtered

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    om_dir = os.path.join(root, ".observational-memory")
    print("  ✓ Removed Stop hook from Claude Code settings")
    print(f"  Data preserved at {om_dir} — delete manually if desired.")
    print("  Then: pip uninstall observational-memory")


def do_backfill():
    """Process all unobserved CC sessions."""
    from observational_memory.observe import find_all_cc_sessions, process_session, cwd_from_session_file, log_error
    from observational_memory.db import is_session_observed
    import time

    sessions = find_all_cc_sessions()
    print(f"Found {len(sessions)} session files across all CC projects.")

    skipped = processed = failed = 0
    total = len(sessions)

    for i, (sid, spath) in enumerate(sessions, 1):
        try:
            if is_session_observed(sid):
                skipped += 1
                continue
        except Exception as e:
            log_error(f"Backfill DB check failed for {sid}: {e}")
            failed += 1
            continue

        cwd = cwd_from_session_file(spath)
        if not cwd:
            skipped += 1
            continue

        try:
            slug = process_session(spath, sid, cwd)
            if slug:
                processed += 1
                print(f"  [{i}/{total}] {slug} <- session {sid[:8]}...")
            else:
                skipped += 1
        except Exception as e:
            log_error(f"Backfill error for session {sid}: {e}")
            failed += 1
            print(f"  [{i}/{total}] FAILED session {sid[:8]}... — {e}")

        if processed > 0 and processed % 5 == 0:
            time.sleep(1)

    print(f"\nDone. Processed: {processed}, Skipped: {skipped}, Failed: {failed}")


def do_reflect(slug: str | None = None, reflect_all: bool = False):
    """Synthesize observations into dense prose."""
    from observational_memory.reflect import reflect_slug
    from observational_memory.db import get_observations_for_project, get_global_observations, get_all_projects

    if reflect_all:
        projects = get_all_projects()
        print(f"Reflecting {len(projects)} projects + global...")
        global_entries = get_global_observations()
        reflect_slug("global", global_entries)
        for project in projects:
            entries = get_observations_for_project(project)
            reflect_slug(project, entries)
        print("Done.")
    elif slug:
        if slug == "global":
            entries = get_global_observations()
        else:
            entries = get_observations_for_project(slug)
        reflect_slug(slug, entries)
    else:
        print("Usage: observational-memory reflect <slug> or --all")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="observational-memory",
        description="Automatic behavioral profiling for Claude Code sessions",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("install", help="Set up observational memory")
    subparsers.add_parser("uninstall", help="Remove the Claude Code hook")
    subparsers.add_parser("backfill", help="Process all past Claude Code sessions")

    reflect_parser = subparsers.add_parser("reflect", help="Synthesize observations into prose")
    reflect_parser.add_argument("slug", nargs="?", help="Project slug to reflect")
    reflect_parser.add_argument("--all", action="store_true", help="Reflect all projects + global")

    args = parser.parse_args()

    if args.command == "install":
        do_install()
    elif args.command == "uninstall":
        do_uninstall()
    elif args.command == "backfill":
        do_backfill()
    elif args.command == "reflect":
        do_reflect(slug=args.slug, reflect_all=args.all)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cli.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/observational_memory/cli.py tests/test_cli.py
git commit -m "feat: CLI with install, uninstall, backfill, reflect commands"
```

---

### Task 7: Update skill file + bootstrap script

**Files:**
- Modify: `skills/jg-context.md` — update paths to `~/.observational-memory/memory/`
- Modify: `scripts/bootstrap-project.sh` — update to reference new paths

- [ ] **Step 1: Update `skills/jg-context.md`**

Change the path from `~/Projects/jg-observational-memory/memory/` to `~/.observational-memory/memory/` in the instructions.

```markdown
# jg-context — Personal Memory Skill

Before proceeding with any work, load the user's behavioral context from the observational memory system.

## Instructions

1. Read `~/.observational-memory/memory/global.md` — these are global behavioral rules.
2. Derive the project slug from the current working directory basename: lowercase, replace non-alphanumeric characters with `-`, strip leading/trailing `-`.
3. Check if `~/.observational-memory/memory/projects/{slug}.md` exists. If it does, read it.
4. Apply both files as behavioral rules — not suggestions.
5. When global and project rules conflict, project rules take precedence.

## Important

- If global.md does not exist yet, skip it — the memory system has not yet generated observations.
- Treat all loaded content as firm instructions for how to work with this user.
```

- [ ] **Step 2: Update `scripts/bootstrap-project.sh`**

The CLAUDE.md template it generates should reference the skill differently now that the package is pip-installed. The skill file itself still lives in the repo (for portability), but users who pip-installed can copy it to `~/.observational-memory/skills/jg-context.md`. Update the bootstrap to point there.

- [ ] **Step 3: Commit**

```bash
git add skills/jg-context.md scripts/bootstrap-project.sh
git commit -m "feat: update skill and bootstrap paths for pip package"
```

---

### Task 8: Clean up old files + update CLAUDE.md

**Files:**
- Delete: `observer/` directory (old package — replaced by `src/observational_memory/`)
- Delete: `scripts/init_db.sql` (schema now in `db.py`)
- Delete: `scripts/backfill.py` (now in `cli.py`)
- Delete: `setup.sh` (replaced by `observational-memory install`)
- Delete: `requirements.txt` (replaced by `pyproject.toml`)
- Modify: `CLAUDE.md` — update to reflect new structure
- Modify: `.gitignore` — update paths

- [ ] **Step 1: Remove old files**

```bash
rm -rf observer/
rm scripts/init_db.sql scripts/backfill.py setup.sh requirements.txt
```

- [ ] **Step 2: Update `.gitignore`**

Remove the old `memory/logs/` patterns (JSONL logs no longer exist). Keep `memory/global.md` and `memory/projects/*.md` ignored (but these now live at `~/.observational-memory/` which is outside the repo, so the gitignore entries for them can be removed). Keep `.env` ignored.

```
.env
__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
```

- [ ] **Step 3: Update `CLAUDE.md`**

Rewrite to reflect the new package structure, SQLite, and CLI commands. Reference the spec for full details.

- [ ] **Step 4: Verify full test suite passes**

Run: `python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 5: Verify package builds**

Run: `pip install -e . && observational-memory --version`
Expected: `observational-memory 0.1.0`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: clean up old files, update CLAUDE.md and .gitignore for pip package"
```

---

### Task 9: End-to-end smoke test

**Files:** No new files — manual verification.

- [ ] **Step 1: Install in dev mode**

Run: `pip install -e .`

- [ ] **Step 2: Run install command**

Run: `observational-memory install`
Expected: Creates `~/.observational-memory/`, inits DB, reports hook status.

- [ ] **Step 3: Verify SQLite DB exists and has tables**

Run: `sqlite3 ~/.observational-memory/memory.db ".tables"`
Expected: `interaction_styles  observations  observed_sessions  reflections`

- [ ] **Step 4: Verify hook is wired**

Run: `cat ~/.claude/settings.json | python -m json.tool | grep observational_memory`
Expected: Shows the hook command.

- [ ] **Step 5: Run backfill (if past sessions exist)**

Run: `observational-memory backfill`
Expected: Processes sessions, prints counts.

- [ ] **Step 6: Run reflect**

Run: `observational-memory reflect --all`
Expected: Synthesizes prose for each project with observations.

- [ ] **Step 7: Verify prose files exist**

Run: `ls ~/.observational-memory/memory/`
Expected: `global.md` and `projects/` directory with `.md` files.

- [ ] **Step 8: Commit any fixes from smoke test**

```bash
git add -A
git commit -m "fix: smoke test fixes"
```

---

### Task 10: migrate-from-postgres command (optional — for Jeremy only)

**Files:**
- Modify: `src/observational_memory/cli.py` — add `migrate-from-postgres` subcommand

This is only needed for migrating Jeremy's existing Postgres data. Not required for new users.

- [ ] **Step 1: Add migrate subcommand to `cli.py`**

Add a `migrate-from-postgres` subparser that accepts `--host`, `--port`, `--dbname`, `--user`, `--password` args. The handler:
1. Attempts to `import psycopg2` — fails gracefully with install instructions if missing
2. Connects to Postgres, reads all 4 tables
3. Inserts into SQLite
4. Reports row counts

- [ ] **Step 2: Run migration**

Run: `observational-memory migrate-from-postgres --host localhost --dbname mydb --user myuser --password mypass`
Expected: Reports counts per table.

- [ ] **Step 3: Verify data**

Run: `sqlite3 ~/.observational-memory/memory.db "SELECT COUNT(*) FROM observations"`
Expected: Same count as Postgres.

- [ ] **Step 4: Commit**

```bash
git add src/observational_memory/cli.py
git commit -m "feat: migrate-from-postgres command for existing users"
```
