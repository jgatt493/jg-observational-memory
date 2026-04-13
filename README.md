# observational-memory

Automatic behavioral profiling for Claude Code sessions.

Watches your Claude Code conversations, extracts observations about how you work (preferences, corrections, patterns), and synthesizes them into dense prose rules that any AI agent can load — so it already knows how you work.

## Install

```bash
pip install observational-memory
observational-memory install
```

Requires an `ANTHROPIC_API_KEY` in your shell environment.

## How it works

1. A Claude Code Stop hook fires after every session
2. The observer sends the conversation to Claude Haiku, extracting behavioral observations
3. Observations accumulate in a local SQLite database
4. After 100+ observations, the reflector synthesizes them into a dense prose profile
5. Any AI agent can load the profile via the included skill file

## Commands

```bash
observational-memory install       # set up database + Claude Code hook
observational-memory uninstall     # remove hook, keep data
observational-memory backfill      # process all past sessions
observational-memory reflect --all # re-synthesize all profiles
```

## Data

Everything lives at `~/.observational-memory/`:
- `memory.db` — SQLite database
- `memory/global.md` — cross-project behavioral rules
- `memory/projects/{slug}.md` — per-project rules
