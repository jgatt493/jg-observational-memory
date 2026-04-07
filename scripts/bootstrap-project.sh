#!/bin/bash
# bootstrap-project.sh — Creates a CLAUDE.md for a new project pointing to the observational memory system.
# Usage: Run from the root of a project directory.

set -e

if [ -f "CLAUDE.md" ]; then
    echo "CLAUDE.md already exists in this directory. Skipping."
    exit 0
fi

cat > CLAUDE.md << 'CLAUDE_EOF'
# Project Context

## Observational Memory

This project uses Jeremy's observational memory system. Load the skill file to get behavioral context:

Skill: `~/Projects/jg-observational-memory/skills/jg-context.md`

Follow the instructions in the skill to load global and project-specific rules before starting work.
CLAUDE_EOF

echo "Created CLAUDE.md with observational memory reference."
