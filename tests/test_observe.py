import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from observer.observe import (
    append_observations,
    check_and_trigger_reflector,
    cwd_from_session_file,
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
    assert record["scope"] == "project"
    assert record["content"] == "likes feature branches"
    assert "ts" in record


def test_append_observations_appends(tmp_path):
    log_path = tmp_path / "test.jsonl"
    log_path.write_text('{"existing": true}\n')
    obs = [{"scope": "project", "type": "decision", "content": "use postgres"}]
    append_observations(str(log_path), obs, "s1", "proj")
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 2


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


def test_cwd_from_session_file(tmp_path):
    session = tmp_path / "test.jsonl"
    session.write_text(json.dumps({
        "type": "progress",
        "cwd": "/Users/test/Projects/myapp",
        "sessionId": "abc123",
    }) + "\n")
    assert cwd_from_session_file(str(session)) == "/Users/test/Projects/myapp"


def test_cwd_from_session_file_missing():
    assert cwd_from_session_file("/nonexistent/file.jsonl") is None


def test_cwd_from_session_file_no_cwd(tmp_path):
    session = tmp_path / "test.jsonl"
    session.write_text(json.dumps({"type": "system"}) + "\n")
    assert cwd_from_session_file(str(session)) is None
