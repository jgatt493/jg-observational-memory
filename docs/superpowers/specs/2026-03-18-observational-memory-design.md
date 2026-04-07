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
│   │   ├── .observed-sessions              # Newline-delimited list of processed session IDs
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
└── docs/
    └── superpowers/specs/
        └── 2026-03-18-observational-memory-design.md
```

---

## Slug Conventions

Two slug concepts are used. It is important not to conflate them:

**CC slug** — Claude Code's internal project identifier. Derived by replacing all `/` in the full working directory path with `-`. Used only to locate the CC session transcript file.
- Example: `/Users/jeremygatt/Projects/dg2` → `-Users-jeremygatt-Projects-dg2`
- The leading `-` is correct and intentional — do **not** strip it. CC slug normalization is different from memory slug normalization.
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

**Catch-up for missed sessions:** The Stop hook only fires on clean agent stops — killed terminals skip it. To handle this, the Observer maintains `memory/logs/.observed-sessions` (a newline-delimited list of session IDs already processed). On each run, after processing the current session, the Observer scans `~/.claude/projects/{cc-slug}/` for any `.jsonl` session files whose IDs are not in `.observed-sessions` and processes them too. This makes the system self-healing — missed sessions are caught up on the next clean stop.

**Error handling:** All errors caught. Logged to `memory/logs/errors.log` with timestamp. Script always exits 0 — observation is best-effort and must never block the user session.

**Extraction prompt:** Stub for phase 1. Returns JSON array of observation objects with fields `scope`, `type`, `content`. Prompt quality is a separate workstream.

### 2. Reflector (`observer/reflect.py`)

**Trigger:** Invoked as fire-and-forget subprocess by Observer, or manually via `python observer/reflect.py {memory-slug}`. Pass `global` as the slug to reflect the global log.

**Processing unprocessed entries:** The cursor file at `memory/logs/.cursors/{memory-slug}` stores a 1-based line number — the last line that was included in a previous reflection. Line `cursor + 1` through EOF are unprocessed. A cursor of `0` (or missing file) means all entries are unprocessed.

**Synthesized file paths:**
- Project: `memory/projects/{slug}.md`
- Global: `memory/global.md` (not inside `memory/projects/`)

**Behavior:**
1. Read cursor file (`memory/logs/.cursors/{slug}`). Lines `cursor+1` through EOF are unprocessed.
2. Read the synthesized `.md` file for this slug (see paths above) if it exists — this is the current state to update.
3. Call `claude-haiku-4-5-20251001` with both the existing prose and the unprocessed entries. The prompt includes a hard constraint: output must not exceed 2000 tokens (~8000 chars). If existing prose + new material would exceed this, the model must compress the existing prose as part of the same rewrite. Output is a single revised dense prose document (full rewrite, not an append).
4. `correction` type entries are prefixed with `[CORRECTION]` in the prompt. The Reflector prompt instructs the model to treat these as firm rules, not soft preferences.
5. Validate output length (`len(text) / 4 <= 2000`). If it still exceeds, make one retry call asking for further compression. If that also fails, write anyway and log a warning.
6. Overwrite the synthesized `.md` file with the validated output.
7. Archive the entire active log file to `memory/logs/archive/{slug}-{iso-timestamp}.jsonl`.
8. Rewrite the active log to contain only the last 20 entries (by line position) from the file. These are context seeds for the next cycle. All of these entries have now been reflected, but they provide continuity. Reset cursor to `0`.

**Note on step 8:** Entries beyond the last 20 are not lost — their content has been synthesized into the `.md` file and the full raw log is preserved in the archive. The 20 seeds provide continuity context for the next reflection, not completeness.

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
  → add session ID to memory/logs/.observed-sessions
  → scan ~/.claude/projects/{cc-slug}/ for unobserved sessions → process those too
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

## Interaction Style Scoring

In addition to observations, the Observer extracts an **interaction style profile** per session — 7 axes scored 0.0–1.0 based on conversation content (not metadata like commit counts).

### Axes

| Axis | Signal |
|---|---|
| `expert` | Gives specific instructions, uses domain terminology, corrects the AI's approach, short directive prompts |
| `inquisitive` | Asks why/how, explores options, wants explanations before acting |
| `architectural` | Thinks in systems, asks about trade-offs and downstream effects, references other services/dependencies |
| `precise` | References specific files/functions/lines, describes exact expected behavior, small targeted changes |
| `scope_aware` | Pushes back on over-engineering, says "not now" or "out of scope", YAGNI instincts |
| `risk_conscious` | Asks about failure modes, flags security/migration/data concerns, thinks about rollback |
| `ai_led` | Defers decisions to the agent, asks for recommendations, "what do you think?", lets agent choose paths |

### JSONL Record

The Observer appends one additional record per session with `type: "interaction_style"`:

```json
{
  "ts": "2026-03-18T10:23:00Z",
  "session": "abc123",
  "project": "dg2",
  "scope": "project",
  "type": "interaction_style",
  "content": {
    "expert": 0.8,
    "inquisitive": 0.2,
    "architectural": 0.6,
    "precise": 0.9,
    "scope_aware": 0.4,
    "risk_conscious": 0.3,
    "ai_led": 0.1,
    "domain": "frontend"
  }
}
```

The `domain` field is a short label the Observer infers from the conversation (e.g., "frontend", "rust/networking", "infrastructure", "data-pipeline"). This allows the Reflector to build per-domain interaction profiles over time.

### Reflector Integration

The Reflector synthesizes interaction style records into the dense prose alongside behavioral rules:

```
interaction-style: frontend(expert, precise, scope-aware) — gives exact instructions, actively prunes scope creep.
rust/networking(inquisitive, ai-led, architectural) — learning the domain but thinks in systems, defers architectural decisions.
```

Only axes scoring >= 0.5 on average across sessions for a domain are included in the synthesized prose. This prevents noise from one-off sessions.

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
