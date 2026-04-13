"""CLI entry points for observational-memory."""
from __future__ import annotations

import argparse
import json
import os
import sys

from observational_memory import __version__
from observational_memory.db import DB_PATH, init_db


def do_install(config_root: str | None = None):
    """Install observational memory: create dirs, init DB, wire hook."""
    root = config_root or os.path.expanduser("~")
    om_dir = os.path.join(root, ".observational-memory")
    memory_dir = os.path.join(om_dir, "memory", "projects")
    os.makedirs(memory_dir, exist_ok=True)

    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  ⚠ ANTHROPIC_API_KEY not set. The observer needs it to call Claude Haiku.")
        print("    Set it in your shell profile before using.")

    # Init DB
    init_db()
    print("  ✓ Initialized SQLite database")

    # Wire CC Stop hook
    claude_dir = os.path.join(root, ".claude")
    os.makedirs(claude_dir, exist_ok=True)
    settings_path = os.path.join(claude_dir, "settings.json")

    if os.path.exists(settings_path):
        with open(settings_path) as f:
            settings = json.load(f)
    else:
        settings = {}

    hook_command = "python -m observational_memory.observe"
    new_hook = {"hooks": [{"type": "command", "command": hook_command, "timeout": 30}]}

    hooks = settings.setdefault("hooks", {})
    stop_hooks = hooks.setdefault("Stop", [])

    already_wired = any(
        "observational_memory" in h.get("hooks", [{}])[0].get("command", "")
        for h in stop_hooks
        if isinstance(h, dict) and h.get("hooks")
    )

    if already_wired:
        print("  ✓ Stop hook already wired")
    else:
        stop_hooks.append(new_hook)
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
        print("  ✓ Wired Claude Code Stop hook")

    print()
    print("  ✓ Setup complete!")
    print()
    print("  Observations will be extracted automatically after each Claude Code session.")
    print()
    print("  Optional next steps:")
    print("  • Backfill past sessions:    observational-memory backfill")
    print("  • Synthesize all profiles:   observational-memory reflect --all")


def do_uninstall(config_root: str | None = None):
    """Remove the Stop hook. Preserve data."""
    root = config_root or os.path.expanduser("~")
    settings_path = os.path.join(root, ".claude", "settings.json")

    if not os.path.exists(settings_path):
        print("  No settings.json found — nothing to remove.")
        return

    with open(settings_path) as f:
        settings = json.load(f)

    stop_hooks = settings.get("hooks", {}).get("Stop", [])
    filtered = [
        h for h in stop_hooks
        if not (isinstance(h, dict) and h.get("hooks") and
                "observational_memory" in h["hooks"][0].get("command", ""))
    ]
    settings.setdefault("hooks", {})["Stop"] = filtered

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)

    om_dir = os.path.join(root, ".observational-memory")
    print("  ✓ Removed Stop hook from Claude Code settings")
    print(f"  Data preserved at {om_dir} — delete manually if desired.")
    print("  Then: pip uninstall observational-memory")


def do_backfill():
    """Process all unobserved CC sessions."""
    from observational_memory.observe import find_all_cc_sessions, process_session, cwd_from_session_file, log_error
    from observational_memory.db import is_session_observed
    import time

    sessions = find_all_cc_sessions()
    print(f"Found {len(sessions)} session files across all CC projects.")

    skipped = processed = failed = 0
    total = len(sessions)

    for i, (sid, spath) in enumerate(sessions, 1):
        try:
            if is_session_observed(sid):
                skipped += 1
                continue
        except Exception as e:
            log_error(f"Backfill DB check failed for {sid}: {e}")
            failed += 1
            continue

        cwd = cwd_from_session_file(spath)
        if not cwd:
            skipped += 1
            continue

        try:
            slug = process_session(spath, sid, cwd)
            if slug:
                processed += 1
                print(f"  [{i}/{total}] {slug} <- session {sid[:8]}...")
            else:
                skipped += 1
        except Exception as e:
            log_error(f"Backfill error for session {sid}: {e}")
            failed += 1
            print(f"  [{i}/{total}] FAILED session {sid[:8]}... — {e}")

        if processed > 0 and processed % 5 == 0:
            time.sleep(1)

    print(f"\nDone. Processed: {processed}, Skipped: {skipped}, Failed: {failed}")


def do_reflect(slug: str | None = None, reflect_all: bool = False):
    """Synthesize observations into dense prose."""
    from observational_memory.reflect import reflect_slug
    from observational_memory.db import get_observations_for_project, get_global_observations, get_all_projects

    if reflect_all:
        projects = get_all_projects()
        print(f"Reflecting {len(projects)} projects + global...")
        global_entries = get_global_observations()
        reflect_slug("global", global_entries)
        for project in projects:
            entries = get_observations_for_project(project)
            reflect_slug(project, entries)
        print("Done.")
    elif slug:
        if slug == "global":
            entries = get_global_observations()
        else:
            entries = get_observations_for_project(slug)
        reflect_slug(slug, entries)
    else:
        print("Usage: observational-memory reflect <slug> or --all")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="observational-memory",
        description="Automatic behavioral profiling for Claude Code sessions",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("install", help="Set up observational memory")
    subparsers.add_parser("uninstall", help="Remove the Claude Code hook")
    subparsers.add_parser("backfill", help="Process all past Claude Code sessions")

    reflect_parser = subparsers.add_parser("reflect", help="Synthesize observations into prose")
    reflect_parser.add_argument("slug", nargs="?", help="Project slug to reflect")
    reflect_parser.add_argument("--all", action="store_true", help="Reflect all projects + global")

    args = parser.parse_args()

    if args.command == "install":
        do_install()
    elif args.command == "uninstall":
        do_uninstall()
    elif args.command == "backfill":
        do_backfill()
    elif args.command == "reflect":
        do_reflect(slug=args.slug, reflect_all=args.all)
    else:
        parser.print_help()
        sys.exit(1)
