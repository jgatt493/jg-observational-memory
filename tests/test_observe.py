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
