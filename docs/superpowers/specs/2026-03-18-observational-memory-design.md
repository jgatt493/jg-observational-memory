# Observational Memory System — Design Spec

**Date:** 2026-03-18
**Status:** Approved (observer/reflector extraction prompts are stubs — quality iteration is a separate workstream)

---

## Overview

A personal observational memory system inspired by Mastra's OM pattern. Two background scripts (Observer and Reflector) maintain a compressed memory of Jeremy's preferences, corrections, and working patterns — per-project and globally — in a format any AI agent can read.

The system is portable: no lock-in to Claude Code or any single agent medium. A skill file acts as the universal interface. Files are plain markdown (synthesized) and JSONL (raw logs), stored in this repository.

---

## Goals

- Build up behavioral rules organically from observation rather than manually
- Per-project memory (tech stack decisions, domain patterns, recurring corrections)
- Global memory ("me-isms" that apply everywhere — testing philosophy, git rules, etc.)
- Accessible to any agent medium (Claude Code, Cursor, etc.) via a skill file
- Token-efficient: dense compressed prose for injection, JSONL for raw logging

---

## File Structure

```
jg-observational-memory/
├── memory/
│   ├── global.md                              # Cross-project me-isms (synthesized prose)
│   ├── logs/
│   │   ├── global.jsonl                       # Raw cross-project observation log
│   │   ├── .cursors/
│   │   │   ├── global                         # Line count of last processed global entry
│   │   │   └── {memory-slug}                  # Line count of last processed entry per project
│   │   ├── projects/
│   │   │   └── {memory-slug}.jsonl            # Raw per-project observation log
│   │   └── archive/
│   │       └── {memory-slug}-{timestamp}.jsonl # Archived entries after reflection
│   └── projects/
│       └── {memory-slug}.md                   # Synthesized prose per project
├── skills/
│   └── jg-context.md                         # Universal skill loaded by any agent
├── observer/
│   ├── observe.py                             # Called by CC Stop hook
│   └── reflect.py                            # Consolidates JSONL → dense prose
├── scripts/
│   └── bootstrap-project.sh                  # Creates CLAUDE.md for a new project
├── ui/
│   ├── server.js                              # Fastify API server
│   └── src/                                  # Vite + React frontend
└── docs/
    └── superpowers/specs/
        └── 2026-03-18-observational-memory-design.md
```

---

## Slug Conventions

Two slug concepts are used. It is important not to conflate them:

**CC slug** — Claude Code's internal project identifier. Derived by replacing all `/` in the full working directory path with `-`. Used only to locate the CC session transcript file.
- Example: `/Users/jeremygatt/Projects/dg2` → `-Users-jeremygatt-Projects-dg2`
- Used in: `~/.claude/projects/{cc-slug}/{session-id}.jsonl`

**Memory slug** — Our own identifier for memory files. Derived from the working directory basename: lowercase, spaces and special characters replaced with `-`, leading/trailing `-` stripped.
- Example: `/Users/jeremygatt/Projects/DG Chat Server` → `dg-chat-server`
- Used in: `memory/projects/{memory-slug}.md`, `memory/logs/projects/{memory-slug}.jsonl`

---

## Components

### 1. Observer (`observer/observe.py`)

**Trigger:** Claude Code `Stop` hook. Receives JSON payload on stdin containing `session_id` and `cwd` (working directory).

**Behavior:**
1. Derive CC slug from `cwd` (replace `/` with `-`) to locate `~/.claude/projects/{cc-slug}/{session-id}.jsonl`
2. Derive memory slug from `cwd` basename (normalize as above)
3. Parse session JSONL to extract user messages and agent responses
4. Call `claude-haiku-4-5-20251001` with the stub extraction prompt
5. For each observation returned, determine `scope`: `"project"` or `"global"` (decided by the extraction prompt based on content generality)
6. Append `scope: "project"` records to `memory/logs/projects/{memory-slug}.jsonl`
7. Append `scope: "global"` records to `memory/logs/global.jsonl`
8. Read cursor files to determine unprocessed entry counts independently for the project log and the global log. For each log where unprocessed entries exceed 100, invoke `reflect.py {slug}` as a separate fire-and-forget subprocess. Project log → `reflect.py {memory-slug}`. Global log → `reflect.py global`. Both may be invoked in the same session if both thresholds are exceeded.

