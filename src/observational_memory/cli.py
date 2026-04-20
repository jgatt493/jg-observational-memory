"""CLI entry points for observational-memory."""
from __future__ import annotations

import argparse
import json
import os
import sys

from observational_memory import __version__
from observational_memory.db import DB_PATH, init_db


def do_install(config_root: str | None = None, no_key_check: bool = False):
    """Install observational memory: create dirs, init DB, wire hook."""
    from observational_memory.api_key import resolve_api_key

    root = config_root or os.path.expanduser("~")
    om_dir = os.path.join(root, ".observational-memory")
    memory_dir = os.path.join(om_dir, "memory", "projects")
    os.makedirs(memory_dir, exist_ok=True)

    # Check for API key — try file-based resolution first
    if not no_key_check:
        resolve_api_key()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            # Interactive: prompt for the key
            if sys.stdin.isatty():
                print()
                print("  ANTHROPIC_API_KEY is required for the observer (calls Claude Haiku).")
                print("  Enter your key below — it will be saved to ~/.observational-memory/.api-key")
                print()
                try:
                    from getpass import getpass
                    key = getpass("  API key: ").strip()
                except (EOFError, KeyboardInterrupt):
                    key = ""
                if key:
                    key_path = os.path.join(om_dir, ".api-key")
                    with open(key_path, "w") as f:
                        f.write(key + "\n")
                    os.chmod(key_path, 0o600)
                    os.environ["ANTHROPIC_API_KEY"] = key
                    print("  ✓ API key saved to ~/.observational-memory/.api-key")
                else:
                    print()
                    print("  ⚠ No key provided. The observer won't work until you set one.")
                    print("  Options:")
                    print('    • export ANTHROPIC_API_KEY="sk-ant-..." in ~/.zshenv')
                    print("    • echo 'sk-ant-...' > ~/.observational-memory/.api-key")
                    print("    • Re-run: om install")
                    print()
                    print("  Continuing install without API key...")
            else:
                # Non-interactive (hook): skip silently, install anyway
                pass

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
    new_hook = {"hooks": [{"type": "command", "command": hook_command, "timeout": 30, "async": True}]}

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
    print("  • Backfill past sessions:    om backfill")
    print("  • Synthesize all profiles:   om reflect --all")


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
    print("  To fully remove: pip uninstall observational-memory")


def do_backfill():
    """Process all unobserved CC sessions."""
    from observational_memory.api_key import resolve_api_key
    from observational_memory.observe import find_all_cc_sessions, process_session, cwd_from_session_file, log_error
    from observational_memory.db import is_session_observed
    import time

    resolve_api_key()

    sessions = find_all_cc_sessions()
    total = len(sessions)
    print(f"Found {total} session files across all CC projects.\n")

    skipped = processed = failed = 0
    start_time = time.time()

    def _progress(i):
        elapsed = time.time() - start_time
        mins, secs = divmod(int(elapsed), 60)
        rate = processed / elapsed if elapsed > 0 and processed > 0 else 0
        print(
            f"\r  [{i}/{total}] "
            f"processed: {processed}  skipped: {skipped}  failed: {failed}  "
            f"({mins}m{secs:02d}s, {rate:.1f} sess/s)",
            end="", flush=True,
        )

    for i, (sid, spath) in enumerate(sessions, 1):
        try:
            if is_session_observed(sid):
                skipped += 1
                _progress(i)
                continue
        except Exception as e:
            log_error(f"Backfill DB check failed for {sid}: {e}")
            failed += 1
            _progress(i)
            continue

        cwd = cwd_from_session_file(spath)
        if not cwd:
            skipped += 1
            _progress(i)
            continue

        try:
            slug = process_session(spath, sid, cwd)
            if slug:
                processed += 1
                print(f"\r  [{i}/{total}] \u2713 {slug} <- {sid[:8]}...{' ' * 20}")
            else:
                skipped += 1
        except Exception as e:
            log_error(f"Backfill error for session {sid}: {e}")
            failed += 1
            print(f"\r  [{i}/{total}] \u2717 FAILED {sid[:8]}... \u2014 {e}{' ' * 20}")

        _progress(i)

        if processed > 0 and processed % 5 == 0:
            time.sleep(1)

    elapsed = time.time() - start_time
    mins, secs = divmod(int(elapsed), 60)
    print(f"\n\nDone in {mins}m{secs:02d}s. Processed: {processed}, Skipped: {skipped}, Failed: {failed}")


