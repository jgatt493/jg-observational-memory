# Tiered Reflections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the observer and reflector to produce tiered output — core behavioral rules + contextual/incident annotations with provenance.

**Architecture:** Observer gains `durability` and `trigger` fields per observation. Reflector produces two sections (===CORE=== and ===CONTEXTUAL===) written to separate files. Burn and rebuild — drop DB, re-observe all sessions.

**Tech Stack:** Python, SQLite, Anthropic Haiku API, pytest

**Spec:** `docs/superpowers/specs/2026-04-14-tiered-reflections-design.md`

---

### Task 1: Update DB Schema — New Columns on observations and reflections

**Files:**
- Modify: `src/observational_memory/db.py:11-61` (SCHEMA string)
- Modify: `src/observational_memory/db.py:83-98` (insert_observations)
- Modify: `src/observational_memory/db.py:159-181` (get_observations_for_project, get_global_observations)
- Modify: `src/observational_memory/db.py:196-213` (upsert_reflection)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write failing test for new observation columns**

Add to `tests/test_db.py`:

```python
def test_insert_observations_with_durability(tmp_db):
    obs = [
        {"scope": "global", "type": "correction", "content": "always feature branches",
         "durability": "durable", "trigger": "explicitly stated rule"},
    ]
    insert_observations(obs, "session-1", "myproj")
    result = get_observations_for_project("myproj")
    assert result[0]["durability"] == "durable"
    assert result[0]["trigger_summary"] == "explicitly stated rule"


def test_insert_observations_without_durability(tmp_db):
    """Backwards compat — missing durability/trigger fields default to None."""
    obs = [{"scope": "global", "type": "preference", "content": "likes tests"}]
    insert_observations(obs, "session-1", "myproj")
    result = get_observations_for_project("myproj")
    assert result[0]["durability"] is None
    assert result[0]["trigger_summary"] is None


def test_upsert_reflection_with_context_prose(tmp_db):
    upsert_reflection("myproj", "core rules", 5, 42, context_prose="[incident:bug] details")
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT prose, context_prose FROM reflections WHERE slug = ?", ("myproj",)).fetchone()
    conn.close()
    assert row[0] == "core rules"
    assert row[1] == "[incident:bug] details"


def test_upsert_reflection_without_context_prose(tmp_db):
    upsert_reflection("myproj", "core rules", 5, 42)
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT context_prose FROM reflections WHERE slug = ?", ("myproj",)).fetchone()
    conn.close()
    assert row[0] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_db.py -v -k "durability or context_prose"`
Expected: FAIL — columns don't exist, function signatures don't match

- [ ] **Step 3: Update SCHEMA string in db.py**

Add to the `observations` CREATE TABLE:
```sql
    durability TEXT CHECK (durability IN ('durable', 'contextual', 'incident')),
    trigger_summary TEXT
```

Add to the `reflections` CREATE TABLE:
```sql
    context_prose TEXT
```

Add index:
```sql
CREATE INDEX IF NOT EXISTS idx_observations_durability ON observations(durability);
```

- [ ] **Step 4: Update insert_observations() to handle new fields**

```python
def insert_observations(observations: list[dict], session_id: str, project: str):
    if not observations:
        return
    conn = get_connection()
    try:
        ts = datetime.now(timezone.utc).isoformat()
        for obs in observations:
            conn.execute(
                """INSERT INTO observations (ts, session_id, project, scope, type, content, durability, trigger_summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (ts, session_id, project, obs["scope"], obs["type"], obs["content"],
                 obs.get("durability"), obs.get("trigger")),
            )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 5: Update get_observations_for_project() and get_global_observations() to return new columns**

```python
def get_observations_for_project(project: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT scope, type, content, durability, trigger_summary FROM observations WHERE project = ? ORDER BY ts",
            (project,),
        ).fetchall()
        return [{"scope": r[0], "type": r[1], "content": r[2], "durability": r[3], "trigger_summary": r[4]} for r in rows]
    finally:
        conn.close()


def get_global_observations() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT scope, type, content, durability, trigger_summary FROM observations WHERE scope = 'global' ORDER BY ts",
        ).fetchall()
        return [{"scope": r[0], "type": r[1], "content": r[2], "durability": r[3], "trigger_summary": r[4]} for r in rows]
    finally:
        conn.close()
