import os
import re


def cc_slug(cwd: str) -> str:
    """Derive Claude Code's internal project slug from a working directory path.

    Replaces all '/' with '-'. The leading '-' is intentional and must be preserved.
    """
    return cwd.replace("/", "-")


def memory_slug(cwd: str) -> str:
    """Derive our memory file slug from a working directory path.

    Takes the basename, lowercases, replaces non-alphanumeric chars with '-',
    strips leading/trailing '-'.
    """
    base = os.path.basename(cwd).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", base)
    return slug.strip("-")
