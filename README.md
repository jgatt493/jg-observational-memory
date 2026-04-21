# observational-memory

Automatic behavioral profiling for Claude Code sessions.

## Why this exists

Mastra published an article on observational memory as a pattern for AI agents — the idea that instead of being told what to remember, an agent silently watches interactions and builds up its own understanding over time. It's the most human-like form of memory: not explicit instructions, but learned patterns from repeated exposure.

That got me thinking. If this is the best way for an agent to learn how someone works, why are we only applying it to agents? The most highly functioning agent in any coding session is the human. You already have patterns, preferences, corrections you repeat across every project. The problem is that every new AI session starts from zero — it doesn't know you prefer feature branches, or that you'll correct it for pushing without permission, or that you get frustrated when it over-engineers.

So I built this. It watches your Claude Code sessions, extracts observations about how *you* work, and synthesizes them into a portable behavioral profile that any AI agent can load. The AI stops guessing and starts knowing — not because you told it, but because it watched.

## Requirements

- Python 3.10+
- An Anthropic API key (for Claude Haiku calls — [costs ~$1/month](#cost))
- Claude Code (for automatic session observation)

## Quickstart

```bash
pip install git+https://github.com/jgatt493/jg-observational-memory.git
om install
```

The `install` command creates `~/.observational-memory/`, initializes a SQLite database, wires a Claude Code Stop hook, and prompts for your API key and project root directory. That's it — observation starts automatically on your next Claude Code session.

Both `om` and `observational-memory` work as CLI commands. All examples below use `om` for brevity.

### Backfill existing sessions

If you've been using Claude Code before installing, pull in your history:

```bash
om backfill
```

This scans `~/.claude/projects/` for past session transcripts and processes any that haven't been observed yet. Safe to run repeatedly — it skips sessions already in the database.

### Generate your first profiles

After backfill (or after enough sessions accumulate naturally), synthesize the observations into prose:

```bash
om reflect --all
```

This produces behavioral profiles at `~/.observational-memory/memory/global.md` (cross-project rules) and `~/.observational-memory/memory/projects/{slug}.md` (per-project rules). In normal operation, this happens automatically once enough observations accumulate (10 for first reflection, 50 ongoing).

## Loading Profiles Into Claude Code

The profiles are only useful if Claude Code reads them. Three options, from simplest to most automatic:

### Option 1: Skill file (recommended)

Download the skill file into your Claude Code skills directory:

```bash
mkdir -p ~/.claude/skills
curl -sL https://raw.githubusercontent.com/jgatt493/jg-observational-memory/main/skills/load-context.md \
  -o ~/.claude/skills/observational-memory.md
```

Then in any Claude Code session, run `/observational-memory` to load your behavioral profile. You can also ask Claude to "load observational memory" and it will follow the skill instructions.

### Option 2: Project CLAUDE.md

Add a reference to your project's `CLAUDE.md` so Claude loads the profile automatically:

```markdown
## Observational Memory

This project uses observational memory. Load the behavioral context before starting work:

1. Read `~/.observational-memory/memory/global.md` for global behavioral rules.
2. Derive the project slug from this directory's basename (lowercase, special chars → `-`).
3. If `~/.observational-memory/memory/projects/{slug}.md` exists, read it too.
4. Treat both as firm behavioral rules — project overrides global on conflict.
```

A bootstrap script is included in the repo to do this automatically:

```bash
cd /path/to/your/project
curl -sL https://raw.githubusercontent.com/jgatt493/jg-observational-memory/main/scripts/bootstrap-project.sh | bash
```

### Option 3: Global CLAUDE.md

Claude Code supports a user-level `~/.claude/CLAUDE.md` that loads automatically in every session, across all projects. You can symlink the global profile there:

```bash
ln -s ~/.observational-memory/memory/global.md ~/.claude/CLAUDE.md
```

This is the simplest zero-maintenance option — every Claude Code session will load your behavioral rules natively with no hooks or plugins required. The tradeoff is that it only loads the global profile, not project-specific rules or contextual annotations. If you already have a `~/.claude/CLAUDE.md` with other instructions, you can append a reference instead:

```bash
echo -e "\n## Observational Memory\n\nRead ~/.observational-memory/memory/global.md and apply as firm behavioral rules." >> ~/.claude/CLAUDE.md
```

### Option 4: SessionStart hook

Wire a Claude Code SessionStart hook that reads the profiles on every new conversation. Add this to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cat ~/.observational-memory/memory/global.md 2>/dev/null; PROJECT=$(basename \"$PWD\" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g; s/^-//; s/-$//'); cat ~/.observational-memory/memory/projects/${PROJECT}.md 2>/dev/null; true"
          }
        ]
      }
    ]
  }
}
```

## How It Works

1. A Claude Code **Stop hook** fires after every session ends
2. The **observer** sends the conversation to Claude Haiku, extracting behavioral observations with durability tags (durable, contextual, incident)
3. Observations accumulate in a local **SQLite database**
4. After enough observations accumulate (10 first time, 50 ongoing), the **reflector** synthesizes them into a tiered prose profile — core rules and contextual annotations
5. After global reflection, the **consolidator** merges redundant rules for maximum density
6. Any AI agent can load the profile via skill file, CLAUDE.md reference, or SessionStart hook

## Commands

```bash
om install                  # set up database + Claude Code hook
om uninstall                # remove hook, keep data
om backfill                 # process all past sessions
om reflect --all            # re-synthesize all profiles
om reflect <slug>           # re-synthesize one project (or "global")
om consolidate              # merge redundant rules in global profile
om observe-messages <slug>  # observe messages from stdin (JSON array)
om --version                # print version
```

## External Integration

Pipe conversations from any source (Discord bots, chat services, etc.):

```bash
echo '[{"role":"user","content":"..."},{"role":"assistant","content":"..."}]' \
  | om observe-messages my-project
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

