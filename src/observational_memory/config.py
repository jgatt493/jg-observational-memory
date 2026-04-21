"""Shared constants and utilities for observational memory."""
import json
import os
from datetime import datetime, timezone

OM_DIR = os.path.expanduser("~/.observational-memory")
MEMORY_ROOT = os.path.join(OM_DIR, "memory")
ERROR_LOG = os.path.join(OM_DIR, "errors.log")
CONFIG_PATH = os.path.join(OM_DIR, "config.json")
MODEL = "claude-haiku-4-5-20251001"


def log_error(msg: str):
    os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
    with open(ERROR_LOG, "a") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")


def load_config() -> dict:
    """Load config from ~/.observational-memory/config.json."""
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(config: dict):
    """Save config to ~/.observational-memory/config.json."""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def get_project_roots() -> list[str]:
    """Get configured project root directories."""
    config = load_config()
    return config.get("project_roots", [])
