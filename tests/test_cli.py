import json
import os
import pytest
from unittest.mock import patch

from observational_memory.cli import do_install, do_uninstall


@pytest.fixture(autouse=True)
def fake_api_key():
    """Set a fake API key for all install tests."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test-fake-key"}):
        yield


def test_install_fails_without_api_key(tmp_path):
    """Install must hard-fail when ANTHROPIC_API_KEY is not set."""
    config_root = str(tmp_path)
    with patch.dict(os.environ, {}, clear=True), \
         patch("observational_memory.cli.DB_PATH", str(tmp_path / "memory.db")), \
         patch("observational_memory.cli.init_db"):
        # Remove the key explicitly
        os.environ.pop("ANTHROPIC_API_KEY", None)
        with pytest.raises(SystemExit) as exc_info:
            do_install(config_root=config_root)
        assert exc_info.value.code == 1


def test_install_creates_dirs(tmp_path):
    config_root = str(tmp_path)
    with patch("observational_memory.cli.DB_PATH", str(tmp_path / "memory.db")):
        with patch("observational_memory.cli.init_db"):
            do_install(config_root=config_root)

    assert (tmp_path / ".observational-memory").is_dir()
    assert (tmp_path / ".observational-memory" / "memory" / "projects").is_dir()


def test_install_creates_settings_with_hook(tmp_path):
    config_root = str(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    settings_path.write_text("{}")

    with patch("observational_memory.cli.DB_PATH", str(tmp_path / "memory.db")):
        with patch("observational_memory.cli.init_db"):
            do_install(config_root=config_root)

    settings = json.loads(settings_path.read_text())
    assert "hooks" in settings
    assert "Stop" in settings["hooks"]
    hook_commands = [
        h["hooks"][0]["command"]
        for h in settings["hooks"]["Stop"]
        if isinstance(h, dict) and h.get("hooks")
    ]
    assert any("observational_memory" in cmd for cmd in hook_commands)


def test_install_skips_duplicate_hook(tmp_path):
    config_root = str(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps({
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python -m observational_memory.observe"}]}]}
    }))

    with patch("observational_memory.cli.DB_PATH", str(tmp_path / "memory.db")):
        with patch("observational_memory.cli.init_db"):
            do_install(config_root=config_root)

    settings = json.loads(settings_path.read_text())
    assert len(settings["hooks"]["Stop"]) == 1


def test_uninstall_removes_hook(tmp_path):
    config_root = str(tmp_path)
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    settings_path = claude_dir / "settings.json"
    settings_path.write_text(json.dumps({
        "hooks": {
            "Stop": [
                {"hooks": [{"type": "command", "command": "some-other-hook"}]},
                {"hooks": [{"type": "command", "command": "python -m observational_memory.observe"}]},
            ]
        }
    }))

    do_uninstall(config_root=config_root)

    settings = json.loads(settings_path.read_text())
    assert len(settings["hooks"]["Stop"]) == 1
    assert "observational_memory" not in settings["hooks"]["Stop"][0]["hooks"][0]["command"]
