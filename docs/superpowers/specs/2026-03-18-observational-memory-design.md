# Observational Memory System — Design Spec

**Date:** 2026-03-18
**Status:** Approved

---

## Overview

A personal observational memory system inspired by Mastra's OM pattern. Two background agents (Observer and Reflector) maintain a compressed memory of Jeremy's preferences, corrections, and working patterns — per-project and globally — in a format any AI agent can read.

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
│   ├── global.md                    # Cross-project me-isms (synthesized prose)
│   ├── logs/
│   │   ├── global.jsonl             # Raw cross-project observation log
│   │   └── projects/
│   │       ├── dg2.jsonl
│   │       └── {project-slug}.jsonl
│   └── projects/
│       ├── dg2.md                   # Synthesized prose per project
│       └── {project-slug}.md
├── skills/
│   └── jg-context.md               # Universal skill loaded by any agent
├── observer/
│   ├── observe.py                   # Called by CC session-stop hook
│   └── reflect.py                  # Consolidates JSONL → dense prose
├── ui/
│   ├── server.js                    # Fastify server (reads memory files from disk)
│   └── src/                         # Vite + React frontend
└── docs/
    └── superpowers/specs/
        └── 2026-03-18-observational-memory-design.md
```

---

## Components

### 1. Observer (`observer/observe.py`)

- Triggered by Claude Code session-stop hook
- Reads conversation history from the CC session
- Calls Claude Haiku API to extract observations about the user
- Appends structured records to the appropriate project JSONL log
- Cross-project observations also appended to `memory/logs/global.jsonl`
- If log exceeds 100 entries, automatically triggers the Reflector

**Note:** The observer extraction prompt is a known high-value TODO. The initial prompt will be a stub; quality iteration is a separate workstream.

### 2. Reflector (`observer/reflect.py`)

- Triggered automatically when JSONL log exceeds 100 entries, or manually
- Reads full JSONL log for a project (or global)
- Calls Claude Haiku to synthesize into dense compressed prose
- Overwrites `memory/projects/{slug}.md` (or `memory/global.md`)
- Archives processed JSONL entries, retaining last 20 raw entries for debugging
- Weights `correction` type observations more heavily than single-mention preferences

### 3. Skill (`skills/jg-context.md`)

- Portable markdown skill loadable by any agent (Claude Code, Cursor, etc.)
- Instructs the agent to:
  - Always read `memory/global.md`
  - Detect project slug from current working directory name
  - Load `memory/projects/{slug}.md` if it exists
  - Treat both files as behavioral rules, not suggestions

### 4. Claude Code Bootstrap

- A global CC memory entry instructs: at the start of any new project, create a `CLAUDE.md` that loads the `jg-context` skill and points to this repository
- Self-propagating: every new CC project inherits the memory system automatically

### 5. Web UI (`ui/`)

- Vite + React frontend, no external UI library
- Small Fastify server reads memory files from disk and serves them to the frontend
- Read-only — no write operations from the UI
- **Dashboard view:** total token count across all files, projects tracked, total observations, last observation timestamp
- **Project view:** synthesized prose, raw JSONL log with timestamp/type filters, token count
- **Global view:** same as project view for `global.md` / `global.jsonl`

---

## Data Flow

### Session End

```
CC session stops
  → session-stop hook fires observe.py
  → observe.py reads conversation history from CC session
  → calls Claude Haiku: extract observations about the user
  → appends N records to memory/logs/projects/{slug}.jsonl
  → cross-project observations → memory/logs/global.jsonl
  → if log > 100 entries → triggers reflect.py
```

### Reflection

```
reflect.py reads full JSONL log
  → calls Claude Haiku: synthesize into dense compressed prose rules
  → overwrites memory/projects/{slug}.md (or global.md)
  → archives processed entries, retains last 20 raw
```

### Session Start (any agent)

```
Agent loads jg-context skill
  → reads memory/global.md
  → detects project slug from working directory
  → if memory/projects/{slug}.md exists → reads it
  → treats both files as behavioral rules for the session
```

---

## JSONL Record Schema

```json
{
  "ts": "2026-03-18T10:23:00Z",
  "session": "abc123",
  "project": "dg2",
  "type": "preference | correction | pattern | decision",
  "content": "user corrected agent: always use feature branches, never commit to main"
}
```

**Observation types:**
- `preference` — something the user expressed they like/dislike
- `correction` — the user had to correct or re-explain something to the agent
- `pattern` — a recurring behavior or approach noticed across the session
- `decision` — a project-specific decision made (architecture, tooling, etc.)

Corrections are weighted more heavily during reflection — if the user had to say something twice, it's a stronger signal.

---

## Memory File Format

Dense compressed prose, not verbose markdown. Prioritizes token efficiency.

**Example `global.md`:**
```
testing: backend(python,rust) always requires test cases. frontend: no unit tests;
e2e playwright only when explicitly asked. if project is frontend-only, skip tests entirely.

git: always feature branches. never commit to main. never reuse a merged branch.
```

---

## Out of Scope (Phase 1)

- Observer prompt quality (high-value TODO, separate iteration)
- Vector/semantic retrieval (phase 2 if files grow large — sqlite-vec candidate)
- Multi-machine sync (git push of this repo is sufficient for now)
- Per-tool setup for non-CC agents (skill file handles behavior; wiring is manual)