**Error handling:** All errors caught. Logged to `memory/logs/errors.log` with timestamp. Script always exits 0 — observation is best-effort and must never block the user session.

**Extraction prompt:** Stub for phase 1. Returns JSON array of observation objects with fields `scope`, `type`, `content`. Prompt quality is a separate workstream.

### 2. Reflector (`observer/reflect.py`)

**Trigger:** Invoked as fire-and-forget subprocess by Observer, or manually via `python observer/reflect.py {memory-slug}`. Pass `global` as the slug to reflect the global log.

**Processing unprocessed entries:** The cursor file at `memory/logs/.cursors/{memory-slug}` stores the line count of the last processed entry. Unprocessed entries are all lines after that cursor. After reflection, the cursor is updated.

**Synthesized file paths:**
- Project: `memory/projects/{slug}.md`
- Global: `memory/global.md` (not inside `memory/projects/`)

**Behavior:**
1. Read cursor file (`memory/logs/.cursors/{slug}`) to get line count of last processed entry. All lines after that index are unprocessed.
2. Read the synthesized `.md` file for this slug (see paths above) if it exists — this is the current state to update.
3. Call `claude-haiku-4-5-20251001` with both the existing prose and the unprocessed entries; produce a single revised dense prose document (full rewrite, not an append).
4. `correction` type entries are prefixed with `[CORRECTION]` in the prompt. The Reflector prompt instructs the model to treat these as firm rules, not soft preferences.
5. Overwrite the synthesized `.md` file with the new output.
6. Archive: write all entries from line 1 through the cursor (the previously-processed entries) to `memory/logs/archive/{slug}-{iso-timestamp}.jsonl`. The unprocessed entries stay in the active log.
7. Truncate the active log to retain only the last 20 entries (by timestamp) from the unprocessed batch. These become the context seed for the next reflection cycle. Reset the cursor file to `0` — all retained entries are now unprocessed seeds.
8. If synthesized output would exceed 2000 tokens (estimated as `len(text) / 4`), the Reflector must compress the existing prose further as part of the same rewrite call before writing.

**Archive naming for global log:** `memory/logs/archive/global-{iso-timestamp}.jsonl`

**Error handling:** Errors logged to `memory/logs/errors.log`, never fatal.

### 3. Skill (`skills/jg-context.md`)

A portable markdown skill loadable by any agent. Instructions:

1. Read `memory/global.md` from `~/Projects/jg-observational-memory/` — **this path is hardcoded for this machine**. If the repo is cloned to a different path, update this line accordingly.
2. Derive memory slug from current working directory basename (lowercase, special chars → `-`)
3. If `memory/projects/{slug}.md` exists, read it
4. Inject global content first, then project content
5. When project and global rules conflict, **project rules take precedence** — the model should treat later-injected project content as the authoritative override
6. Treat all content as behavioral rules, not suggestions

**For non-CC agents:** Wiring (e.g. adding to a Cursor system prompt) is manual per tool, but the skill behavior is identical.

### 4. CC Bootstrap (`scripts/bootstrap-project.sh`)

A shell script run manually once when starting work in a new project directory. Creates a `CLAUDE.md` in the current directory with:
- An instruction to load the `jg-context` skill from `~/Projects/jg-observational-memory/skills/jg-context.md`
- The global CC memory entry (added once to `~/.claude/CLAUDE.md`) reminds the user to run this script for any new project

### 5. Web UI (`ui/`)

