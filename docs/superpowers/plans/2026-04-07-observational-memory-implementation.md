# Observational Memory System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a personal observational memory system that watches Claude Code sessions and builds compressed behavioral rules per-project and globally.

**Architecture:** Python scripts (Observer + Reflector) triggered by CC Stop hook. Observer reads session transcripts, calls Haiku to extract observations, appends to JSONL logs. Reflector synthesizes JSONL into dense prose `.md` files. A skill file lets any agent load the memory. A bootstrap script wires new projects.

**Tech Stack:** Python 3.13, anthropic SDK, pytest, Claude Haiku (`claude-haiku-4-5-20251001`)

**Spec:** `docs/superpowers/specs/2026-03-18-observational-memory-design.md`

---

## File Structure

```
jg-observational-memory/
├── observer/
│   ├── __init__.py
│   ├── slugs.py            # CC slug + memory slug derivation
│   ├── session_parser.py   # Reads CC session JSONL, extracts messages
│   ├── observe.py          # Observer entry point (called by Stop hook)
│   ├── reflect.py          # Reflector entry point
│   └── prompts.py          # Extraction + reflection prompt templates
├── tests/
│   ├── __init__.py
│   ├── test_slugs.py
│   ├── test_session_parser.py
│   ├── test_observe.py
│   └── test_reflect.py
├── memory/                 # Created at runtime, .gitkeep for structure
│   ├── .gitkeep
│   ├── logs/
│   │   ├── .gitkeep
│   │   ├── .cursors/.gitkeep
│   │   ├── projects/.gitkeep
│   │   └── archive/.gitkeep
│   └── projects/.gitkeep
├── skills/
│   └── jg-context.md
├── scripts/
│   └── bootstrap-project.sh
├── requirements.txt
├── .gitignore
└── docs/
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `observer/__init__.py`
- Create: `tests/__init__.py`
- Create: `memory/.gitkeep`, `memory/logs/.gitkeep`, `memory/logs/.cursors/.gitkeep`, `memory/logs/projects/.gitkeep`, `memory/logs/archive/.gitkeep`, `memory/projects/.gitkeep`

- [ ] **Step 1: Create requirements.txt**

```
anthropic>=0.49.0
pytest>=8.0.0
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
memory/logs/*.jsonl
memory/logs/projects/*.jsonl
memory/logs/archive/*.jsonl
memory/logs/.observed-sessions
memory/logs/.cursors/*
memory/logs/errors.log
memory/global.md
memory/projects/*.md
```

- [ ] **Step 3: Create directory structure with .gitkeep files**

```bash
mkdir -p observer tests memory/logs/.cursors memory/logs/projects memory/logs/archive memory/projects skills scripts
touch observer/__init__.py tests/__init__.py
touch memory/.gitkeep memory/logs/.gitkeep memory/logs/.cursors/.gitkeep memory/logs/projects/.gitkeep memory/logs/archive/.gitkeep memory/projects/.gitkeep
```

- [ ] **Step 4: Install dependencies**

```bash
pip3 install anthropic pytest
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore observer/__init__.py tests/__init__.py memory/
git commit -m "feat: scaffold project structure and dependencies"
```

---

### Task 2: Slug utilities

**Files:**
- Create: `observer/slugs.py`
- Create: `tests/test_slugs.py`

- [ ] **Step 1: Write failing tests for slug derivation**

```python
# tests/test_slugs.py
from observer.slugs import cc_slug, memory_slug


def test_cc_slug_basic():
    assert cc_slug("/Users/jeremygatt/Projects/dg2") == "-Users-jeremygatt-Projects-dg2"


def test_cc_slug_preserves_leading_dash():
    result = cc_slug("/Users/foo/bar")
    assert result.startswith("-")


def test_memory_slug_basic():
    assert memory_slug("/Users/jeremygatt/Projects/dg2") == "dg2"


def test_memory_slug_lowercases():
    assert memory_slug("/Users/foo/Projects/DG-Chat") == "dg-chat"


def test_memory_slug_replaces_spaces():
    assert memory_slug("/Users/foo/Projects/DG Chat Server") == "dg-chat-server"


def test_memory_slug_strips_special_chars():
    assert memory_slug("/Users/foo/Projects/my_project!v2") == "my-project-v2"


def test_memory_slug_strips_leading_trailing_dashes():
    assert memory_slug("/Users/foo/Projects/-my-project-") == "my-project"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_slugs.py -v`
Expected: FAIL — `ImportError: cannot import name 'cc_slug'`

- [ ] **Step 3: Implement slugs.py**

```python
# observer/slugs.py
import os
import re


def cc_slug(cwd: str) -> str:
    """Derive Claude Code's internal project slug from a working directory path.

    Replaces all '/' with '-'. The leading '-' is intentional and must be preserved.
    """
    return cwd.replace("/", "-")


def memory_slug(cwd: str) -> str:
    """Derive our memory file slug from a working directory path.

    Takes the basename, lowercases, replaces non-alphanumeric chars with '-',
    strips leading/trailing '-'.
    """
    base = os.path.basename(cwd).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", base)
    return slug.strip("-")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_slugs.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add observer/slugs.py tests/test_slugs.py
git commit -m "feat: add CC slug and memory slug derivation utilities"
```

---

### Task 3: Session parser

**Files:**
- Create: `observer/session_parser.py`
- Create: `tests/test_session_parser.py`
- Create: `tests/fixtures/sample_session.jsonl` (test fixture)

- [ ] **Step 1: Create test fixture**

Create `tests/fixtures/sample_session.jsonl` with realistic CC session data based on the format observed. Must include `user`, `assistant`, `progress`, `system`, and `file-history-snapshot` types.

```jsonl
{"type":"progress","data":{"type":"hook_progress","hookEvent":"SessionStart"},"sessionId":"test-session-123","cwd":"/Users/test/Projects/myapp","timestamp":"2026-03-18T10:00:00Z","uuid":"aaa"}
{"type":"system","message":{"role":"system","content":"System prompt here"},"uuid":"bbb","timestamp":"2026-03-18T10:00:01Z"}
{"type":"user","message":{"role":"user","content":"I always want feature branches, never commit to main"},"uuid":"ccc","timestamp":"2026-03-18T10:00:02Z"}
{"type":"assistant","message":{"role":"assistant","content":"Got it, I'll use feature branches."},"uuid":"ddd","timestamp":"2026-03-18T10:00:03Z"}
{"type":"user","message":{"role":"user","content":"No, I said don't use mocks for database tests. Use real DB."},"uuid":"eee","timestamp":"2026-03-18T10:00:04Z"}
{"type":"assistant","message":{"role":"assistant","content":"Understood, switching to real database for tests."},"uuid":"fff","timestamp":"2026-03-18T10:00:05Z"}
{"type":"file-history-snapshot","messageId":"ggg","snapshot":{"messageId":"ggg","trackedFileBackups":{},"timestamp":"2026-03-18T10:00:06Z"}}
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_session_parser.py
import os
from observer.session_parser import parse_session

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_session.jsonl")


def test_parse_session_returns_messages():
    messages = parse_session(FIXTURE_PATH)
    assert len(messages) > 0


def test_parse_session_extracts_only_user_and_assistant():
    messages = parse_session(FIXTURE_PATH)
    roles = {m["role"] for m in messages}
    assert roles == {"user", "assistant"}


def test_parse_session_preserves_order():
    messages = parse_session(FIXTURE_PATH)
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"


def test_parse_session_extracts_content():
    messages = parse_session(FIXTURE_PATH)
    assert "feature branches" in messages[0]["content"]


def test_parse_session_nonexistent_file():
    messages = parse_session("/nonexistent/path.jsonl")
    assert messages == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_session_parser.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 4: Implement session_parser.py**

```python
# observer/session_parser.py
import json


def parse_session(path: str) -> list[dict]:
    """Parse a CC session JSONL file and return user + assistant messages in order."""
    messages = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("type") not in ("user", "assistant"):
                    continue
                msg = record.get("message", {})
                role = msg.get("role")
                content = msg.get("content", "")
                if role and content and isinstance(content, str):
                    messages.append({"role": role, "content": content})
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    return messages
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_session_parser.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
mkdir -p tests/fixtures
git add observer/session_parser.py tests/test_session_parser.py tests/fixtures/
git commit -m "feat: add session JSONL parser for CC transcripts"
```

---

### Task 4: Prompts module

**Files:**
- Create: `observer/prompts.py`

No tests for this task — prompts are string templates. Quality iteration is a separate workstream per spec.

- [ ] **Step 1: Create stub prompts**

```python
# observer/prompts.py

OBSERVER_SYSTEM_PROMPT = """You are an observation agent. You watch conversations between a user and an AI assistant and extract observations about the USER — their preferences, corrections, patterns, and decisions.

You do NOT observe the assistant's behavior. You observe the HUMAN.

For each observation, classify it:
- "preference": something the user likes or dislikes
- "correction": the user had to correct or re-explain something
- "pattern": a recurring behavior or approach
- "decision": a project-specific decision (architecture, tooling, domain)

For each observation, determine scope:
- "global": applies across all projects (e.g., git workflow, testing philosophy)
- "project": specific to the current project

Return a JSON array of observations. Each observation:
{"scope": "global|project", "type": "preference|correction|pattern|decision", "content": "concise description of the observation"}

If there are no meaningful observations, return an empty array: []

Be selective. Only extract observations that would be useful for future sessions. Skip trivial interactions."""

OBSERVER_USER_PROMPT = """Here is a conversation between the user and an AI assistant. Extract observations about the user.

Project: {project}

Conversation:
{conversation}"""

REFLECTOR_SYSTEM_PROMPT = """You are a memory synthesis agent. You take raw observations about a user and synthesize them into dense, compressed prose — behavioral rules that an AI agent should follow when working with this user.

Rules:
1. Output must not exceed 8000 characters (~2000 tokens).
2. Use flat prose with topic-prefix labels. No headers, no bullet lists.
3. Maximize information density — every word should carry meaning.
4. Entries marked [CORRECTION] are firm rules, not soft preferences. The user had to explicitly correct an agent. These MUST appear in the output.
5. If you receive existing prose, integrate the new observations into it. Do not simply append — rewrite the whole document to be coherent.
6. Merge duplicate or related observations.
7. Drop observations that are trivial or one-off.

Example output format:
testing: backend(python,rust) always requires test cases. frontend: no unit tests; e2e playwright only when explicitly asked.

git: always feature branches. never commit to main. never reuse a merged branch."""

REFLECTOR_USER_PROMPT = """Here are the current synthesized rules (may be empty if first reflection):

{existing_prose}

---

Here are new observations to integrate:

{observations}

---

Produce the updated dense prose. Remember: max 8000 characters, flat prose with topic prefixes, [CORRECTION] entries are firm rules."""
```

- [ ] **Step 2: Commit**

```bash
git add observer/prompts.py
git commit -m "feat: add stub observer and reflector prompt templates"
```

---

### Task 5: Observer script

**Files:**
- Create: `observer/observe.py`
- Create: `tests/test_observe.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_observe.py
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from observer.observe import (
    process_session,
    append_observations,
    load_observed_sessions,
    save_observed_session,
    check_and_trigger_reflector,
)


def test_append_observations_creates_file(tmp_path):
    log_path = tmp_path / "test.jsonl"
    obs = [
        {"scope": "project", "type": "preference", "content": "likes feature branches"}
    ]
    append_observations(str(log_path), obs, "test-session", "myproject")
    assert log_path.exists()
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["type"] == "preference"
    assert record["session"] == "test-session"
    assert record["project"] == "myproject"
    assert "ts" in record


def test_append_observations_appends(tmp_path):
    log_path = tmp_path / "test.jsonl"
    log_path.write_text('{"existing": true}\n')
    obs = [{"scope": "project", "type": "decision", "content": "use postgres"}]
    append_observations(str(log_path), obs, "s1", "proj")
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 2


def test_load_observed_sessions_empty(tmp_path):
    path = tmp_path / ".observed-sessions"
    result = load_observed_sessions(str(path))
    assert result == set()


def test_load_observed_sessions_existing(tmp_path):
    path = tmp_path / ".observed-sessions"
    path.write_text("session-1\nsession-2\n")
    result = load_observed_sessions(str(path))
    assert result == {"session-1", "session-2"}


def test_save_observed_session(tmp_path):
    path = tmp_path / ".observed-sessions"
    save_observed_session(str(path), "new-session")
    assert "new-session" in path.read_text()


def test_check_and_trigger_reflector_below_threshold(tmp_path):
    log_path = tmp_path / "test.jsonl"
    cursor_path = tmp_path / "cursor"
    log_path.write_text("\n".join(["{}" for _ in range(50)]) + "\n")
    cursor_path.write_text("0")
    with patch("observer.observe.subprocess") as mock_sub:
        check_and_trigger_reflector(str(log_path), str(cursor_path), "slug")
        mock_sub.Popen.assert_not_called()


def test_check_and_trigger_reflector_above_threshold(tmp_path):
    log_path = tmp_path / "test.jsonl"
    cursor_path = tmp_path / "cursor"
    log_path.write_text("\n".join(["{}" for _ in range(101)]) + "\n")
    cursor_path.write_text("0")
    with patch("observer.observe.subprocess") as mock_sub:
        check_and_trigger_reflector(str(log_path), str(cursor_path), "slug")
        mock_sub.Popen.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_observe.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement observe.py**

```python
# observer/observe.py
"""Observer: extracts observations from CC session transcripts."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import anthropic

from observer.slugs import cc_slug, memory_slug
from observer.session_parser import parse_session
from observer.prompts import OBSERVER_SYSTEM_PROMPT, OBSERVER_USER_PROMPT

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


def extract_observations(messages: list[dict], project: str) -> list[dict]:
    """Call Haiku to extract observations from conversation messages."""
    if not messages:
        return []
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
    text = response.content[0].text
    # Parse JSON array from response
    try:
        observations = json.loads(text)
        if not isinstance(observations, list):
            return []
        return [
            obs for obs in observations
            if isinstance(obs, dict)
            and obs.get("scope") in ("global", "project")
            and obs.get("type") in ("preference", "correction", "pattern", "decision")
            and obs.get("content")
        ]
    except json.JSONDecodeError:
        log_error(f"Failed to parse observer response as JSON: {text[:500]}")
        return []


def process_session(session_path: str, session_id: str, cwd: str):
    """Process a single session transcript."""
    slug = memory_slug(cwd)
    messages = parse_session(session_path)
    if not messages:
        return
    observations = extract_observations(messages, slug)
    if not observations:
        return
    project_obs = [o for o in observations if o["scope"] == "project"]
    global_obs = [o for o in observations if o["scope"] == "global"]
    if project_obs:
        project_log = os.path.join(MEMORY_ROOT, "logs", "projects", f"{slug}.jsonl")
        append_observations(project_log, project_obs, session_id, slug)
    if global_obs:
        global_log = os.path.join(MEMORY_ROOT, "logs", "global.jsonl")
        append_observations(global_log, global_obs, session_id, slug)
    # Check reflection thresholds
    if project_obs:
        check_and_trigger_reflector(
            os.path.join(MEMORY_ROOT, "logs", "projects", f"{slug}.jsonl"),
            os.path.join(MEMORY_ROOT, "logs", ".cursors", slug),
            slug,
        )
    if global_obs:
        check_and_trigger_reflector(
            os.path.join(MEMORY_ROOT, "logs", "global.jsonl"),
            os.path.join(MEMORY_ROOT, "logs", ".cursors", "global"),
            "global",
        )


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
    if session_id not in observed:
        process_session(session_path, session_id, cwd)
        save_observed_session(observed_path, session_id)

    # Catch up missed sessions
    for sid, spath in find_unobserved_sessions(cc_project_dir, observed | {session_id}):
        try:
            process_session(spath, sid, cwd)
            save_observed_session(observed_path, sid)
        except Exception as e:
            log_error(f"Error processing missed session {sid}: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error(f"Observer fatal error: {e}")
    sys.exit(0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_observe.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add observer/observe.py tests/test_observe.py
git commit -m "feat: implement observer script with session catch-up"
```

---

### Task 6: Reflector script

**Files:**
- Create: `observer/reflect.py`
- Create: `tests/test_reflect.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_reflect.py
import json
import os
from unittest.mock import patch, MagicMock
from observer.reflect import (
    read_cursor,
    get_unprocessed_entries,
    read_synthesized_prose,
    archive_and_truncate,
    validate_token_length,
)


def test_read_cursor_missing_file(tmp_path):
    assert read_cursor(str(tmp_path / "nonexistent")) == 0


def test_read_cursor_existing(tmp_path):
    cursor_path = tmp_path / "cursor"
    cursor_path.write_text("42")
    assert read_cursor(str(cursor_path)) == 42


def test_read_cursor_zero(tmp_path):
    cursor_path = tmp_path / "cursor"
    cursor_path.write_text("0")
    assert read_cursor(str(cursor_path)) == 0


def test_get_unprocessed_entries(tmp_path):
    log_path = tmp_path / "log.jsonl"
    lines = [json.dumps({"content": f"entry-{i}"}) for i in range(10)]
    log_path.write_text("\n".join(lines) + "\n")
    entries = get_unprocessed_entries(str(log_path), cursor=5)
    assert len(entries) == 5
    assert entries[0]["content"] == "entry-5"


def test_get_unprocessed_entries_cursor_zero(tmp_path):
    log_path = tmp_path / "log.jsonl"
    lines = [json.dumps({"content": f"entry-{i}"}) for i in range(3)]
    log_path.write_text("\n".join(lines) + "\n")
    entries = get_unprocessed_entries(str(log_path), cursor=0)
    assert len(entries) == 3


def test_read_synthesized_prose_missing(tmp_path):
    assert read_synthesized_prose(str(tmp_path / "nonexistent.md")) == ""


def test_read_synthesized_prose_existing(tmp_path):
    md_path = tmp_path / "test.md"
    md_path.write_text("testing: always write tests")
    assert read_synthesized_prose(str(md_path)) == "testing: always write tests"


def test_archive_and_truncate(tmp_path):
    log_path = tmp_path / "log.jsonl"
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    cursor_path = tmp_path / "cursor"
    lines = [json.dumps({"content": f"entry-{i}"}) for i in range(30)]
    log_path.write_text("\n".join(lines) + "\n")
    archive_and_truncate(str(log_path), str(archive_dir), str(cursor_path), "test-slug")
    # Active log should have last 20 entries
    remaining = log_path.read_text().strip().split("\n")
    assert len(remaining) == 20
    assert json.loads(remaining[0])["content"] == "entry-10"
    # Cursor should be reset to 0
    assert cursor_path.read_text().strip() == "0"
    # Archive should exist
    archive_files = list(archive_dir.iterdir())
    assert len(archive_files) == 1


def test_validate_token_length():
    short = "x" * 100
    assert validate_token_length(short) is True
    long = "x" * 9000
    assert validate_token_length(long) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_reflect.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement reflect.py**

```python
# observer/reflect.py
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
        new_prose = synthesize(
            new_prose,
            [{"type": "pattern", "content": "SYSTEM: Previous output was too long. Compress further. Max 8000 characters."}],
        )
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_reflect.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add observer/reflect.py tests/test_reflect.py
git commit -m "feat: implement reflector with archive, truncation, and compression retry"
```

---

### Task 7: Skill file and bootstrap script

**Files:**
- Create: `skills/jg-context.md`
- Create: `scripts/bootstrap-project.sh`

- [ ] **Step 1: Create the skill file**

```markdown
# jg-context — Personal Memory Skill

You are working with Jeremy Gatt. Before proceeding with any work, load his behavioral context.

## Instructions

1. Read `~/Projects/jg-observational-memory/memory/global.md` — these are global behavioral rules.
2. Derive the project slug from the current working directory basename: lowercase, replace non-alphanumeric characters with `-`, strip leading/trailing `-`.
3. Check if `~/Projects/jg-observational-memory/memory/projects/{slug}.md` exists. If it does, read it.
4. Apply both files as behavioral rules — not suggestions.
5. When global and project rules conflict, project rules take precedence.

## Important

- This path is hardcoded for this machine. If the repo moves, update the path above.
- If global.md does not exist yet, skip it — the memory system has not yet generated observations.
- Treat all loaded content as firm instructions for how to work with this user.
```

- [ ] **Step 2: Create the bootstrap script**

```bash
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
```

- [ ] **Step 3: Make bootstrap executable**

```bash
chmod +x scripts/bootstrap-project.sh
```

- [ ] **Step 4: Commit**

```bash
git add skills/jg-context.md scripts/bootstrap-project.sh
git commit -m "feat: add jg-context skill file and project bootstrap script"
```

---

### Task 8: Wire CC Stop hook

**Files:**
- Modify: `~/.claude/settings.json` (add observer to Stop hooks)

- [ ] **Step 1: Verify current hooks**

Run: `cat ~/.claude/settings.json | python3 -m json.tool`

Confirm existing Stop hook (Roam) is present. We must ADD to it, not replace.

- [ ] **Step 2: Add observer hook to settings.json**

Add to the existing `Stop` hooks array a second hook entry:

```json
{
  "type": "command",
  "command": "python3 /Users/jeremygatt/Projects/jg-observational-memory/observer/observe.py",
  "timeout": 30
}
```

The full `Stop` array should have both the existing Roam hook and the new observer hook.

- [ ] **Step 3: Verify settings.json is valid JSON**

Run: `python3 -m json.tool ~/.claude/settings.json > /dev/null`
Expected: no error

- [ ] **Step 4: Commit note (do not commit settings.json — it's outside the repo)**

Note: `~/.claude/settings.json` is outside this repo. No git commit for this step.

---

### Task 9: End-to-end smoke test

- [ ] **Step 1: Run all unit tests**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Test observer manually with real session data**

Create a test script that simulates the Stop hook payload:

```bash
echo '{"sessionId": "e8e10080-d7d5-4a71-9bbe-2d9b611553ec", "cwd": "/Users/jeremygatt/Projects/jg-observational-memory"}' | ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" python3 observer/observe.py
```

- [ ] **Step 3: Verify observations were written**

```bash
cat memory/logs/projects/jg-observational-memory.jsonl
cat memory/logs/global.jsonl
```

Expected: JSONL entries with observations extracted from the real session.

- [ ] **Step 4: Test reflector manually (if enough entries)**

```bash
python3 observer/reflect.py jg-observational-memory
```

Or to test with a lower threshold, temporarily modify the test.

- [ ] **Step 5: Commit any test artifacts cleanup**

```bash
git add -A
git commit -m "chore: complete end-to-end smoke test"
```
