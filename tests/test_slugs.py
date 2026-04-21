from unittest.mock import patch

from observational_memory.slugs import cc_slug, memory_slug


def test_cc_slug_basic():
    assert cc_slug("/Users/testuser/Projects/myapp") == "-Users-testuser-Projects-myapp"


def test_cc_slug_preserves_leading_dash():
    result = cc_slug("/Users/foo/bar")
    assert result.startswith("-")


def test_memory_slug_basic():
    assert memory_slug("/Users/testuser/Projects/myapp") == "myapp"


def test_memory_slug_lowercases():
    assert memory_slug("/Users/foo/Projects/DG-Chat") == "dg-chat"


def test_memory_slug_replaces_spaces():
    assert memory_slug("/Users/foo/Projects/DG Chat Server") == "dg-chat-server"


def test_memory_slug_strips_special_chars():
    assert memory_slug("/Users/foo/Projects/my_project!v2") == "my-project-v2"


def test_memory_slug_strips_leading_trailing_dashes():
    assert memory_slug("/Users/foo/Projects/-my-project-") == "my-project"


def test_memory_slug_uses_project_root():
    """When cwd is inside a project root, use first path component relative to root."""
    with patch("observational_memory.slugs.get_project_roots", return_value=["/Users/alice/Projects"]):
        assert memory_slug("/Users/alice/Projects/my-app") == "my-app"
        assert memory_slug("/Users/alice/Projects/my-app/packages/core") == "my-app"
        assert memory_slug("/Users/alice/Projects/labs-deepgram/apps/chat-blt") == "labs-deepgram"


def test_memory_slug_falls_back_to_basename():
    """When cwd is not inside any project root, fall back to basename."""
    with patch("observational_memory.slugs.get_project_roots", return_value=["/Users/alice/Projects"]):
        assert memory_slug("/tmp/scratch/experiment") == "experiment"


def test_memory_slug_multiple_roots():
    """Matches against multiple configured roots."""
    roots = ["/Users/alice/Projects", "/Users/alice/work"]
    with patch("observational_memory.slugs.get_project_roots", return_value=roots):
        assert memory_slug("/Users/alice/work/client-app/src") == "client-app"
        assert memory_slug("/Users/alice/Projects/my-app") == "my-app"


def test_memory_slug_no_roots_configured():
    """With no roots configured, always uses basename."""
    with patch("observational_memory.slugs.get_project_roots", return_value=[]):
        assert memory_slug("/Users/alice/Projects/my-app/packages/core") == "core"
