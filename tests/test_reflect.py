from unittest.mock import patch, MagicMock

from observational_memory.reflect import (
    validate_token_length,
    read_synthesized_prose,
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


def test_reflect_slug_writes_prose(tmp_path):
    """Test that reflect_slug writes the synthesized prose to the correct file."""
    md_path = str(tmp_path / "test.md")
    entries = [{"type": "preference", "content": "likes tests"}]

    with patch("observational_memory.reflect.synthesize", return_value="testing: always write tests"):
        with patch("observational_memory.reflect.upsert_reflection"):
            with patch("observational_memory.reflect.get_max_observation_id", return_value=42):
                from observational_memory.reflect import reflect_slug
                reflect_slug("test", entries, md_path)

    with open(md_path) as f:
        assert f.read() == "testing: always write tests"
