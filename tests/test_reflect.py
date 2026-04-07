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


def test_compress_prose_is_callable():
    """Verify compress_prose exists and accepts a string."""
    from observer.reflect import compress_prose
    # Just verify it's importable and has the right signature
    import inspect
    sig = inspect.signature(compress_prose)
    assert len(sig.parameters) == 1
