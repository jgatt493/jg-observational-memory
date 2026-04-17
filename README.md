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
observational-memory observe-messages <slug>  # observe messages from stdin (JSON array)
```

## External Integration

Pipe conversations from any source (Discord bots, chat services, etc.):

```bash
echo '[{"role":"user","content":"..."},{"role":"assistant","content":"..."}]' \
  | observational-memory observe-messages my-project
```

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
