# Changelog

## 0.1.0 — 2026-04-21

Initial release.

### Features

- **Observer pipeline** — Claude Code Stop hook parses session transcripts and extracts behavioral observations (preferences, corrections, patterns, decisions) via Claude Haiku
- **Reflector pipeline** — synthesizes accumulated observations into tiered prose profiles (core rules + contextual annotations) per project and globally
- **Tiered durability** — observations tagged as durable, contextual, or incident; reflector separates core behavioral rules from evolving context
- **SQLite storage** — local database at `~/.observational-memory/memory.db` with tables for observations, interaction styles, sessions, and reflections
- **Interaction style scoring** — 7-axis scoring (expert, inquisitive, architectural, precise, scope_aware, risk_conscious, ai_led) per session
- **CLI commands** — `om install`, `om uninstall`, `om backfill`, `om reflect`, `om observe-messages`
- **Short alias** — `om` works as a shorthand for `observational-memory`
- **Backfill** — process all past Claude Code sessions with progress stats
- **External integration** — pipe conversations from any source via `om observe-messages`
- **Deduplication** — observer feeds existing observations into prompt to avoid extracting duplicates; reflector deduplicates project reflections against global profile
- **Line-based checkpointing** — resumed sessions only process new messages
- **Ephemeral session filtering** — skips temporary worktree sessions
- **API key flexibility** — supports env var, file path, or `~/.observational-memory/.api-key` with masked interactive input during install
- **Skill file** — included skill for loading profiles into any AI agent session