def do_reflect(slug: str | None = None, reflect_all: bool = False):
    """Synthesize observations into dense prose."""
    from observational_memory.api_key import resolve_api_key
    from observational_memory.reflect import reflect_slug
    from observational_memory.db import get_observations_for_project, get_global_observations, get_all_projects
    import time

    resolve_api_key()

    if reflect_all:
        projects = get_all_projects()
        total = len(projects) + 1  # +1 for global
        print(f"Reflecting {len(projects)} projects + global...\n")
        start_time = time.time()

        global_entries = get_global_observations()
        print(f"  [1/{total}] global ({len(global_entries)} observations)...")
        reflect_slug("global", global_entries)

        for i, project in enumerate(projects, 2):
            entries = get_observations_for_project(project)
            print(f"  [{i}/{total}] {project} ({len(entries)} observations)...")
            reflect_slug(project, entries)

        elapsed = time.time() - start_time
        mins, secs = divmod(int(elapsed), 60)
        print(f"\nDone in {mins}m{secs:02d}s. Reflected {total} profiles.")
    elif slug:
        print(f"Reflecting {slug}...")
        if slug == "global":
            entries = get_global_observations()
        else:
            entries = get_observations_for_project(slug)
        print(f"  {len(entries)} observations to synthesize...")
        reflect_slug(slug, entries)
        print("Done.")
    else:
        print("Usage: om reflect <slug> or --all")
        sys.exit(1)


def do_migrate_from_postgres(host: str, port: str, dbname: str, user: str, password: str):
    """One-time migration from existing Postgres database."""
    try:
        import psycopg2
    except ImportError:
        print("  psycopg2 is required for migration. Install it:")
        print("    pip install psycopg2-binary")
        sys.exit(1)

    from observational_memory.db import get_connection, init_db
    init_db()

    pg = psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)
    sqlite = get_connection()

    tables = {
        "observations": "INSERT INTO observations (ts, session_id, project, scope, type, content) VALUES (?, ?, ?, ?, ?, ?)",
        "interaction_styles": "INSERT INTO interaction_styles (ts, session_id, project, domain, expert, inquisitive, architectural, precise, scope_aware, risk_conscious, ai_led) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        "observed_sessions": "INSERT OR IGNORE INTO observed_sessions (session_id, project, ts, had_observations) VALUES (?, ?, ?, ?)",
        "reflections": "INSERT OR REPLACE INTO reflections (slug, prose, char_count, observation_count, ts) VALUES (?, ?, ?, ?, ?)",
    }

    for table, insert_sql in tables.items():
        cur = pg.cursor()
        cur.execute(f"SELECT * FROM {table}")
        cols = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        cur.close()

        # Map column values to the insert order
        for row in rows:
            row_dict = dict(zip(cols, row))
            if table == "observations":
                vals = (str(row_dict["ts"]), row_dict["session_id"], row_dict["project"],
                        row_dict["scope"], row_dict["type"], row_dict["content"])
            elif table == "interaction_styles":
                vals = (str(row_dict["ts"]), row_dict["session_id"], row_dict["project"],
                        row_dict["domain"], row_dict["expert"], row_dict["inquisitive"],
                        row_dict["architectural"], row_dict["precise"], row_dict["scope_aware"],
                        row_dict["risk_conscious"], row_dict["ai_led"])
            elif table == "observed_sessions":
                vals = (row_dict["session_id"], row_dict["project"], str(row_dict["ts"]),
                        int(row_dict.get("had_observations", False)))
            elif table == "reflections":
                vals = (row_dict["slug"], row_dict["prose"], row_dict.get("char_count", 0),
                        row_dict.get("observation_count", 0), str(row_dict["ts"]))
            sqlite.execute(insert_sql, vals)

        sqlite.commit()
        print(f"  ✓ {table}: {len(rows)} rows migrated")

    pg.close()
    sqlite.close()
    print("\n  Migration complete!")


