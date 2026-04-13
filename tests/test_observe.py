import json
from unittest.mock import patch, MagicMock

from observational_memory.observe import (
    cwd_from_session_file,
    strip_code_fences,
)


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


def test_strip_code_fences_json():
    text = '```json\n[{"scope": "global"}]\n```'
    result = strip_code_fences(text)
    assert result == '[{"scope": "global"}]'


def test_strip_code_fences_plain():
    text = '[{"scope": "global"}]'
    assert strip_code_fences(text) == text


def test_maybe_trigger_reflection_below_threshold():
    with patch("observational_memory.observe.get_unprocessed_count", return_value=50):
        with patch("observational_memory.observe.subprocess") as mock_sub:
            from observational_memory.observe import maybe_trigger_reflection
            maybe_trigger_reflection("slug")
            mock_sub.Popen.assert_not_called()


def test_maybe_trigger_reflection_above_threshold():
    with patch("observational_memory.observe.get_unprocessed_count", return_value=101):
        with patch("observational_memory.observe.subprocess") as mock_sub:
            from observational_memory.observe import maybe_trigger_reflection
            maybe_trigger_reflection("slug")
            mock_sub.Popen.assert_called_once()