```

- [ ] **Step 6: Update upsert_reflection() to accept context_prose**

```python
def upsert_reflection(slug: str, prose: str, observation_count: int, last_observation_id: int, context_prose: str | None = None):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO reflections (slug, prose, char_count, observation_count, last_observation_id, ts, context_prose)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (slug) DO UPDATE SET
                 prose = EXCLUDED.prose,
                 char_count = EXCLUDED.char_count,
                 observation_count = EXCLUDED.observation_count,
                 last_observation_id = EXCLUDED.last_observation_id,
                 ts = EXCLUDED.ts,
                 context_prose = EXCLUDED.context_prose""",
            (slug, prose, len(prose), observation_count, last_observation_id, datetime.now(timezone.utc).isoformat(), context_prose),
        )
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add src/observational_memory/db.py tests/test_db.py
git commit -m "feat: add durability/trigger columns to observations, context_prose to reflections"
```

---

### Task 2: Update Observer Prompt — Add durability and trigger fields

**Files:**
- Modify: `src/observational_memory/prompts.py:1-89` (OBSERVER_SYSTEM_PROMPT, OBSERVER_USER_PROMPT)
- Modify: `src/observational_memory/observe.py:150-157` (observation validation in extract_observations)
- Test: `tests/test_observe.py`

- [ ] **Step 1: Write failing test for new observation fields in extract_observations**

Add to `tests/test_observe.py`:

```python
def test_extract_observations_parses_durability():
    """extract_observations should pass through durability and trigger fields."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "observations": [
            {"scope": "global", "type": "correction", "content": "always feature branches",
             "durability": "durable", "trigger": "explicitly stated rule"},
            {"scope": "project", "type": "pattern", "content": "frustrated by timeouts",
             "durability": "incident", "trigger": "npm version bug"},
        ],
        "interaction_style": {
            "expert": 0.8, "inquisitive": 0.2, "architectural": 0.5,
            "precise": 0.9, "scope_aware": 0.4, "risk_conscious": 0.3,
            "ai_led": 0.1, "domain": "devtools"
        }
    }))]

    with patch("observational_memory.observe.anthropic") as mock_anthropic, \
         patch("observational_memory.observe.get_existing_observations_summary", return_value=""):
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response
        from observational_memory.observe import extract_observations
        obs, style = extract_observations([{"role": "user", "content": "test"}], "test-proj")

    assert len(obs) == 2
    assert obs[0]["durability"] == "durable"
    assert obs[0]["trigger"] == "explicitly stated rule"
    assert obs[1]["durability"] == "incident"


