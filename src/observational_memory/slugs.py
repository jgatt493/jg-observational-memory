import os
import re

from observational_memory.config import get_project_roots


def cc_slug(cwd: str) -> str:
    """Derive Claude Code's internal project slug from a working directory path.

    Replaces all '/' with '-'. The leading '-' is intentional and must be preserved.
    """
    return cwd.replace("/", "-")


def _slugify(name: str) -> str:
    """Lowercase a name and replace non-alphanumeric chars with dashes."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    return slug.strip("-")


def memory_slug(cwd: str) -> str:
    """Derive our memory file slug from a working directory path.

    If the cwd is inside a configured project root, uses the first path component
    relative to that root. This handles nested projects (monorepos) correctly —
    /Users/alice/Projects/my-app/packages/core → "my-app"

    Falls back to basename if no project root matches.
    """
    for root in get_project_roots():
        root = root.rstrip("/")
        if cwd.startswith(root + "/"):
            relative = cwd[len(root) + 1:]
            first_component = relative.split("/")[0]
            return _slugify(first_component)

    return _slugify(os.path.basename(cwd))
