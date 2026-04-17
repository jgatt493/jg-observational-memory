import json
import os
from observational_memory.session_parser import parse_session, extract_text_content

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_session.jsonl")


def test_parse_session_returns_messages():
    messages, total = parse_session(FIXTURE_PATH)
    assert len(messages) > 0
    assert total > 0


def test_parse_session_extracts_only_user_and_assistant():
    messages, _ = parse_session(FIXTURE_PATH)
    roles = {m["role"] for m in messages}
    assert roles == {"user", "assistant"}


def test_parse_session_preserves_order():
    messages, _ = parse_session(FIXTURE_PATH)
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"


def test_parse_session_extracts_content():
    messages, _ = parse_session(FIXTURE_PATH)
    assert "feature branches" in messages[0]["content"]


def test_parse_session_handles_content_blocks():
    """Assistant messages with content block arrays should have text extracted."""
    messages, _ = parse_session(FIXTURE_PATH)
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert any("feature branches" in m["content"] for m in assistant_msgs)
    assert any("real database" in m["content"] for m in assistant_msgs)


def test_parse_session_extracts_tool_result_text():
    """Tool result content should be extracted from user messages."""
    messages, _ = parse_session(FIXTURE_PATH)
    assert any("All tests passed" in m["content"] for m in messages)


def test_parse_session_skips_tool_use_only_messages():
    """Messages with only tool_use blocks (no text) should be skipped."""
    messages, _ = parse_session(FIXTURE_PATH)
    assert not any("Bash" in m["content"] for m in messages)


def test_parse_session_nonexistent_file():
    messages, total = parse_session("/nonexistent/path.jsonl")
    assert messages == []
    assert total == 0


def test_parse_session_start_line(tmp_path):
    """Parsing from a start_line should skip earlier messages."""
    session = tmp_path / "test.jsonl"
    lines = [
        json.dumps({"type": "user", "message": {"role": "user", "content": "first message"}}),
        json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "first reply"}}),
        json.dumps({"type": "user", "message": {"role": "user", "content": "second message"}}),
        json.dumps({"type": "assistant", "message": {"role": "assistant", "content": "second reply"}}),
    ]
    session.write_text("\n".join(lines) + "\n")

    # Parse all
    all_msgs, total = parse_session(str(session))
    assert len(all_msgs) == 4
    assert total == 4

    # Parse from line 2 (skip first two)
    partial_msgs, total = parse_session(str(session), start_line=2)
    assert len(partial_msgs) == 2
    assert partial_msgs[0]["content"] == "second message"
    assert total == 4


def test_parse_session_start_line_past_end(tmp_path):
    """Parsing from beyond file end should return no messages."""
    session = tmp_path / "test.jsonl"
    session.write_text(json.dumps({"type": "user", "message": {"role": "user", "content": "hello"}}) + "\n")

    msgs, total = parse_session(str(session), start_line=100)
    assert msgs == []
    assert total == 1


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