def test_extract_observations_allows_missing_durability():
    """Observations without durability/trigger should still be accepted."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({
        "observations": [
            {"scope": "global", "type": "preference", "content": "likes tests"},
        ],
        "interaction_style": {
            "expert": 0.5, "inquisitive": 0.5, "architectural": 0.5,
            "precise": 0.5, "scope_aware": 0.5, "risk_conscious": 0.5,
            "ai_led": 0.5, "domain": "general"
        }
    }))]

    with patch("observational_memory.observe.anthropic") as mock_anthropic, \
         patch("observational_memory.observe.get_existing_observations_summary", return_value=""):
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response
        from observational_memory.observe import extract_observations
        obs, style = extract_observations([{"role": "user", "content": "test"}], "test-proj")

    assert len(obs) == 1
    assert obs[0].get("durability") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_observe.py -v -k "durability"`
Expected: FAIL or PASS depending on whether current validation strips unknown fields — verify behavior

- [ ] **Step 3: Update OBSERVER_SYSTEM_PROMPT in prompts.py**

Add to the output format section — each observation now includes `durability` and `trigger`:

```json
{
  "observations": [
    {
      "scope": "global|project",
      "type": "preference|correction|pattern|decision",
      "content": "concise description",
      "durability": "durable|contextual|incident",
      "trigger": "what caused this observation"
    }
  ],
  "interaction_style": { ... }
}
```

Add classification guidance after the observation types section:

```
## Durability Classification

For each observation, classify its durability:
- "durable": A stable preference or rule that would apply in any future session. The user explicitly stated it as a general rule, or it's a pattern clearly not tied to a specific event.
  Example: "User explicitly states 'always use feature branches'" → durable, trigger: "explicitly stated rule"
- "contextual": Tied to how the user works in this specific project or phase. May evolve as the project changes.
  Example: "User prefers script-based infra in this project" → contextual, trigger: "rejected HTTP service proposal for data pipeline"
- "incident": A reaction to a specific event, bug, or frustration. May not recur once the root cause is resolved.
  Example: "User frustrated by CC session timeouts" → incident, trigger: "npm version bug causing repeated CC crashes"

The "trigger" field is a short description of what caused the observation. Be specific — name the event, bug, tool, or conversation moment.

Note: You only see one session. If you're unsure whether something is durable or incident, lean toward the more specific classification (contextual or incident). The reflector will promote it later if it keeps appearing.
```

- [ ] **Step 4: Update observation validation in extract_observations (observe.py)**

The current validation (lines 150-156) filters observations. Keep the existing required-field checks but preserve `durability` and `trigger` if present:

```python
    observations = []
    for obs in raw_obs:
        if (isinstance(obs, dict)
            and obs.get("scope") in ("global", "project")
            and obs.get("type") in ("preference", "correction", "pattern", "decision")
            and obs.get("content")):
            # Preserve durability/trigger if present, normalize trigger key
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_observe.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/observational_memory/prompts.py src/observational_memory/observe.py tests/test_observe.py
git commit -m "feat: observer now extracts durability and trigger per observation"
```

---

### Task 3: Update Reflector — Tiered Output with Parsing

**Files:**
- Modify: `src/observational_memory/prompts.py:91-127` (REFLECTOR_SYSTEM_PROMPT, REFLECTOR_USER_PROMPT)
- Modify: `src/observational_memory/reflect.py` (synthesize, reflect_slug, parse tiered output)
- Test: `tests/test_reflect.py`

- [ ] **Step 1: Write failing test for tiered output parsing**

Add to `tests/test_reflect.py`:

```python
def test_parse_tiered_output_both_sections():
    from observational_memory.reflect import parse_tiered_output
    text = """===CORE===
git: Always feature branches.
testing: Backend requires tests.

===CONTEXTUAL===
[incident:npm-bug] User frustrated by timeouts.
[contextual:data-platform] Prefers scripts over HTTP."""
    core, context = parse_tiered_output(text)
    assert "git: Always feature branches." in core
    assert "[incident:npm-bug]" in context


def test_parse_tiered_output_core_only():
    from observational_memory.reflect import parse_tiered_output
    text = """===CORE===
git: Always feature branches."""
    core, context = parse_tiered_output(text)
    assert "git: Always feature branches." in core
    assert context is None


def test_parse_tiered_output_no_delimiters():
    """Fallback: treat entire response as core if no delimiters found."""
    from observational_memory.reflect import parse_tiered_output
    text = "git: Always feature branches.\ntesting: Backend requires tests."
    core, context = parse_tiered_output(text)
    assert "git: Always feature branches." in core
    assert context is None


def test_parse_tiered_output_empty_contextual():
    from observational_memory.reflect import parse_tiered_output
    text = """===CORE===
git: Always feature branches.

