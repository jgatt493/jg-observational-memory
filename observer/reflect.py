"""Reflector: synthesizes JSONL observations into dense compressed prose."""
import json
import os
import shutil
import sys
from datetime import datetime, timezone

import anthropic

from observer.prompts import REFLECTOR_SYSTEM_PROMPT, REFLECTOR_USER_PROMPT

MEMORY_ROOT = os.path.join(os.path.dirname(__file__), "..", "memory")
MODEL = "claude-haiku-4-5-20251001"
MAX_CHARS = 8000  # ~2000 tokens
SEED_COUNT = 20


def log_error(msg: str):
    path = os.path.join(MEMORY_ROOT, "logs", "errors.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")


def read_cursor(cursor_path: str) -> int:
    try:
        return int(open(cursor_path).read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def get_unprocessed_entries(log_path: str, cursor: int) -> list[dict]:
    entries = []
    with open(log_path) as f:
        for i, line in enumerate(f):
            if i < cursor:
                continue
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def read_synthesized_prose(md_path: str) -> str:
    try:
        return open(md_path).read()
    except FileNotFoundError:
        return ""


def validate_token_length(text: str) -> bool:
    return len(text) <= MAX_CHARS


def archive_and_truncate(log_path: str, archive_dir: str, cursor_path: str, slug: str):
    os.makedirs(archive_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_path = os.path.join(archive_dir, f"{slug}-{timestamp}.jsonl")
    shutil.copy2(log_path, archive_path)

    # Keep last SEED_COUNT entries
    with open(log_path) as f:
        all_lines = f.readlines()
    seed_lines = all_lines[-SEED_COUNT:] if len(all_lines) > SEED_COUNT else all_lines
    with open(log_path, "w") as f:
        f.writelines(seed_lines)

    # Reset cursor
    os.makedirs(os.path.dirname(cursor_path), exist_ok=True)
    with open(cursor_path, "w") as f:
        f.write("0")


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


def resolve_paths(slug: str) -> tuple[str, str, str, str]:
    """Return (log_path, cursor_path, md_path, archive_dir) for a given slug."""
    if slug == "global":
        log_path = os.path.join(MEMORY_ROOT, "logs", "global.jsonl")
        md_path = os.path.join(MEMORY_ROOT, "global.md")
    else:
        log_path = os.path.join(MEMORY_ROOT, "logs", "projects", f"{slug}.jsonl")
        md_path = os.path.join(MEMORY_ROOT, "projects", f"{slug}.md")
    cursor_path = os.path.join(MEMORY_ROOT, "logs", ".cursors", slug)
    archive_dir = os.path.join(MEMORY_ROOT, "logs", "archive")
    return log_path, cursor_path, md_path, archive_dir


def main():
    if len(sys.argv) < 2:
        log_error("reflect.py requires a slug argument")
        sys.exit(0)

    slug = sys.argv[1]
    log_path, cursor_path, md_path, archive_dir = resolve_paths(slug)

    if not os.path.exists(log_path):
        sys.exit(0)

    cursor = read_cursor(cursor_path)
    entries = get_unprocessed_entries(log_path, cursor)
    if not entries:
        sys.exit(0)

    existing_prose = read_synthesized_prose(md_path)
    new_prose = synthesize(existing_prose, entries)

    # Validate length, retry once if too long
    if not validate_token_length(new_prose):
        log_error(f"Synthesis for {slug} exceeded {MAX_CHARS} chars ({len(new_prose)}), retrying with compression")
        new_prose = compress_prose(new_prose)
        if not validate_token_length(new_prose):
            log_error(f"Synthesis for {slug} still exceeds limit after retry ({len(new_prose)}), writing anyway")

    # Write synthesized prose
    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w") as f:
        f.write(new_prose)

    # Archive and truncate
    archive_and_truncate(log_path, archive_dir, cursor_path, slug)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error(f"Reflector fatal error: {e}")
    sys.exit(0)
