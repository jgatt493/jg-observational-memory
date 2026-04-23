import json
from unittest.mock import patch, MagicMock

from observational_memory.observe import (
    cwd_from_session_file,
    extract_json_block,
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


def test_extract_json_block_clean():
    text = '{"observations": [], "interaction_style": {}}'
    assert json.loads(extract_json_block(text)) == json.loads(text)


def test_extract_json_block_trailing_prose():
    text = '{"observations": []} \n\n**Rationale:** The user prefers...'
    result = extract_json_block(text)
    assert json.loads(result) == {"observations": []}


def test_extract_json_block_preamble_and_fences():
    text = '```json\n{"observations": []}\n```\nSome extra text'
    result = extract_json_block(text)
    assert json.loads(result) == {"observations": []}


def test_extract_json_block_no_json():
    text = "Done. Skill is wired up and ready to go."
    assert extract_json_block(text) is None


def test_extract_json_block_nested_braces():
    text = '{"observations": [{"content": "uses {curly} braces"}]}'
    result = extract_json_block(text)
    parsed = json.loads(result)
    assert parsed["observations"][0]["content"] == "uses {curly} braces"


def test_main_reads_snake_case_session_id():
    """main() should accept session_id (snake_case) from hook payload."""
    payload = json.dumps({
        "session_id": "abc123",
        "cwd": "/Users/test/Projects/myapp",
    })
    with patch("sys.stdin", MagicMock(read=MagicMock(return_value=payload))), \
         patch("observational_memory.observe.process_session", return_value=None), \
         patch("observational_memory.observe.find_all_cc_sessions", return_value=[]), \
         patch("observational_memory.observe.log_error") as mock_log:
        from observational_memory.observe import main
        main()
        # Should NOT log a missing sessionId error
        for call in mock_log.call_args_list:
            assert "Missing sessionId" not in call[0][0]


def test_main_reads_camel_case_session_id():
    """main() should still accept sessionId (camelCase) for backwards compat."""
    payload = json.dumps({
        "sessionId": "abc123",
        "cwd": "/Users/test/Projects/myapp",
    })
    with patch("sys.stdin", MagicMock(read=MagicMock(return_value=payload))), \
         patch("observational_memory.observe.process_session", return_value=None), \
         patch("observational_memory.observe.find_all_cc_sessions", return_value=[]), \
         patch("observational_memory.observe.log_error") as mock_log:
        from observational_memory.observe import main
        main()
        for call in mock_log.call_args_list:
            assert "Missing sessionId" not in call[0][0]


def test_main_rejects_missing_session_id():
    """main() should exit when neither session_id nor sessionId is present."""
    payload = json.dumps({"cwd": "/Users/test/Projects/myapp"})
    with patch("sys.stdin", MagicMock(read=MagicMock(return_value=payload))), \
         patch("observational_memory.observe.log_error") as mock_log:
        from observational_memory.observe import main
        try:
            main()
        except SystemExit:
            pass
        mock_log.assert_called()
        assert "Missing sessionId" in mock_log.call_args[0][0]


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
    assert "durability" not in obs[0]


def test_maybe_trigger_reflection_below_threshold():
    with patch("observational_memory.observe.get_unprocessed_count", return_value=30), \
         patch("observational_memory.observe.has_reflection", return_value=True):
        with patch("observational_memory.observe.subprocess") as mock_sub:
            from observational_memory.observe import maybe_trigger_reflection
            maybe_trigger_reflection("slug")
            mock_sub.Popen.assert_not_called()


def test_maybe_trigger_reflection_above_threshold():
    with patch("observational_memory.observe.get_unprocessed_count", return_value=50), \
         patch("observational_memory.observe.has_reflection", return_value=True):
        with patch("observational_memory.observe.subprocess") as mock_sub:
            from observational_memory.observe import maybe_trigger_reflection
            maybe_trigger_reflection("slug")
            mock_sub.Popen.assert_called_once()


def test_maybe_trigger_first_reflection_low_threshold():
    """First reflection triggers at 10 observations, not 50."""
    with patch("observational_memory.observe.get_unprocessed_count", return_value=10), \
         patch("observational_memory.observe.has_reflection", return_value=False):
        with patch("observational_memory.observe.subprocess") as mock_sub:
            from observational_memory.observe import maybe_trigger_reflection
            maybe_trigger_reflection("slug")
            mock_sub.Popen.assert_called_once()


def test_maybe_trigger_first_reflection_below_threshold():
    """Below 10 observations, even first reflection doesn't trigger."""
    with patch("observational_memory.observe.get_unprocessed_count", return_value=5), \
         patch("observational_memory.observe.has_reflection", return_value=False):
        with patch("observational_memory.observe.subprocess") as mock_sub:
            from observational_memory.observe import maybe_trigger_reflection
            maybe_trigger_reflection("slug")
            mock_sub.Popen.assert_not_called()
