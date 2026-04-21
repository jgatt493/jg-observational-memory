import os
from unittest.mock import patch, MagicMock

from observational_memory.reflect import (
    validate_token_length,
    read_synthesized_prose,
    parse_tiered_output,
)


def test_validate_token_length():
    assert validate_token_length("x" * 100) is True
    assert validate_token_length("x" * 9000) is False


def test_read_synthesized_prose_missing(tmp_path):
    assert read_synthesized_prose(str(tmp_path / "nonexistent.md")) == ""


def test_read_synthesized_prose_existing(tmp_path):
    md_path = tmp_path / "test.md"
    md_path.write_text("testing: always write tests")
    assert read_synthesized_prose(str(md_path)) == "testing: always write tests"


def test_compress_prose_is_callable():
    from observational_memory.reflect import compress_prose
    import inspect
    sig = inspect.signature(compress_prose)
    assert len(sig.parameters) == 1


def test_parse_tiered_output_both_sections():
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
    text = """===CORE===
git: Always feature branches."""
    core, context = parse_tiered_output(text)
    assert "git: Always feature branches." in core
    assert context is None


def test_parse_tiered_output_no_delimiters():
    """Fallback: treat entire response as core if no delimiters found."""
    text = "git: Always feature branches.\ntesting: Backend requires tests."
    core, context = parse_tiered_output(text)
    assert "git: Always feature branches." in core
    assert context is None


def test_parse_tiered_output_empty_contextual():
    text = """===CORE===
git: Always feature branches.

===CONTEXTUAL===
"""
    core, context = parse_tiered_output(text)
    assert "git: Always feature branches." in core
    assert context is None


def test_reflect_slug_writes_core_and_context(tmp_path):
    """reflect_slug should write both core and context files when both sections present."""
    md_path = str(tmp_path / "test.md")
    entries = [{"type": "preference", "content": "likes tests", "durability": "durable", "trigger_summary": "stated"}]

    tiered = "===CORE===\ntesting: always write tests\n\n===CONTEXTUAL===\n[incident:bug] frustrated by timeouts"

    with patch("observational_memory.reflect.synthesize", return_value=tiered), \
         patch("observational_memory.reflect.upsert_reflection") as mock_upsert, \
         patch("observational_memory.reflect.get_max_observation_id", return_value=42):
        from observational_memory.reflect import reflect_slug
        reflect_slug("test", entries, md_path)

    with open(md_path) as f:
        assert "testing: always write tests" in f.read()

    context_path = str(tmp_path / "test_context.md")
    with open(context_path) as f:
        assert "[incident:bug]" in f.read()

    # Verify upsert was called with context_prose
    mock_upsert.assert_called_once()
    args, kwargs = mock_upsert.call_args
    assert kwargs.get("context_prose") == "[incident:bug] frustrated by timeouts"


def test_reflect_slug_no_context_file_when_core_only(tmp_path):
    """reflect_slug should not write a context file when there's no contextual section."""
    md_path = str(tmp_path / "test.md")
    entries = [{"type": "preference", "content": "likes tests", "durability": "durable", "trigger_summary": "stated"}]

    with patch("observational_memory.reflect.synthesize", return_value="===CORE===\ntesting: always write tests"), \
         patch("observational_memory.reflect.upsert_reflection"), \
         patch("observational_memory.reflect.get_max_observation_id", return_value=42):
        from observational_memory.reflect import reflect_slug
        reflect_slug("test", entries, md_path)

    context_path = str(tmp_path / "test_context.md")
    assert not os.path.exists(context_path)


def test_reflect_slug_removes_stale_context_file(tmp_path):
    """reflect_slug should remove stale context file when new reflection has no contextual section."""
    md_path = str(tmp_path / "test.md")
    context_path = str(tmp_path / "test_context.md")
    # Create a stale context file
    with open(context_path, "w") as f:
        f.write("old context")

    entries = [{"type": "preference", "content": "likes tests", "durability": "durable", "trigger_summary": "stated"}]

    with patch("observational_memory.reflect.synthesize", return_value="===CORE===\ntesting: always write tests"), \
         patch("observational_memory.reflect.upsert_reflection"), \
         patch("observational_memory.reflect.get_max_observation_id", return_value=42):
        from observational_memory.reflect import reflect_slug
        reflect_slug("test", entries, md_path)

    assert not os.path.exists(context_path)


def test_reflect_slug_fallback_no_delimiters(tmp_path):
    """When synthesize returns no delimiters, treat as core, no context file."""
    md_path = str(tmp_path / "test.md")
    entries = [{"type": "preference", "content": "likes tests"}]

    with patch("observational_memory.reflect.synthesize", return_value="testing: always write tests"), \
         patch("observational_memory.reflect.upsert_reflection") as mock_upsert, \
         patch("observational_memory.reflect.get_max_observation_id", return_value=42):
        from observational_memory.reflect import reflect_slug
        reflect_slug("test", entries, md_path)

    with open(md_path) as f:
        assert f.read() == "testing: always write tests"

    context_path = str(tmp_path / "test_context.md")
    assert not os.path.exists(context_path)

    args, kwargs = mock_upsert.call_args
    assert kwargs.get("context_prose") is None


def test_consolidate_global_rewrites_file(tmp_path):
    """consolidate_global should call the API and rewrite global.md."""
    global_md = tmp_path / "global.md"
    global_md.write_text("rule-a: do thing.\n\nrule-b: also do thing (same as rule-a).")

    with patch("observational_memory.reflect.MEMORY_ROOT", str(tmp_path)), \
         patch("observational_memory.reflect.anthropic") as mock_anthropic:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="rule-a: do thing. (Includes former rule-b.)")]
        mock_anthropic.Anthropic.return_value.messages.create.return_value = mock_response

        from observational_memory.reflect import consolidate_global
        consolidate_global()

    assert global_md.read_text() == "rule-a: do thing. (Includes former rule-b.)"


def test_consolidate_global_no_file(tmp_path, capsys):
    """consolidate_global should handle missing global.md gracefully."""
    with patch("observational_memory.reflect.MEMORY_ROOT", str(tmp_path)):
        from observational_memory.reflect import consolidate_global
        consolidate_global()

    assert "No global.md" in capsys.readouterr().out


def test_reflect_slug_global_triggers_consolidation(tmp_path):
    """reflect_slug for 'global' should auto-run consolidation."""
    md_path = str(tmp_path / "global.md")
    entries = [{"type": "preference", "content": "likes tests", "durability": "durable", "trigger_summary": "stated"}]

    with patch("observational_memory.reflect.synthesize", return_value="===CORE===\ntesting: always write tests"), \
         patch("observational_memory.reflect.upsert_reflection"), \
         patch("observational_memory.reflect.get_max_observation_id", return_value=42), \
         patch("observational_memory.reflect.MEMORY_ROOT", str(tmp_path)), \
         patch("observational_memory.reflect.consolidate_global") as mock_consolidate:
        from observational_memory.reflect import reflect_slug
        reflect_slug("global", entries, md_path)

    mock_consolidate.assert_called_once()
