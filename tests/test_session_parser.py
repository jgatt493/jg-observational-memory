import json
import os
from observational_memory.session_parser import parse_session, extract_text_content

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


def test_parse_session_handles_content_blocks():
    """Assistant messages with content block arrays should have text extracted."""
    messages = parse_session(FIXTURE_PATH)
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert any("feature branches" in m["content"] for m in assistant_msgs)
    assert any("real database" in m["content"] for m in assistant_msgs)


def test_parse_session_extracts_tool_result_text():
    """Tool result content should be extracted from user messages."""
    messages = parse_session(FIXTURE_PATH)
    assert any("All tests passed" in m["content"] for m in messages)


def test_parse_session_skips_tool_use_only_messages():
    """Messages with only tool_use blocks (no text) should be skipped."""
    messages = parse_session(FIXTURE_PATH)
    # The tool_use-only assistant message should not appear
    assert not any("Bash" in m["content"] for m in messages)


def test_parse_session_nonexistent_file():
    messages = parse_session("/nonexistent/path.jsonl")
    assert messages == []


def test_extract_text_content_string():
    assert extract_text_content("hello") == "hello"


def test_extract_text_content_blocks():
    blocks = [
        {"type": "text", "text": "First part"},
        {"type": "tool_use", "id": "123", "name": "Bash", "input": {}},
        {"type": "text", "text": "Second part"},
    ]
    result = extract_text_content(blocks)
    assert "First part" in result
    assert "Second part" in result
    assert "Bash" not in result


def test_extract_text_content_tool_result():
    blocks = [{"type": "tool_result", "tool_use_id": "123", "content": "output text"}]
    assert extract_text_content(blocks) == "output text"


def test_extract_text_content_empty():
    assert extract_text_content("") == ""
    assert extract_text_content([]) == ""
    assert extract_text_content(None) == ""
