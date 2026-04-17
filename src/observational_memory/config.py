"""Shared constants and utilities for observational memory."""
import os
from datetime import datetime, timezone

MEMORY_ROOT = os.path.expanduser("~/.observational-memory/memory")
ERROR_LOG = os.path.expanduser("~/.observational-memory/errors.log")
MODEL = "claude-haiku-4-5-20251001"


def log_error(msg: str):
    os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
    with open(ERROR_LOG, "a") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")
