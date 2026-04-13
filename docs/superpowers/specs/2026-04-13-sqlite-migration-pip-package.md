# SQLite Migration + Pip Package — Design Spec

**Date:** 2026-04-13
**Status:** Approved

---

## Overview

Migrate the observational memory system from Postgres to SQLite and package it as a pip-installable CLI. The goal is zero-config setup: `pip install observational-memory && observational-memory install` — no Docker, no `.env`, no repo cloning.

---

## Goals

- One-command install for anyone with Python and Claude Code
- No external infrastructure (no Docker, no Postgres, no env files for DB)
- Preserve all existing behavior (observer, reflector, session parsing, prompts)
- Publishable to PyPI

---

## Database Migration: Postgres → SQLite

### Storage location

`~/.observational-memory/memory.db` — conventional, not configurable. Created automatically on `install`.

### Schema

Same 4 tables, adapted for SQLite syntax:

```sql
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
```

### `db.py` changes

- Replace `psycopg2` with `sqlite3` (stdlib — no dependency)
- Replace `get_connection()` with a function returning a `sqlite3.connect()` to `~/.observational-memory/memory.db`
- Enable WAL mode on every connection (`PRAGMA journal_mode=WAL`) — prevents `database is locked` errors when the observer and reflector run concurrently
- Replace `%s` placeholders with `?`
- Replace `TIMESTAMPTZ` with `TEXT` (ISO 8601 strings)
- Replace `BOOLEAN` with `INTEGER` (0/1)
- Replace `SERIAL` with `INTEGER PRIMARY KEY AUTOINCREMENT`
- `ON CONFLICT` and `EXCLUDED` syntax used by `mark_session_observed` and `upsert_reflection` is valid in SQLite 3.24.0+ (Python 3.10 ships with 3.37+) — no changes needed
- All function signatures stay identical — callers don't change
- All import paths change from `from observer.xxx` to `from observational_memory.xxx`
- Add `init_db()` function that runs the schema creation (called by `install` and on first connection)

### What's removed

- `psycopg2-binary` from requirements
- All `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` env vars
- `scripts/init_db.sql` (schema moves into `db.py` as a constant)
- `.env` file from the template (users only need `ANTHROPIC_API_KEY` in their shell env)

---

## Package Structure

Restructure from flat `observer/` to proper Python package:

```
observational-memory/
├── pyproject.toml
├── src/
│   └── observational_memory/
│       ├── __init__.py         # Version constant
│       ├── cli.py              # CLI entry points (install, uninstall, backfill, reflect)
│       ├── db.py               # SQLite layer
│       ├── observe.py          # Observer (CC Stop hook entrypoint)
│       ├── reflect.py          # Reflector
│       ├── prompts.py          # LLM prompts
│       ├── session_parser.py   # CC session JSONL parser
│       └── slugs.py            # Slug derivation
├── skills/
│   └── jg-context.md           # Portable skill (not packaged — lives in repo)
├── scripts/
│   └── bootstrap-project.sh    # Creates CLAUDE.md in other projects
├── tests/
│   ├── test_db.py
│   ├── test_observe.py
│   ├── test_reflect.py
│   ├── test_session_parser.py
│   ├── test_slugs.py
│   └── fixtures/
├── docs/
├── CLAUDE.md
└── README.md                   # For PyPI (auto-rendered)
```