===CONTEXTUAL===
"""
    core, context = parse_tiered_output(text)
    assert "git: Always feature branches." in core
    assert context is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_reflect.py -v -k "parse_tiered"`
Expected: FAIL — parse_tiered_output doesn't exist

- [ ] **Step 3: Implement parse_tiered_output()**

Add to `src/observational_memory/reflect.py`:

```python
def parse_tiered_output(text: str) -> tuple[str, str | None]:
    """Parse reflector output into core and contextual sections.

    Returns (core_prose, context_prose_or_None).
    Fallback: if delimiters not found, treat entire response as core.
    """
    core_marker = "===CORE==="
    ctx_marker = "===CONTEXTUAL==="

    if core_marker not in text:
        # Fallback: no delimiters, treat as core
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
```

- [ ] **Step 4: Run parse tests to verify they pass**

Run: `pytest tests/test_reflect.py -v -k "parse_tiered"`
Expected: ALL PASS

- [ ] **Step 5: Write failing test for reflect_slug writing two files**

Add to `tests/test_reflect.py`:

```python
def test_reflect_slug_writes_core_and_context(tmp_path):
    """reflect_slug should write both core and context files when both sections present."""
    core_path = str(tmp_path / "test.md")
    entries = [{"type": "preference", "content": "likes tests", "durability": "durable", "trigger_summary": "stated"}]

    tiered = "===CORE===\ntesting: always write tests\n\n===CONTEXTUAL===\n[incident:bug] frustrated by timeouts"

    with patch("observational_memory.reflect.synthesize", return_value=tiered), \
         patch("observational_memory.reflect.upsert_reflection") as mock_upsert, \
         patch("observational_memory.reflect.get_max_observation_id", return_value=42):
        from observational_memory.reflect import reflect_slug
        reflect_slug("test", entries, core_path)

    with open(core_path) as f:
        assert "testing: always write tests" in f.read()

    context_path = core_path.replace(".md", "_context.md")
    with open(context_path) as f:
        assert "[incident:bug]" in f.read()

    # Verify upsert was called with context_prose
    mock_upsert.assert_called_once()
    call_kwargs = mock_upsert.call_args
    assert call_kwargs[1]["context_prose"] is not None or "[incident:bug]" in str(call_kwargs)


def test_reflect_slug_no_context_file_when_core_only(tmp_path):
    """reflect_slug should not write a context file when there's no contextual section."""
    core_path = str(tmp_path / "test.md")
    entries = [{"type": "preference", "content": "likes tests", "durability": "durable", "trigger_summary": "stated"}]

    with patch("observational_memory.reflect.synthesize", return_value="===CORE===\ntesting: always write tests"), \
         patch("observational_memory.reflect.upsert_reflection"), \
         patch("observational_memory.reflect.get_max_observation_id", return_value=42):
        from observational_memory.reflect import reflect_slug
        reflect_slug("test", entries, core_path)

    context_path = core_path.replace(".md", "_context.md")
    assert not os.path.exists(context_path)
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_reflect.py -v -k "reflect_slug_writes_core or reflect_slug_no_context"`
Expected: FAIL — reflect_slug doesn't handle tiered output

- [ ] **Step 7: Update REFLECTOR_SYSTEM_PROMPT in prompts.py**

Replace the existing reflector system prompt with tiered output instructions:

```python
REFLECTOR_SYSTEM_PROMPT = """You are a memory synthesis agent. You take raw observations about a user and synthesize them into a tiered behavioral profile.

You produce TWO sections:

===CORE===
Dense behavioral rules — firm instructions for how an AI agent should work with this user. Only durable, reinforced preferences belong here. Max 8000 characters.

===CONTEXTUAL===
Annotations with provenance — incident reactions, project-specific patterns, and evolving preferences. Each entry prefixed with [durability:trigger] (e.g., [incident:npm-timeout-bug], [contextual:data-platform-phase]).

Rules:
1. Output MUST contain ===CORE=== on its own line. ===CONTEXTUAL=== is optional (omit if nothing contextual).
2. Core section: max 8000 characters. Use flat prose with topic-prefix labels. No headers, no bullet lists. Maximize density.
3. Contextual section: uncapped but naturally dense. Each entry on its own line with [durability:trigger] prefix.
4. Entries marked [CORRECTION] are firm rules. They MUST appear in the core section.
5. If you receive existing core and contextual prose, integrate new observations. Rewrite coherently — don't append.
6. Merge duplicate or related observations.
7. Drop trivial or project-specific technical facts. Only keep observations about the USER's behavior.

Promotion/Demotion:
- If an incident-tagged observation has been reinforced by multiple new observations, extract the UNDERLYING PRINCIPLE and promote it to core. Example: repeated frustration with a specific bug → core rule "user doesn't want workarounds that ignore obvious root causes."
- If a core entry appears on re-evaluation to be incident-specific (tied to one event, not reinforced), demote it to contextual.
- Drop stale incident entries that have not been reinforced by newer observations.

For interaction_style entries: average scores per domain. Only include axes >= 0.5. Format: interaction-style: domain(axis1, axis2).

Example core format:
git: always feature branches. never commit to main. never reuse merged branches.

Example contextual format:
[incident:npm-version-bug] User escalated about CC session crashes — 5 observations from 2 sessions. Underlying preference (promoted to core): rejects workarounds for systemic issues.
[contextual:data-platform] Prefers script-based infra over HTTP services in this project — rejected API proposal."""

