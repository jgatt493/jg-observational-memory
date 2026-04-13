"""Reflector: synthesizes observations into dense compressed prose."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import anthropic

from observational_memory.prompts import REFLECTOR_SYSTEM_PROMPT, REFLECTOR_USER_PROMPT
from observational_memory.db import (
    get_observations_for_project,
    get_global_observations,
    get_all_projects,
    upsert_reflection,
)

MEMORY_ROOT = os.path.expanduser("~/.observational-memory/memory")
ERROR_LOG = os.path.expanduser("~/.observational-memory/errors.log")
MODEL = "claude-haiku-4-5-20251001"
MAX_CHARS = 8000  # ~2000 tokens


def log_error(msg: str):
    os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
    with open(ERROR_LOG, "a") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")


def read_synthesized_prose(md_path: str) -> str:
    try:
        return open(md_path).read()
    except FileNotFoundError:
        return ""


def validate_token_length(text: str) -> bool:
    return len(text) <= MAX_CHARS


def compress_prose(prose: str) -> str:
    """Ask Haiku to compress prose that exceeds the size limit."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system="You are a compression agent. Take the provided text and compress it to fit within 8000 characters while preserving all important behavioral rules. Maintain the dense prose format with topic-prefix labels. Prioritize [CORRECTION] items.",
        messages=[
            {"role": "user", "content": f"Compress this text to under 8000 characters:\n\n{prose}"}
        ],
    )
    return response.content[0].text


def synthesize(existing_prose: str, entries: list[dict]) -> str:
    """Call Haiku to synthesize observations into dense prose."""
    observations_text = "\n".join(
        f"{'[CORRECTION] ' if e.get('type') == 'correction' else ''}{e.get('content', '')}"
        for e in entries
    )
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=REFLECTOR_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": REFLECTOR_USER_PROMPT.format(
                existing_prose=existing_prose or "(no existing rules)",
                observations=observations_text,
            )}
        ],
    )
    return response.content[0].text


def get_max_observation_id(slug: str) -> int:
    """Get the max observation ID for a project (used for last_observation_id tracking)."""
    from observational_memory.db import get_connection
    conn = get_connection()
    try:
        if slug == "global":
            row = conn.execute(
                "SELECT MAX(id) FROM observations WHERE scope = 'global'"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT MAX(id) FROM observations WHERE project = ?", (slug,)
            ).fetchone()
        return row[0] if row and row[0] else 0
    finally:
        conn.close()


def reflect_slug(slug: str, entries: list[dict], md_path: str | None = None):
    """Run reflection for a single slug with given entries."""
    if not entries:
        return

    if md_path is None:
        if slug == "global":
            md_path = os.path.join(MEMORY_ROOT, "global.md")
        else:
            md_path = os.path.join(MEMORY_ROOT, "projects", f"{slug}.md")

    existing_prose = read_synthesized_prose(md_path)
    new_prose = synthesize(existing_prose, entries)

    if not validate_token_length(new_prose):
        log_error(f"Synthesis for {slug} exceeded {MAX_CHARS} chars ({len(new_prose)}), retrying with compression")
        new_prose = compress_prose(new_prose)
        if not validate_token_length(new_prose):
            log_error(f"Synthesis for {slug} still exceeds limit after retry ({len(new_prose)}), writing anyway")

    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w") as f:
        f.write(new_prose)

    try:
        max_id = get_max_observation_id(slug)
        upsert_reflection(slug, new_prose, len(entries), max_id)
    except Exception as e:
        log_error(f"Failed to upsert reflection for {slug}: {e}")

    print(f"  {slug}: {len(entries)} observations -> {len(new_prose)} chars")


def main():
    reflect_all = "--all" in sys.argv
    slug = None
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            slug = arg
            break

    if reflect_all:
        projects = get_all_projects()
        print(f"Reflecting {len(projects)} projects + global...")
        global_entries = get_global_observations()
        reflect_slug("global", global_entries)
        for project in projects:
            entries = get_observations_for_project(project)
            reflect_slug(project, entries)
        print("Done.")
    elif slug:
        if slug == "global":
            entries = get_global_observations()
        else:
            entries = get_observations_for_project(slug)
        reflect_slug(slug, entries)
    else:
        log_error("reflect.py requires a slug argument or --all")

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error(f"Reflector fatal error: {e}")
    sys.exit(0)
