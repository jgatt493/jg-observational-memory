"""Observer: extracts observations from CC session transcripts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import anthropic

from observer.slugs import cc_slug, memory_slug
from observer.session_parser import parse_session
from observer.prompts import OBSERVER_SYSTEM_PROMPT, OBSERVER_USER_PROMPT
from observer.db import insert_observations, insert_interaction_style, is_session_observed

MEMORY_ROOT = os.path.join(os.path.dirname(__file__), "..", "memory")
REFLECTION_THRESHOLD = 100
MODEL = "claude-haiku-4-5-20251001"


def log_error(msg: str):
    path = os.path.join(MEMORY_ROOT, "logs", "errors.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")


def load_observed_sessions(path: str) -> set[str]:
    try:
        with open(path) as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()


def save_observed_session(path: str, session_id: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(session_id + "\n")


def append_observations(log_path: str, observations: list[dict], session_id: str, project: str):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        for obs in observations:
            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "session": session_id,
                "project": project,
                "scope": obs["scope"],
                "type": obs["type"],
                "content": obs["content"],
            }
            f.write(json.dumps(record) + "\n")


def check_and_trigger_reflector(log_path: str, cursor_path: str, slug: str):
    try:
        total_lines = sum(1 for _ in open(log_path))
    except FileNotFoundError:
        return
    try:
        cursor = int(open(cursor_path).read().strip())
    except (FileNotFoundError, ValueError):
        cursor = 0
    unprocessed = total_lines - cursor
    if unprocessed > REFLECTION_THRESHOLD:
        reflect_script = os.path.join(os.path.dirname(__file__), "reflect.py")
        subprocess.Popen(
            [sys.executable, reflect_script, slug],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def strip_code_fences(text: str) -> str:
    """Strip markdown code fences (e.g. ```json ... ```) from model output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return text


def extract_observations(messages: list[dict], project: str) -> tuple[list[dict], dict | None]:
    """Call Haiku to extract observations and interaction style from conversation.

    Returns (observations_list, interaction_style_dict_or_None).
    """
    if not messages:
        return [], None
    conversation = "\n".join(
        f"{'USER' if m['role'] == 'user' else 'ASSISTANT'}: {m['content']}"
        for m in messages
    )
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=OBSERVER_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": OBSERVER_USER_PROMPT.format(
                project=project, conversation=conversation
            )}
        ],
    )
    text = strip_code_fences(response.content[0].text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        log_error(f"Failed to parse observer response as JSON: {text[:500]}")
        return [], None

    # Handle new format: {"observations": [...], "interaction_style": {...}}
    if isinstance(parsed, dict) and "observations" in parsed:
        raw_obs = parsed.get("observations", [])
        interaction_style = parsed.get("interaction_style")
    elif isinstance(parsed, list):
        # Backwards compat with old format (flat array)
        raw_obs = parsed
        interaction_style = None
    else:
        return [], None

    observations = [
        obs for obs in raw_obs
        if isinstance(obs, dict)
        and obs.get("scope") in ("global", "project")
        and obs.get("type") in ("preference", "correction", "pattern", "decision")
        and obs.get("content")
    ]
    return observations, interaction_style


def process_session(session_path: str, session_id: str, cwd: str) -> str | None:
    """Process a single session transcript. Returns the memory slug if observations were written."""
    slug = memory_slug(cwd)
    messages = parse_session(session_path)
    if not messages:
        return None
    observations, interaction_style = extract_observations(messages, slug)

    if not observations and not interaction_style:
        return None

    # Write to Postgres
    try:
        if observations:
            insert_observations(observations, session_id, slug)
        if interaction_style and isinstance(interaction_style, dict):
            insert_interaction_style(interaction_style, session_id, slug)
    except Exception as e:
        log_error(f"Postgres write failed for session {session_id}: {e}")

    # Also write to JSONL (legacy, used by reflector until migrated)
    project_obs = [o for o in observations if o["scope"] == "project"]
    global_obs = [o for o in observations if o["scope"] == "global"]
    if project_obs:
        project_log = os.path.join(MEMORY_ROOT, "logs", "projects", f"{slug}.jsonl")
        append_observations(project_log, project_obs, session_id, slug)
    if global_obs:
        global_log = os.path.join(MEMORY_ROOT, "logs", "global.jsonl")
        append_observations(global_log, global_obs, session_id, slug)
    if interaction_style and isinstance(interaction_style, dict):
        style_record = [{
            "scope": "project",
            "type": "interaction_style",
            "content": interaction_style,
        }]
        project_log = os.path.join(MEMORY_ROOT, "logs", "projects", f"{slug}.jsonl")
        append_observations(project_log, style_record, session_id, slug)
        global_log = os.path.join(MEMORY_ROOT, "logs", "global.jsonl")
        append_observations(global_log, style_record, session_id, slug)

    return slug


def find_unobserved_sessions(cc_project_dir: str, observed: set[str]) -> list[tuple[str, str]]:
    """Find session JSONL files that haven't been observed yet."""
    unobserved = []
    try:
        for fname in os.listdir(cc_project_dir):
            if fname.endswith(".jsonl"):
                sid = fname.removesuffix(".jsonl")
                if sid not in observed:
                    unobserved.append((sid, os.path.join(cc_project_dir, fname)))
    except FileNotFoundError:
        pass
    return unobserved


def main():
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception) as e:
        log_error(f"Failed to read stdin payload: {e}")
        sys.exit(0)

    session_id = payload.get("sessionId", "")
    cwd = payload.get("cwd", "")
    if not session_id or not cwd:
        log_error(f"Missing sessionId or cwd in payload: {payload}")
        sys.exit(0)

    cc_project_slug = cc_slug(cwd)
    cc_project_dir = os.path.expanduser(f"~/.claude/projects/{cc_project_slug}")
    observed_path = os.path.join(MEMORY_ROOT, "logs", ".observed-sessions")
    observed = load_observed_sessions(observed_path)

    # Process current session
    session_path = os.path.join(cc_project_dir, f"{session_id}.jsonl")
    slug = None
    if session_id not in observed:
        slug = process_session(session_path, session_id, cwd)
        save_observed_session(observed_path, session_id)

    # Catch up missed sessions
    for sid, spath in find_unobserved_sessions(cc_project_dir, observed | {session_id}):
        try:
            result = process_session(spath, sid, cwd)
            if result is not None:
                slug = result
            save_observed_session(observed_path, sid)
        except Exception as e:
            log_error(f"Error processing missed session {sid}: {e}")

    # After all sessions are processed, check reflection thresholds once
    if slug is not None:
        check_and_trigger_reflector(
            os.path.join(MEMORY_ROOT, "logs", "projects", f"{slug}.jsonl"),
            os.path.join(MEMORY_ROOT, "logs", ".cursors", slug),
            slug,
        )
        check_and_trigger_reflector(
            os.path.join(MEMORY_ROOT, "logs", "global.jsonl"),
            os.path.join(MEMORY_ROOT, "logs", ".cursors", "global"),
            "global",
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error(f"Observer fatal error: {e}")
    sys.exit(0)