### `pyproject.toml`

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
```

Single dependency: `anthropic`. Everything else is stdlib.

---

## CLI (`cli.py`)

Entry point: `observational-memory <command>`

### `install`

1. Warn if `ANTHROPIC_API_KEY` is not set (non-blocking — they can set it later)
2. Create `~/.observational-memory/` and `~/.observational-memory/memory/projects/` directories
3. Initialize SQLite database (create tables if not exist)
4. Wire CC Stop hook into `~/.claude/settings.json`:
   - Read existing settings (or create empty)
   - Add a Stop hook entry that runs the observer
   - The hook command: `python -m observational_memory.observe`
   - Skip if already wired (check for `observational_memory` in existing hook commands)
5. Print success + optional next steps

### `uninstall`

1. Remove the Stop hook from `~/.claude/settings.json`
2. Print message that data is preserved at `~/.observational-memory/` (user deletes manually)

### `backfill`

Delegates to existing backfill logic — processes all unobserved CC sessions.

### `reflect`

- `observational-memory reflect <slug>` — reflect one project
- `observational-memory reflect --all` — reflect all projects + global

### `migrate-from-postgres`

- `observational-memory migrate-from-postgres` — one-time migration from existing Postgres DB
- Accepts `--host`, `--port`, `--dbname`, `--user`, `--password` args (defaults to the old env var values)
- Requires `psycopg2-binary` to be installed (not a package dependency — user installs manually if needed)

### `--version`

- `observational-memory --version` — prints package version

---

## Observer Changes

### Hook command

The CC Stop hook command changes from:

```
export $(cat /path/to/.env | xargs) && PYTHONPATH=/path/to/repo python /path/to/repo/observer/observe.py
```

To:

```
python -m observational_memory.observe
```

No env vars to export (SQLite needs no config). No PYTHONPATH (it's pip-installed). The `ANTHROPIC_API_KEY` must be in the user's shell environment.

### Memory file paths

Synthesized prose files move from the repo to `~/.observational-memory/`:

- `~/.observational-memory/memory/global.md`
- `~/.observational-memory/memory/projects/{slug}.md`
- `~/.observational-memory/errors.log`

The `MEMORY_ROOT` constant in `observe.py` and `reflect.py` changes to `~/.observational-memory/memory`.

### Skill file update

`skills/jg-context.md` path changes from `~/Projects/jg-observational-memory/memory/` to `~/.observational-memory/memory/`. This makes it machine-independent.

---

## Reflector: JSONL Removal

The reflector currently has three modes: legacy JSONL-based, `--from-db` single slug, and `--from-db --all`. With SQLite as the primary store, **all reflection reads from SQLite**. The JSONL-based code path (cursor files, `get_unprocessed_entries` from files, `archive_and_truncate`) is removed.

**What changes in `reflect.py`:**
- Remove `read_cursor()`, `get_unprocessed_entries()`, `archive_and_truncate()`, `resolve_paths()`
- Remove the legacy JSONL code path from `main()`
- `reflect_slug()` stays the same — it already takes a list of entries and a slug
- CLI routes to `reflect_slug()` directly with entries from `get_observations_for_project()` / `get_global_observations()`

**What changes in `observe.py`:**
- Remove `check_and_trigger_reflector()` (depends on JSONL line counts)
- Remove JSONL dual-write (`append_observations` and all JSONL log writing)
- Reflection is now triggered by a count query against SQLite: `SELECT COUNT(*) FROM observations WHERE project = ? AND id > (SELECT COALESCE(MAX(last_observation_id), 0) FROM reflections WHERE slug = ?)`. Add `last_observation_id` column to `reflections` table.
- The subprocess invocation changes from `subprocess.Popen([sys.executable, reflect_script, slug])` to `subprocess.Popen([sys.executable, "-m", "observational_memory.reflect", slug])`

**What's removed entirely:**
- JSONL log files, cursor files, archive directory
- `memory/logs/` directory structure (no longer needed)
- The `MEMORY_ROOT` paths related to logs

**What stays:**
- Synthesized prose files at `~/.observational-memory/memory/global.md` and `~/.observational-memory/memory/projects/{slug}.md`
- Error logging to `~/.observational-memory/errors.log`

---

## What Stays the Same

- `observe.py` core logic: session parsing, Haiku extraction, observation writing to SQLite, catch-up for missed sessions
- `prompts.py`: unchanged
- `session_parser.py`: unchanged
- `slugs.py`: unchanged
- All `db.py` function signatures: `insert_observations`, `insert_interaction_style`, `mark_session_observed`, `is_session_observed`, `get_observations_for_project`, `get_global_observations`, `get_all_projects`, `upsert_reflection`
- Model pinned to `claude-haiku-4-5-20251001`

---

## Migration Path (for existing users — i.e., Jeremy)

A one-time migration script (`cli.py migrate-from-postgres`) that:

1. Connects to the existing Postgres DB (env vars or args)
2. Reads all rows from all 4 tables
3. Inserts them into the new SQLite DB
4. Reports counts

This is a convenience, not a requirement. New users start fresh.

---

## Testing

- Existing tests adapt to SQLite (use in-memory `":memory:"` DB or tmp_path)
- Add `test_db.py` for SQLite-specific behavior (init_db, WAL mode, upsert)
- `test_observe.py` and `test_reflect.py` stay structurally the same — they already mock DB calls
- Add `test_cli.py` for install/uninstall commands — `install` and `uninstall` accept an optional `config_root` parameter (defaults to `~`) so tests can use a tmp directory without monkey-patching

---

## Out of Scope

- PyPI publishing automation (manual `python -m build && twine upload` for now)
- Dashboard migration (separate project, can read SQLite directly)
- Vector/semantic retrieval
- Multi-machine sync
