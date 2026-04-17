"""Reflector: synthesizes observations into dense compressed prose."""
from __future__ import annotations

import os
import sys

import anthropic

from observational_memory.api_key import resolve_api_key
from observational_memory.config import MEMORY_ROOT, MODEL, log_error
from observational_memory.prompts import REFLECTOR_SYSTEM_PROMPT, REFLECTOR_USER_PROMPT
from observational_memory.db import (
    get_connection,
    get_observations_for_project,
    get_global_observations,
    get_all_projects,
    upsert_reflection,
)

MAX_CHARS = 8000  # ~2000 tokens


def read_synthesized_prose(md_path: str) -> str:
    try:
        with open(md_path) as f:
            return f.read()
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


def parse_tiered_output(text: str) -> tuple[str, str | None]:
    """Parse reflector output into core and contextual sections.

    Returns (core_prose, context_prose_or_None).
    Fallback: if delimiters not found, treat entire response as core.
    """
    core_marker = "===CORE==="
    ctx_marker = "===CONTEXTUAL==="

    if core_marker not in text:
        log_error("Reflector output missing ===CORE=== delimiter, treating as core")
        return text.strip(), None

    if ctx_marker in text:
        parts = text.split(ctx_marker, 1)
        core = parts[0].replace(core_marker, "").strip()
        context = parts[1].strip()
        return core, context if context else None
    else:
        core = text.replace(core_marker, "").strip()
        return core, None


def synthesize(existing_core_prose: str, existing_context_prose: str, entries: list[dict]) -> str:
    """Call Haiku to synthesize observations into tiered prose."""
    observations_text = "\n".join(
        f"[{e.get('durability', 'unknown')}] "
        f"{'[CORRECTION] ' if e.get('type') == 'correction' else ''}"
        f"{e.get('content', '')} "
        f"(trigger: {e.get('trigger_summary', 'unknown')})"
        for e in entries
    )
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        system=REFLECTOR_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": REFLECTOR_USER_PROMPT.format(
                existing_core_prose=existing_core_prose or "(no existing rules)",
                existing_context_prose=existing_context_prose or "(no existing context)",
                observations=observations_text,
            )}
        ],
    )
    return response.content[0].text


def get_max_observation_id(slug: str) -> int:
    """Get the max observation ID for a project (used for last_observation_id tracking)."""
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

    base, ext = os.path.splitext(md_path)
    context_path = f"{base}_context{ext}"

    existing_core = read_synthesized_prose(md_path)
    existing_context = read_synthesized_prose(context_path)

    raw_output = synthesize(existing_core, existing_context, entries)
    core_prose, context_prose = parse_tiered_output(raw_output)

    # Validate and compress core section only
    if not validate_token_length(core_prose):
        log_error(f"Core for {slug} exceeded {MAX_CHARS} chars ({len(core_prose)}), compressing")
        core_prose = compress_prose(core_prose)
        if not validate_token_length(core_prose):
            log_error(f"Core for {slug} still exceeds limit after compression ({len(core_prose)}), writing anyway")

    # Write core file
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w") as f:
        f.write(core_prose)

    # Write context file (only if non-empty), remove stale context file if no contextual section
    if context_prose:
        with open(context_path, "w") as f:
            f.write(context_prose)
    elif os.path.exists(context_path):
        os.remove(context_path)

    try:
        max_id = get_max_observation_id(slug)
        upsert_reflection(slug, core_prose, len(entries), max_id, context_prose=context_prose)
    except Exception as e:
        log_error(f"Failed to upsert reflection for {slug}: {e}")

    print(f"  {slug}: {len(entries)} observations -> {len(core_prose)} chars core" +
          (f", {len(context_prose)} chars context" if context_prose else ""))


def main():
    resolve_api_key()
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
