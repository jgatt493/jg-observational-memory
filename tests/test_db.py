import os
import sqlite3
from unittest.mock import patch

import pytest

from observational_memory.db import (
    init_db,
    insert_observations,
    insert_interaction_style,
    mark_session_observed,
    is_session_observed,
    get_observations_for_project,
    get_global_observations,
    get_all_projects,
    upsert_reflection,
    get_unprocessed_count,
)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path):
    """Patch DB_PATH for all tests in this module."""
    db_path = str(tmp_path / "test.db")
    with patch("observational_memory.db.DB_PATH", db_path):
        init_db()
        yield db_path


def test_init_db_creates_tables(tmp_db):
    conn = sqlite3.connect(tmp_db)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = sorted(r[0] for r in cur.fetchall())
    conn.close()
    assert "interaction_styles" in tables
    assert "observations" in tables
    assert "observed_sessions" in tables
    assert "reflections" in tables


def test_init_db_enables_wal(tmp_db):
    conn = sqlite3.connect(tmp_db)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal"


def test_insert_and_get_observations(tmp_db):
    obs = [
        {"scope": "project", "type": "preference", "content": "likes tests"},
        {"scope": "global", "type": "correction", "content": "never mock DB"},
    ]
    insert_observations(obs, "session-1", "myproj")
    result = get_observations_for_project("myproj")
    assert len(result) == 2
    assert result[0]["content"] == "likes tests"


def test_get_global_observations(tmp_db):
    obs = [
        {"scope": "global", "type": "preference", "content": "global rule"},
        {"scope": "project", "type": "preference", "content": "project only"},
    ]
    insert_observations(obs, "session-1", "proj")
    result = get_global_observations()
    assert len(result) == 1
    assert result[0]["content"] == "global rule"


def test_insert_interaction_style(tmp_db):
    style = {
        "domain": "frontend",
        "expert": 0.8, "inquisitive": 0.2, "architectural": 0.5,
        "precise": 0.9, "scope_aware": 0.4, "risk_conscious": 0.3, "ai_led": 0.1,
    }
    insert_interaction_style(style, "session-1", "myproj")
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT domain, expert FROM interaction_styles").fetchone()
    conn.close()
    assert row[0] == "frontend"
    assert row[1] == pytest.approx(0.8)


def test_mark_and_check_session_observed(tmp_db):
    assert is_session_observed("s1") is False
    mark_session_observed("s1", "proj", True)
    assert is_session_observed("s1") is True


def test_mark_session_observed_idempotent(tmp_db):
    mark_session_observed("s1", "proj", True)
    mark_session_observed("s1", "proj", False)  # Should not raise
    assert is_session_observed("s1") is True


def test_upsert_reflection(tmp_db):
    upsert_reflection("myproj", "testing: always write tests", 5, 42)
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT prose, observation_count, last_observation_id FROM reflections WHERE slug = ?", ("myproj",)).fetchone()
    conn.close()
    assert row[0] == "testing: always write tests"
    assert row[1] == 5
    assert row[2] == 42


def test_upsert_reflection_updates(tmp_db):
    upsert_reflection("myproj", "v1", 5, 10)
    upsert_reflection("myproj", "v2", 10, 50)
    conn = sqlite3.connect(tmp_db)
    row = conn.execute("SELECT prose, last_observation_id FROM reflections WHERE slug = ?", ("myproj",)).fetchone()
    conn.close()
    assert row[0] == "v2"
    assert row[1] == 50


def test_get_all_projects(tmp_db):
    insert_observations([{"scope": "project", "type": "preference", "content": "a"}], "s1", "proj-a")
    insert_observations([{"scope": "project", "type": "preference", "content": "b"}], "s2", "proj-b")
    projects = get_all_projects()
    assert "proj-a" in projects
    assert "proj-b" in projects


def test_get_unprocessed_count(tmp_db):
    insert_observations([{"scope": "project", "type": "preference", "content": f"obs-{i}"} for i in range(5)], "s1", "myproj")
    assert get_unprocessed_count("myproj") == 5
    upsert_reflection("myproj", "prose", 5, 3)  # last_observation_id=3
    assert get_unprocessed_count("myproj") == 2


def test_get_unprocessed_count_global(tmp_db):
    insert_observations([
        {"scope": "global", "type": "preference", "content": "global-1"},
        {"scope": "global", "type": "preference", "content": "global-2"},
        {"scope": "project", "type": "preference", "content": "project-only"},
    ], "s1", "someproj")
    assert get_unprocessed_count("global") == 2


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
    obs = [{"scope": "global", "type": "preference", "content": "likes tests"}]
    insert_observations(obs, "session-1", "myproj")
    result = get_observations_for_project("myproj")
    assert result[0]["durability"] is None
    assert result[0]["trigger_summary"] is None


def test_insert_observations_rejects_invalid_durability(tmp_db):
    obs = [{"scope": "global", "type": "preference", "content": "test",
            "durability": "bogus", "trigger": "test"}]
    with pytest.raises(sqlite3.IntegrityError):
        insert_observations(obs, "session-1", "myproj")


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
