"""Resolve ANTHROPIC_API_KEY from env or file path."""
import os
import stat
import sys


def resolve_api_key():
    """Ensure ANTHROPIC_API_KEY is set, reading from file if needed.

    Checks in order:
    1. ANTHROPIC_API_KEY already set in env — done
    2. ANTHROPIC_API_KEY_FILE points to a file — read and set ANTHROPIC_API_KEY
    3. ~/.observational-memory/.api-key exists — read and set ANTHROPIC_API_KEY

    Silently returns if no key found (caller handles the error).
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return

    # Check ANTHROPIC_API_KEY_FILE env var
    key_file = os.environ.get("ANTHROPIC_API_KEY_FILE")
    if key_file:
        key = _read_key_file(key_file)
        if key:
            os.environ["ANTHROPIC_API_KEY"] = key
            return

    # Check default location
    default_path = os.path.expanduser("~/.observational-memory/.api-key")
    key = _read_key_file(default_path)
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key


def _read_key_file(path: str) -> str | None:
    try:
        # Warn if key file is world-readable
        file_stat = os.stat(path)
        if file_stat.st_mode & (stat.S_IROTH | stat.S_IRGRP):
            print(
                f"  Warning: {path} is readable by other users. "
                f"Run: chmod 600 {path}",
                file=sys.stderr,
            )
        with open(path) as f:
            key = f.read().strip()
            return key if key else None
    except (FileNotFoundError, PermissionError):
        return None
