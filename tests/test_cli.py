import json
import os
import pytest
from unittest.mock import patch, MagicMock

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


def test_observe_messages_extracts_and_stores(tmp_path):
    """observe-messages should extract observations from piped JSON and store them."""
    from observational_memory.cli import do_observe_messages

    messages = json.dumps([
        {"role": "user", "content": "Always use feature branches, never commit to main"},
        {"role": "assistant", "content": "Got it, feature branches only."},
    ])

    mock_obs = [{"scope": "global", "type": "preference", "content": "feature branches only",
                 "durability": "durable", "trigger": "explicitly stated"}]
    mock_style = {"domain": "git", "expert": 0.8, "inquisitive": 0.1, "architectural": 0.3,
                  "precise": 0.7, "scope_aware": 0.5, "risk_conscious": 0.2, "ai_led": 0.1}

    db_path = str(tmp_path / "test.db")
    with patch("sys.stdin", MagicMock(read=MagicMock(return_value=messages))), \
         patch("observational_memory.observe.extract_observations", return_value=(mock_obs, mock_style)), \
         patch("observational_memory.db.insert_observations") as mock_insert, \
         patch("observational_memory.db.insert_interaction_style") as mock_style_insert, \
         patch("observational_memory.db.mark_session_observed"), \
         patch("observational_memory.observe.maybe_trigger_reflection"):
        do_observe_messages(project="test-project", session_id="test-session-1")

    mock_insert.assert_called_once()
    assert mock_insert.call_args[0][0] == mock_obs
    assert mock_insert.call_args[0][2] == "test-project"
    mock_style_insert.assert_called_once()


def test_observe_messages_rejects_empty_input():
    from observational_memory.cli import do_observe_messages

    with patch("sys.stdin", MagicMock(read=MagicMock(return_value="[]"))):
        with pytest.raises(SystemExit) as exc_info:
            do_observe_messages(project="test")
        assert exc_info.value.code == 1


def test_observe_messages_rejects_bad_json():
    from observational_memory.cli import do_observe_messages

    with patch("sys.stdin", MagicMock(read=MagicMock(return_value="not json"))):
        with pytest.raises(SystemExit) as exc_info:
            do_observe_messages(project="test")
        assert exc_info.value.code == 1
