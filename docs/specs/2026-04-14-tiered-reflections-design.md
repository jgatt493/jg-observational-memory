# Tiered Reflections — Observer & Reflector Improvements

**Date:** 2026-04-14
**Status:** Approved

## Problem

The reflector treats all observations equally. A frustration from a specific npm bug gets the same weight as "always use feature branches." The output is a flat wall of rules with no provenance, no categorization, and no way to distinguish durable preferences from circumstantial reactions. Incident-specific responses get promoted to permanent behavioral rules.

## Approach

Keep the existing two-stage pipeline (observer → reflector). No new stages. Make each stage smarter with richer metadata and tiered output.

## Observer Changes

### New Observation Fields

Each observation gains two new metadata fields:

```json
{
  "scope": "global",
  "type": "correction",
  "content": "User frustrated by repeated interruptions...",
  "durability": "incident",
  "trigger": "npm version bug causing CC session crashes"
}
```

**`durability`** — one of three values:
- `durable` — stable preference or rule that applies in any future session
- `contextual` — tied to how the user works in a specific project or phase, may evolve
- `incident` — reaction to a specific event, bug, or frustration that may not recur

**`trigger`** — short free-text annotation of what caused the observation. For durable rules: "repeated across sessions" or "explicitly stated as rule." For incidents: names the specific event. Stored in DB as `trigger_summary` column (since `trigger` is a SQL reserved word). The JSON field from Haiku is `trigger`; the code maps it to `trigger_summary` on insert.

### Schema Change

Two new columns on `observations`:

```sql
ALTER TABLE observations ADD COLUMN durability TEXT CHECK (durability IN ('durable', 'contextual', 'incident'));
ALTER TABLE observations ADD COLUMN trigger_summary TEXT;
```

### Observer Prompt Changes

- Add `durability` and `trigger` to the output JSON format
- Add classification guidance with examples:
  - `durable`: "User explicitly states 'always use feature branches'" → durable, trigger: "explicitly stated rule"
  - `contextual`: "User prefers script-based infra in this project" → contextual, trigger: "rejected HTTP service proposal"
  - `incident`: "User frustrated by CC timeouts" → incident, trigger: "npm version bug causing session crashes"
- Instruct Haiku: use `incident` when the observation is clearly tied to a one-time event; use `durable` when it's a pattern reinforced across the conversation or stated as a general rule; use `contextual` when it's project-specific or phase-specific.

**Important:** Observer durability tagging is best-effort. The observer sees a single session and cannot know whether something has been repeated across sessions. It classifies based on the language and context within that session. The reflector is the authoritative tier assignment mechanism — it sees all observations together and makes the final call on what's core vs contextual.

## Reflector Changes

### Tiered Output

The reflector produces two distinct sections separated by a delimiter:

```
===CORE===
git: Always feature branches, never main...
testing: Backend always requires tests...

===CONTEXTUAL===
[incident:npm-timeout-bug] User escalated about CC interruptions...
[contextual:data-platform] Prefers script-based infra over HTTP services...
```

### Core Section

- Goes into `global.md` or `projects/{slug}.md`
- 8K char cap
- Dense prose, same format as today
- Only `durable` observations belong here
- `incident` observations get promoted ONLY if they reveal an underlying durable preference (e.g., npm bug is incident, but "user doesn't want workarounds when there's an obvious bigger problem" is durable)

### Contextual Section

- Goes into `global_context.md` or `projects/{slug}_context.md`
- Uncapped but naturally dense
- Each entry annotated with `[durability:trigger]` prefix
- Contains incident-derived rules, contextual patterns, and provenance trail

### Promotion/Demotion Rules

The reflector manages movement between tiers:
- **Promote to core:** incident/contextual observations that have been reinforced by new observations across multiple sessions → extract the underlying principle, add to core
- **Demote to contextual:** entries in core that on re-evaluation appear incident-specific
- **Drop entirely:** stale incident entries that have not been reinforced — staleness is determined by the reflector's judgment based on observation position (earlier in the list = older) and whether newer observations reference or reinforce the same pattern. No explicit timestamp cutoff; the reflector uses its discretion.

### Reflector Prompt Changes

- System prompt updated with: tiered output format rules, promotion/demotion logic, 8K cap applies to core section only
- User prompt template gains two input placeholders: `{existing_core_prose}` and `{existing_context_prose}` (replacing the single `{existing_prose}`)
- Observations passed to reflector include durability and trigger fields: `[durable] content (trigger: ...)` format
- Explicitly instructed to output `===CORE===` and `===CONTEXTUAL===` sections on their own lines
- Given promotion/demotion rules as part of the system prompt

### Schema Change

New column on `reflections`:

```sql
ALTER TABLE reflections ADD COLUMN context_prose TEXT;
```

### Parsing the Tiered Output

The reflector response is split on `===CORE===` and `===CONTEXTUAL===` delimiters. Each delimiter appears on its own line with no surrounding whitespace.

**Parsing logic:**
1. Look for `===CORE===` and `===CONTEXTUAL===` in the response text
2. Split on these delimiters, strip whitespace from each section
3. **Fallback:** If delimiters are not found, treat the entire response as core prose and log a warning. Write no context file. This prevents a Haiku formatting failure from breaking the pipeline.
4. If `===CONTEXTUAL===` is missing but `===CORE===` is present, treat everything after `===CORE===` as core. No context file.
5. If `===CONTEXTUAL===` section is empty, skip writing the context file.

### Compression

The existing `compress_prose()` fallback applies only to the core section. If the core section exceeds 8K after synthesis, compress it independently. The contextual section is never compressed — it is either naturally dense or gets pruned by the reflector on subsequent runs.

### Updated Function Signatures

- `upsert_reflection(slug, prose, observation_count, last_observation_id, context_prose=None)` — new optional parameter for context prose
- `get_observations_for_project(project)` and `get_global_observations()` — must return `durability` and `trigger_summary` columns alongside existing fields so the reflector can use them

### File Writes

`reflect_slug()` writes two files per slug:
- `{slug}.md` — core rules (from `===CORE===` section)
- `{slug}_context.md` — contextual annotations (from `===CONTEXTUAL===` section, if non-empty)

## Skill Loading Changes

`jg-context.md` Step 2 updated:

1. Read `global.md` — core rules, apply as firm instructions
2. Read `global_context.md` — contextual annotations, apply as informational background
3. Derive project slug from cwd
4. Read `projects/{slug}.md` if exists — project core rules, firm instructions
5. Read `projects/{slug}_context.md` if exists — project contextual annotations, informational

**Key distinction:** Core files are rules. Context files explain *why* and flag things that might be evolving.

## Migration

Burn and rebuild:
1. Land code changes
2. Drop DB (`rm ~/.observational-memory/memory.db`)
3. `observational-memory install` (reinitialize clean DB with new schema)
4. `observational-memory backfill` (re-process all sessions with new observer prompt)
5. `observational-memory reflect --all` (produce tiered output)

No migration of existing data. All 159 sessions get re-observed from scratch with the new fields.

## Files Changed

- `src/observational_memory/prompts.py` — observer and reflector prompts
- `src/observational_memory/db.py` — new columns on observations and reflections
- `src/observational_memory/observe.py` — parse new fields from observer response
- `src/observational_memory/reflect.py` — parse tiered output, write two files per slug
- `skills/jg-context.md` — load context files alongside core files
- `tests/` — update tests for new fields and tiered output
