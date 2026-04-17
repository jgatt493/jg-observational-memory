# Observational Memory System

Pip-installable system that watches Claude Code sessions, extracts behavioral observations about how the user works, and synthesizes them into dense prose rules that any AI agent can load.

## Setup

```bash
pip install observational-memory
observational-memory install
```

That's it. The install command creates `~/.observational-memory/`, initializes a SQLite database, and wires a Claude Code Stop hook. Only requires `ANTHROPIC_API_KEY` in your shell env.

## Two Sides of This Project

**1. The system (what you're developing here):** Observer + Reflector pipeline, SQLite storage, session parsing, prompt engineering. Python package in `src/observational_memory/`.

**2. The output (what other projects consume):** `~/.observational-memory/memory/global.md` and `~/.observational-memory/memory/projects/{slug}.md` — dense behavioral profiles loaded via skill file or SessionStart hook.

## Architecture

```
CC Stop hook → python -m observational_memory.observe (stdin: {sessionId, cwd})
  → parses session transcript from ~/.claude/projects/{cc-slug}/{session-id}.jsonl
  → calls Haiku to extract observations + interaction style scores
  → writes to SQLite (~/.observational-memory/memory.db)
  → if unprocessed entries exceed threshold (10 first time, 50 ongoing), fires reflector as subprocess

observational-memory reflect {slug}
  → reads existing prose + observations from SQLite
  → calls Haiku to synthesize a full prose rewrite (max 8000 chars)
  → writes ~/.observational-memory/memory/projects/{slug}.md or global.md
  → stores in SQLite (reflections table)
```

## Key Concepts

**CC slug** — full path with `/` → `-` (e.g. `-Users-alice-Projects-myapp`). Locates CC session files. Leading `-` is intentional.

**Memory slug** — basename, lowercased, special chars → `-`, stripped (e.g. `myapp`, `chat-server`). Used for memory file naming.

**Observation types:** preference, correction, pattern, decision. Corrections are treated as firm rules by the reflector.

**Interaction style:** 7 axes scored 0.0-1.0 per session (expert, inquisitive, architectural, precise, scope_aware, risk_conscious, ai_led) plus a domain label.

## Database

SQLite at `~/.observational-memory/memory.db`. Schema defined in `src/observational_memory/db.py`. Four tables: observations, interaction_styles, observed_sessions, reflections.

## CLI Commands

```bash
observational-memory install                    # set up everything
observational-memory uninstall                  # remove hook, preserve data
observational-memory backfill                   # process all past CC sessions
observational-memory reflect --all              # re-synthesize all projects
observational-memory reflect {slug}             # re-synthesize one project
observational-memory observe-messages {slug}    # observe messages from stdin (JSON array)
observational-memory --version                  # print version
pytest                                          # run tests (no API or DB needed)
```

## File Layout

```
src/observational_memory/
  __init__.py        # Version constant
  __main__.py        # python -m support
  api_key.py         # Resolves ANTHROPIC_API_KEY from env, file, or default
  cli.py             # CLI entry points
  db.py              # SQLite layer
  observe.py         # Observer — CC Stop hook entrypoint
  reflect.py         # Reflector — synthesizes observations → prose
  prompts.py         # System/user prompts for observer and reflector
  session_parser.py  # Parses CC session JSONL into message list
  slugs.py           # cc_slug() and memory_slug() derivation
scripts/
  bootstrap-project.sh  # Creates CLAUDE.md in a new project
skills/
  load-context.md      # Example skill file loaded by any agent
tests/
  test_*.py          # Unit tests — mock API calls
```

## Design Specs

- Original: `docs/specs/2026-03-18-observational-memory-design.md`
- SQLite migration: `docs/specs/2026-04-13-sqlite-migration-pip-package.md`