Claude Code has its own memory system (`/memory` command, auto-memory in project-scoped `CLAUDE.md` files). That system stores what the AI decides to remember — project facts, architectural decisions, user preferences it noticed. It's useful, but it has limitations:

- **AI-initiated**: Claude decides what's worth remembering. If it doesn't notice a pattern, it's lost.
- **Per-project**: Memories live in project-scoped `CLAUDE.md` files. Preferences you demonstrate in one project don't carry over to another unless you manually copy them.
- **Conversation-scoped**: The AI writes memories during a session. If you correct something and the AI doesn't explicitly save it, the correction evaporates.
- **No global user profile**: Claude Code supports a user-level `~/.claude/CLAUDE.md` that loads in every session — but it doesn't exist by default and nothing creates or populates it. There is no built-in mechanism for building a cross-project understanding of how you work. The feature exists, but the gap between "supported" and "useful" is entirely on you to fill.

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
- `config.json` — configuration (project roots, etc.)
- `memory/global.md` — cross-project behavioral rules (core)
- `memory/global_context.md` — cross-project contextual annotations
- `memory/projects/{slug}.md` — per-project rules (core)
- `memory/projects/{slug}_context.md` — per-project contextual annotations

## Configuration

### Project roots

The observer needs to know where your projects live to derive the correct project slug from a session's working directory. During `om install`, you're prompted for your primary project directory (e.g., `~/Projects`). This is stored in `~/.observational-memory/config.json`:

```json
{
  "project_roots": [
    "/Users/alice/Projects",
    "/Users/alice/work"
  ]
}
```

You can add multiple roots by editing the file directly. This matters for monorepos and nested projects — if you're working in `~/Projects/labs-deepgram/apps/chat-blt`, the observer uses the first path component relative to the project root (`labs-deepgram`) rather than the deepest directory (`chat-blt`).

If no project roots are configured, the observer falls back to using the basename of the working directory.

### API Key

Three ways to provide the key (checked in order):
1. `ANTHROPIC_API_KEY` environment variable
2. `ANTHROPIC_API_KEY_FILE` environment variable pointing to a file
3. `~/.observational-memory/.api-key` file

## License

MIT