**Architecture:** Fastify API server (`ui/server.js`) reads memory files from disk and exposes a REST API. Vite + React frontend. In development: Vite on port 5173, Fastify on port 3001, Vite proxy config routes `/api` to Fastify. In production: Fastify serves compiled `ui/dist/` bundle.

**Token count calculation:** Estimated as `Math.floor(text.length / 4)` — character heuristic, no external dependencies.

**Views:**
- **Dashboard:** Total estimated token count across all memory files, number of projects tracked, total observations logged (sum of all JSONL line counts), last observation timestamp
- **Project view:** Current synthesized prose, raw JSONL log entries with timestamp/type filters, estimated token count
- **Global view:** Same as project view for `global.md` / `global.jsonl`

Read-only. No write operations from the UI.

---

## Data Flow

### Session End

```
CC Stop hook fires → JSON payload (session_id, cwd) to observe.py stdin
  → derive CC slug (path → dashes) to find session transcript
  → derive memory slug (basename normalization) for memory files
  → read ~/.claude/projects/{cc-slug}/{session-id}.jsonl
  → call Haiku: extract observations → [{scope, type, content}]
  → append project-scoped observations to memory/logs/projects/{slug}.jsonl
  → append global-scoped observations to memory/logs/global.jsonl
  → check cursors; if unprocessed > 100 → fire-and-forget reflect.py {slug}
  → errors → memory/logs/errors.log; always exit 0
```

### Reflection

```
reflect.py {slug}
  → read cursor → identify unprocessed entries (lines after cursor)
  → read existing memory/projects/{slug}.md OR memory/global.md (for slug=global)
  → call Haiku: full prose rewrite incorporating existing state + new entries
    ([CORRECTION] entries → treated as firm rules)
  → overwrite synthesized .md file
  → archive entries 1..cursor → memory/logs/archive/{slug}-{timestamp}.jsonl
  → truncate active log to last 20 unprocessed entries; reset cursor to 0
```

### Session Start (any agent)

```
Agent loads jg-context skill
  → reads memory/global.md
  → derives memory slug from working directory basename
  → if memory/projects/{slug}.md exists → reads it
  → injects global first, project second (project overrides on conflict)
  → treats both as behavioral rules
```

---

## JSONL Record Schema

```json
{
  "ts": "2026-03-18T10:23:00Z",
  "session": "abc123",
  "project": "dg2",
  "scope": "project | global",
  "type": "preference | correction | pattern | decision",
  "content": "user corrected agent: always use feature branches, never commit to main"
}
```

**Observation types:**

| Type | Meaning |
|---|---|
| `preference` | Something the user expressed they like or dislike |
| `correction` | The user had to correct or re-explain something to the agent |
| `pattern` | A recurring behavior or approach observed across the session |
| `decision` | A project-specific decision made (architecture, tooling, domain design) |

---

## Dense Compressed Prose Format

Flat, minimal prose — no headers, minimal punctuation, maximum information density. Target ~150–200 tokens per thematic group. No bullet lists. Labeled by topic prefix. Maximum file size ~2000 tokens (estimated as `len / 4`).

**Example `global.md`:**
```
testing: backend(python,rust) always requires test cases. frontend: no unit tests;
e2e playwright only when explicitly asked. if project is frontend-only, skip tests entirely.

git: always feature branches. never commit to main. never reuse a merged branch.
```

---

## Model

Both Observer and Reflector pin to `claude-haiku-4-5-20251001`. Version is explicit in all API calls to prevent behavior drift.

---

## Out of Scope (Phase 1)

- Observer/Reflector extraction prompt quality (high-value TODO, separate iteration)
- Vector/semantic retrieval (phase 2 candidate if files grow large — sqlite-vec)
- Multi-machine sync (git push of this repo is sufficient for now)
- Per-tool setup for non-CC agents (skill file handles behavior; wiring is manual)
