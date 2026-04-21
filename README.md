# observational-memory

Automatic behavioral profiling for Claude Code sessions.

Watches your Claude Code conversations, extracts observations about how you work (preferences, corrections, patterns), and synthesizes them into dense prose rules that any AI agent can load — so it already knows how you work.

## Install

```bash
pip install observational-memory
observational-memory install
```

Requires an `ANTHROPIC_API_KEY` — set it in your shell environment, or put it in `~/.observational-memory/.api-key`.

## How it works

1. A Claude Code Stop hook fires after every session
2. The observer sends the conversation to Claude Haiku, extracting behavioral observations with durability tags (durable, contextual, incident)
3. Observations accumulate in a local SQLite database
4. After 10 observations (first time) or 50 (ongoing), the reflector synthesizes them into a tiered prose profile — core rules and contextual annotations
5. Any AI agent can load the profile via the included skill file or a SessionStart hook

## Commands

```bash
observational-memory install                  # set up database + Claude Code hook
observational-memory uninstall                # remove hook, keep data
observational-memory backfill                 # process all past sessions
observational-memory reflect --all            # re-synthesize all profiles
observational-memory consolidate             # merge redundant rules in global profile
observational-memory observe-messages <slug>  # observe messages from stdin (JSON array)
```

## External Integration

Pipe conversations from any source (Discord bots, chat services, etc.):

```bash
echo '[{"role":"user","content":"..."},{"role":"assistant","content":"..."}]' \
  | observational-memory observe-messages my-project
```

## What the Output Looks Like

After a few sessions, the reflector produces files like this:

**Core rules** (`global.md`) — dense behavioral instructions for any AI agent:

```
git: always feature branches, never commit to main, never reuse merged branches.

delegation: user delegates implementation with trust but expects clear scope
confirmation before execution. Mandatory progress notes before every exit.

root-cause-fixing: user dislikes workarounds that mask systemic problems.
Demands fixes to underlying root causes rather than band-aids.

testing: backend always requires tests. Frontend only requires E2E Playwright
when explicitly asked. Treats tests as immutable specification.
```

**Contextual annotations** (`global_context.md`) — provenance and evolving patterns:

```
[incident:npm-timeout-bug] User escalated about CC session crashes — repeated
across 3 sessions. Underlying preference promoted to core: rejects workarounds
for systemic issues.

[contextual:data-platform] Prefers script-based infra over HTTP services in
this project — rejected API proposal in favor of CLI tools.
```

## How This Compares to Claude Code's Built-in Memory

Claude Code has its own memory system (`/memory` command, auto-memory in `CLAUDE.md` project files). That system stores what the AI decides to remember — project facts, architectural decisions, user preferences it noticed. It's useful, but it has limitations:

- **AI-initiated**: Claude decides what's worth remembering. If it doesn't notice a pattern, it's lost.
- **Per-project**: Memories live in project-scoped `CLAUDE.md` files. Preferences you demonstrate in one project don't carry over to another unless you manually copy them.
- **Conversation-scoped**: The AI writes memories during a session. If you correct something and the AI doesn't explicitly save it, the correction evaporates.

Observational memory works differently:

- **Systematic**: Every session is processed. The observer extracts what happened, not what the AI thought was important.
- **Cross-project**: Global observations accumulate across all projects into a single behavioral profile.
- **Durable by design**: Observations are classified by durability (durable, contextual, incident) and stored in SQLite. The reflector synthesizes them into prose rules, promoting patterns that recur and demoting one-off incidents.
- **User-focused**: The observer only tracks how *you* work — preferences, corrections, communication style — never project facts or architecture decisions.

The two systems are complementary. Claude Code's memory handles project-specific context (file paths, architecture, conventions). Observational memory handles *you* — how you like to work, what you've corrected, what patterns you repeat across every project.

## Cost

Everything runs on Claude Haiku, which keeps costs negligible. Based on real usage (~150 sessions/month):

| Component | Calls/month | Est. cost |
|-----------|------------|-----------|
| Observer (per session) | ~150 | ~$0.80 |
| Reflector (per threshold) | ~12 | ~$0.15 |
| Consolidator (per global reflect) | ~6 | ~$0.06 |
| **Total** | | **~$1.00/month** |

That's about $0.007 per session. The observer is the bulk of the cost since it runs on every session, but Haiku's input pricing ($0.80/MTok) keeps even heavy users well under $2/month. The reflector and consolidator fire infrequently — only when enough new observations accumulate — so they're essentially free.

For comparison, a single medium-length Claude Sonnet conversation costs more than an entire month of observational memory.

## Session Discovery and Data Durability

The observer scans `~/.claude/projects/{slug}/` for session JSONL files one level deep — it picks up top-level session files but intentionally skips subagent transcripts nested in `{session_id}/subagents/`. Subagent sessions are AI-to-AI conversations with no direct user interaction, so they contain no behavioral signal worth extracting.

Claude Code manages its own session file lifecycle and prunes old JSONL files after roughly 30 days. This means the number of session files on disk stays roughly constant — new sessions appear, old ones get cleaned up.

This doesn't matter for observational memory. The Stop hook fires after every session ends, processing the transcript in real-time and writing observations to SQLite before Claude Code ever cleans up the file. The `om backfill` command exists as a safety net for sessions the hook missed (e.g., if the hook wasn't installed yet, or if it errored). Once a session is in the database, the JSONL file can disappear — all the behavioral data has already been extracted and is durable in SQLite.

## Data

Everything lives at `~/.observational-memory/`:
- `memory.db` — SQLite database
- `memory/global.md` — cross-project behavioral rules (core)
- `memory/global_context.md` — cross-project contextual annotations
- `memory/projects/{slug}.md` — per-project rules (core)
- `memory/projects/{slug}_context.md` — per-project contextual annotations

## API Key

Three ways to provide the key (checked in order):
1. `ANTHROPIC_API_KEY` environment variable
2. `ANTHROPIC_API_KEY_FILE` environment variable pointing to a file
3. `~/.observational-memory/.api-key` file

## License

MIT
