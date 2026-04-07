from observer.slugs import cc_slug, memory_slug


def test_cc_slug_basic():
    assert cc_slug("/Users/jeremygatt/Projects/dg2") == "-Users-jeremygatt-Projects-dg2"


def test_cc_slug_preserves_leading_dash():
    result = cc_slug("/Users/foo/bar")
    assert result.startswith("-")


def test_memory_slug_basic():
    assert memory_slug("/Users/jeremygatt/Projects/dg2") == "dg2"


def test_memory_slug_lowercases():
    assert memory_slug("/Users/foo/Projects/DG-Chat") == "dg-chat"


def test_memory_slug_replaces_spaces():
    assert memory_slug("/Users/foo/Projects/DG Chat Server") == "dg-chat-server"


def test_memory_slug_strips_special_chars():
    assert memory_slug("/Users/foo/Projects/my_project!v2") == "my-project-v2"


def test_memory_slug_strips_leading_trailing_dashes():
    assert memory_slug("/Users/foo/Projects/-my-project-") == "my-project"