def do_observe_messages(project: str, session_id: str | None = None):
    """Observe messages from stdin. Accepts JSON array of {role, content} objects."""
    import uuid
    from observational_memory.api_key import resolve_api_key
    from observational_memory.observe import extract_observations, maybe_trigger_reflection, log_error
    from observational_memory.db import insert_observations, insert_interaction_style, mark_session_observed

    resolve_api_key()

    try:
        raw = sys.stdin.read()
        messages = json.loads(raw)
    except Exception as e:
        print(f"  ✗ Failed to parse stdin as JSON: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(messages, list) or not messages:
        print("  ✗ Expected a non-empty JSON array of messages", file=sys.stderr)
        sys.exit(1)

    sid = session_id or str(uuid.uuid4())

    try:
        observations, interaction_style = extract_observations(messages, project)
    except Exception as e:
        log_error(f"observe-messages failed for {project}: {e}")
        print(f"  ✗ Observation extraction failed: {e}", file=sys.stderr)
        sys.exit(1)

    has_obs = bool(observations) or bool(interaction_style)

    if observations:
        insert_observations(observations, sid, project)
    if interaction_style and isinstance(interaction_style, dict):
        insert_interaction_style(interaction_style, sid, project)
    mark_session_observed(sid, project, has_obs)

    print(f"  {project}: {len(observations)} observations extracted (session {sid[:8]}...)")

    if has_obs:
        maybe_trigger_reflection(project)
        maybe_trigger_reflection("global")


def main():
    parser = argparse.ArgumentParser(
        prog="observational-memory",
        description="Automatic behavioral profiling for Claude Code sessions",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    install_parser = subparsers.add_parser("install", help="Set up observational memory")
    install_parser.add_argument("--no-key-check", action="store_true", help="Skip ANTHROPIC_API_KEY check")
    subparsers.add_parser("uninstall", help="Remove the Claude Code hook")
    subparsers.add_parser("backfill", help="Process all past Claude Code sessions")

    observe_parser = subparsers.add_parser("observe-messages", help="Observe messages from stdin (pipe JSON array)")
    observe_parser.add_argument("project", help="Project slug for these observations")
    observe_parser.add_argument("--session-id", help="Session ID (auto-generated if omitted)")

    reflect_parser = subparsers.add_parser("reflect", help="Synthesize observations into prose")
    reflect_parser.add_argument("slug", nargs="?", help="Project slug to reflect")
    reflect_parser.add_argument("--all", action="store_true", help="Reflect all projects + global")

    migrate_parser = subparsers.add_parser("migrate-from-postgres", help="Migrate data from Postgres")
    migrate_parser.add_argument("--host", default="localhost")
    migrate_parser.add_argument("--port", default="5432")
    migrate_parser.add_argument("--dbname", required=True, help="Postgres database name")
    migrate_parser.add_argument("--user", required=True, help="Postgres username")
    migrate_parser.add_argument("--password", required=True, help="Postgres password")

    args = parser.parse_args()

    if args.command == "install":
        do_install(no_key_check=args.no_key_check)
    elif args.command == "uninstall":
        do_uninstall()
    elif args.command == "backfill":
        do_backfill()
    elif args.command == "observe-messages":
        do_observe_messages(project=args.project, session_id=args.session_id)
    elif args.command == "reflect":
        do_reflect(slug=args.slug, reflect_all=args.all)
    elif args.command == "migrate-from-postgres":
        do_migrate_from_postgres(args.host, args.port, args.dbname, args.user, args.password)
    else:
        parser.print_help()
        sys.exit(1)
