import os
from unittest.mock import patch

from observational_memory.api_key import resolve_api_key


def test_resolve_from_env():
    """If ANTHROPIC_API_KEY is set, do nothing."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-existing"}):
        resolve_api_key()
        assert os.environ["ANTHROPIC_API_KEY"] == "sk-existing"


def test_resolve_from_key_file(tmp_path):
    """Read key from ANTHROPIC_API_KEY_FILE."""
    key_file = tmp_path / "key.txt"
    key_file.write_text("sk-from-file\n")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY_FILE": str(key_file)}, clear=True):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        resolve_api_key()
        assert os.environ["ANTHROPIC_API_KEY"] == "sk-from-file"


def test_resolve_from_default_path(tmp_path):
    """Read key from ~/.observational-memory/.api-key."""
    key_file = tmp_path / ".api-key"
    key_file.write_text("sk-from-default\n")
    with patch.dict(os.environ, {}, clear=True), \
         patch("observational_memory.api_key.os.path.expanduser", return_value=str(key_file)):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY_FILE", None)
        resolve_api_key()
        assert os.environ["ANTHROPIC_API_KEY"] == "sk-from-default"


def test_resolve_no_key_does_not_crash(tmp_path):
    """If no key found anywhere, silently return."""
    fake_path = str(tmp_path / "nonexistent" / ".api-key")
    with patch.dict(os.environ, {}, clear=True), \
         patch("observational_memory.api_key.os.path.expanduser", return_value=fake_path):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY_FILE", None)
        resolve_api_key()  # should not raise
        assert "ANTHROPIC_API_KEY" not in os.environ
