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