REFLECTOR_USER_PROMPT = """Here are the current synthesized core rules (may be empty if first reflection):

{existing_core_prose}

---

Here is the current contextual prose (may be empty):

{existing_context_prose}

---

Here are observations to integrate (with durability and trigger metadata):

{observations}

---

Produce the updated output with ===CORE=== and ===CONTEXTUAL=== sections. Core section max 8000 characters. [CORRECTION] entries are firm rules that must appear in core."""
```

- [ ] **Step 8: Update synthesize() to accept both core and context prose**

In `src/observational_memory/reflect.py`, update `synthesize()`:

```python
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
```

- [ ] **Step 9: Update reflect_slug() to handle tiered output and write two files**

```python
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
```

- [ ] **Step 10: Run all reflect tests**

Run: `pytest tests/test_reflect.py -v`
Expected: ALL PASS

- [ ] **Step 11: Run full test suite**

Run: `pytest -v`
Expected: ALL PASS

- [ ] **Step 12: Commit**

```bash
git add src/observational_memory/prompts.py src/observational_memory/reflect.py tests/test_reflect.py
git commit -m "feat: reflector produces tiered core + contextual output"
```

---

### Task 4: Update Skill File

**Files:**
- Modify: `skills/jg-context.md`
- Copy to: `~/.claude/skills/jg-context.md`

- [ ] **Step 1: Update jg-context.md Step 2 to load context files**

Replace the Step 2 section:

```markdown
## Step 2: Load Behavioral Context

1. Read `~/.observational-memory/memory/global.md` — core behavioral rules. Apply as firm instructions.
2. Read `~/.observational-memory/memory/global_context.md` if it exists — contextual annotations and provenance. Apply as informational background (explains *why* rules exist, flags evolving patterns). Not directive.
3. Derive the project slug from the current working directory basename: lowercase, replace non-alphanumeric characters with `-`, strip leading/trailing `-`.
4. Check if `~/.observational-memory/memory/projects/{slug}.md` exists. If it does, read it — project-specific core rules. Apply as firm instructions.
5. Check if `~/.observational-memory/memory/projects/{slug}_context.md` exists. If it does, read it — project-specific contextual annotations. Apply as informational background.
6. When global and project rules conflict, project rules take precedence.
```

- [ ] **Step 2: Copy to global skills directory**

```bash
cp skills/jg-context.md ~/.claude/skills/jg-context.md
```

- [ ] **Step 3: Commit**

```bash
git add skills/jg-context.md
git commit -m "feat: skill loads tiered core + context memory files"
```

---

### Task 5: Burn and Rebuild

**Files:** None (operational task — DB reset and re-processing)

- [ ] **Step 1: Delete existing DB**

```bash
rm ~/.observational-memory/memory.db ~/.observational-memory/memory.db-shm ~/.observational-memory/memory.db-wal 2>/dev/null
```

- [ ] **Step 2: Delete existing memory files**

```bash
rm -f ~/.observational-memory/memory/global.md ~/.observational-memory/memory/global_context.md
rm -f ~/.observational-memory/memory/projects/*.md
```

- [ ] **Step 3: Reinitialize DB**

```bash
observational-memory install
```

Expected: "✓ Initialized SQLite database" and "✓ Stop hook already wired"

- [ ] **Step 4: Backfill all sessions**

```bash
observational-memory backfill
```

Expected: ~159 sessions found, most processed with new durability/trigger fields

- [ ] **Step 5: Verify observations have new fields**

```bash
sqlite3 ~/.observational-memory/memory.db "SELECT durability, trigger_summary, content FROM observations WHERE durability IS NOT NULL LIMIT 5"
```

Expected: Rows with durable/contextual/incident values and trigger descriptions

- [ ] **Step 6: Reflect all projects**

```bash
observational-memory reflect --all
```

Expected: Each project produces core + context char counts

- [ ] **Step 7: Verify tiered output files**

```bash
ls ~/.observational-memory/memory/global.md ~/.observational-memory/memory/global_context.md
ls ~/.observational-memory/memory/projects/*_context.md
```

Expected: Both core and context files exist for projects that have contextual observations

- [ ] **Step 8: Spot check global.md — should be tighter than before**

```bash
cat ~/.observational-memory/memory/global.md
```

Expected: Dense core rules without incident-specific clutter
