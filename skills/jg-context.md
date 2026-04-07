# jg-context — Personal Memory Skill

You are working with Jeremy Gatt. Before proceeding with any work, load his behavioral context.

## Instructions

1. Read `~/Projects/jg-observational-memory/memory/global.md` — these are global behavioral rules.
2. Derive the project slug from the current working directory basename: lowercase, replace non-alphanumeric characters with `-`, strip leading/trailing `-`.
3. Check if `~/Projects/jg-observational-memory/memory/projects/{slug}.md` exists. If it does, read it.
4. Apply both files as behavioral rules — not suggestions.
5. When global and project rules conflict, project rules take precedence.

## Important

- This path is hardcoded for this machine. If the repo moves, update the path above.
- If global.md does not exist yet, skip it — the memory system has not yet generated observations.
- Treat all loaded content as firm instructions for how to work with this user.
