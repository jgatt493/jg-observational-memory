#!/bin/bash
# bootstrap-project.sh — Creates a CLAUDE.md for a new project pointing to the observational memory system.
# Usage: Run from the root of a project directory.
# Requires: pip install observational-memory

set -e

if [ -f "CLAUDE.md" ]; then
    echo "CLAUDE.md already exists in this directory. Skipping."
    exit 0
fi

cat > CLAUDE.md << 'CLAUDE_EOF'
# Project Context

## Observational Memory

This project uses observational memory. Load the behavioral context before starting work:

1. Read `~/.observational-memory/memory/global.md` for global behavioral rules.
2. Derive the project slug from this directory's basename (lowercase, special chars → `-`).
3. If `~/.observational-memory/memory/projects/{slug}.md` exists, read it too.
4. Treat both as firm behavioral rules — project overrides global on conflict.
CLAUDE_EOF

echo "Created CLAUDE.md with observational memory reference."
