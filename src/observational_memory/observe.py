"""Observer: extracts observations from CC session transcripts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import anthropic

from observational_memory.api_key import resolve_api_key
from observational_memory.slugs import cc_slug, memory_slug
from observational_memory.session_parser import parse_session
from observational_memory.prompts import OBSERVER_SYSTEM_PROMPT, OBSERVER_USER_PROMPT
from observational_memory.db import (
    insert_observations,
    insert_interaction_style,
    is_session_observed,
    mark_session_observed,
    get_observations_for_project,
    get_global_observations,
    get_unprocessed_count,
)

MEMORY_ROOT = os.path.expanduser("~/.observational-memory/memory")
ERROR_LOG = os.path.expanduser("~/.observational-memory/errors.log")
REFLECTION_THRESHOLD = 100
MODEL = "claude-haiku-4-5-20251001"


def log_error(msg: str):
    os.makedirs(os.path.dirname(ERROR_LOG), exist_ok=True)
    with open(ERROR_LOG, "a") as f:
        f.write(f"[{datetime.now(timezone.utc).isoformat()}] {msg}\n")


def cwd_from_session_file(path: str) -> str | None:
    """Extract the cwd from the first record in a CC session JSONL file."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                cwd = record.get("cwd")
                if cwd:
                    return cwd
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def strip_code_fences(text: str) -> str:
    """Strip markdown code fences (e.g. ```json ... ```) from model output."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return text


def maybe_trigger_reflection(slug: str):
    """Spawn the reflector if unprocessed observation count exceeds the threshold."""
    count = get_unprocessed_count(slug)
    if count > REFLECTION_THRESHOLD:
        subprocess.Popen(
            [sys.executable, "-m", "observational_memory.reflect", slug],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def get_existing_observations_summary(project: str) -> str:
    """Build a summary of existing observations for dedup context."""
    try:
        project_obs = get_observations_for_project(project)
        global_obs = get_global_observations()
    except Exception:
        return ""

    # Deduplicate by content and take unique entries
    seen = set()
    unique = []
    for obs in project_obs + global_obs:
        if obs["content"] not in seen:
            seen.add(obs["content"])
            unique.append(obs)

    if not unique:
        return ""

    # Truncate to last 50 unique observations to avoid blowing up the prompt
    recent = unique[-50:]
    lines = [f"- [{o['type']}] {o['content']}" for o in recent]
    return "\n".join(lines)


def extract_observations(messages: list[dict], project: str) -> tuple[list[dict], dict | None]:
    """Call Haiku to extract observations and interaction style from conversation.

    Returns (observations_list, interaction_style_dict_or_None).
    """
    if not messages:
        return [], None
    # Truncate very long conversations to avoid hitting context limits
    # Keep first 5 + last 50 messages to capture initial context and recent patterns
    if len(messages) > 60:
        messages = messages[:5] + messages[-50:]
    conversation = "\n".join(
        f"{'USER' if m['role'] == 'user' else 'ASSISTANT'}: {m['content']}"
        for m in messages
    )

    # Build dedup context from existing observations
    existing_summary = get_existing_observations_summary(project)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=OBSERVER_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": OBSERVER_USER_PROMPT.format(
                project=project,
                conversation=conversation,
                existing_observations=existing_summary,
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

    observations = []
    for obs in raw_obs:
        if (isinstance(obs, dict)
            and obs.get("scope") in ("global", "project")
            and obs.get("type") in ("preference", "correction", "pattern", "decision")
            and obs.get("content")):
            cleaned = {
                "scope": obs["scope"],
                "type": obs["type"],
                "content": obs["content"],
            }
            if obs.get("durability") in ("durable", "contextual", "incident"):
                cleaned["durability"] = obs["durability"]
            if obs.get("trigger"):
                cleaned["trigger"] = obs["trigger"]
            observations.append(cleaned)
    return observations, interaction_style


def process_session(session_path: str, session_id: str, cwd: str) -> str | None:
    """Process a single session transcript. Returns the memory slug if observations were written."""
    slug = memory_slug(cwd)
    messages = parse_session(session_path)
    if not messages:
        return None
    observations, interaction_style = extract_observations(messages, slug)

    has_obs = bool(observations) or bool(interaction_style)

    try:
        if observations:
            insert_observations(observations, session_id, slug)
        if interaction_style and isinstance(interaction_style, dict):
            insert_interaction_style(interaction_style, session_id, slug)
        mark_session_observed(session_id, slug, has_obs)
    except Exception as e:
        log_error(f"DB write failed for session {session_id}: {e}")

    if not has_obs:
        return None

    return slug


def find_all_cc_sessions() -> list[tuple[str, str]]:
    """Scan all CC project directories for session JSONL files.

    Returns list of (session_id, file_path) across all projects.
    """
    cc_projects_root = os.path.expanduser("~/.claude/projects")
    sessions = []
    try:
        for project_dir_name in os.listdir(cc_projects_root):
            project_dir = os.path.join(cc_projects_root, project_dir_name)
            if not os.path.isdir(project_dir):
                continue
            for fname in os.listdir(project_dir):
                if fname.endswith(".jsonl"):
                    sid = fname.removesuffix(".jsonl")
                    sessions.append((sid, os.path.join(project_dir, fname)))
    except FileNotFoundError:
        pass
    return sessions


def main():
    resolve_api_key()
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception) as e:
        log_error(f"Failed to read stdin payload: {e}")
        sys.exit(0)

    session_id = payload.get("session_id", "") or payload.get("sessionId", "")
    cwd = payload.get("cwd", "")
    if not session_id or not cwd:
        log_error(f"Missing sessionId or cwd in payload: {payload}")
        sys.exit(0)

    cc_project_slug = cc_slug(cwd)
    cc_project_dir = os.path.expanduser(f"~/.claude/projects/{cc_project_slug}")
    slugs_written = set()

    # Process current session
    session_path = os.path.join(cc_project_dir, f"{session_id}.jsonl")
    if not is_session_observed(session_id):
        slug = process_session(session_path, session_id, cwd)
        if slug:
            slugs_written.add(slug)

    # Catch up missed sessions across ALL projects
    for sid, spath in find_all_cc_sessions():
        if sid == session_id:
            continue
        try:
            if is_session_observed(sid):
                continue
            # Derive cwd from the session file itself
            session_cwd = cwd_from_session_file(spath)
            if not session_cwd:
                continue
            slug = process_session(spath, sid, session_cwd)
            if slug:
                slugs_written.add(slug)
        except Exception as e:
            log_error(f"Error processing missed session {sid}: {e}")

    # After all sessions are processed, check reflection thresholds per project
    for slug in slugs_written:
        maybe_trigger_reflection(slug)
    if slugs_written:
        maybe_trigger_reflection("global")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error(f"Observer fatal error: {e}")
    sys.exit(0)
