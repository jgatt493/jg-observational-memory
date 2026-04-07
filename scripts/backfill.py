"""Backfill: process all existing CC session transcripts into observational memory."""
from __future__ import annotations

import os
import sys
import time

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from observer.observe import (
    process_session,
    cwd_from_session_file,
    find_all_cc_sessions,
    log_error,
)
from observer.db import is_session_observed


def main():
    sessions = find_all_cc_sessions()
    total = len(sessions)
    print(f"Found {total} session files across all CC projects.")

    skipped = 0
    processed = 0
    failed = 0

    for i, (sid, spath) in enumerate(sessions, 1):
        # Check if already observed
        try:
            if is_session_observed(sid):
                skipped += 1
                continue
        except Exception as e:
            log_error(f"Backfill DB check failed for {sid}: {e}")
            failed += 1
            continue

        # Get cwd from session file
        cwd = cwd_from_session_file(spath)
        if not cwd:
            skipped += 1
            continue

        # Process
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

        # Brief pause to avoid hammering the API
        if processed > 0 and processed % 5 == 0:
            time.sleep(1)

    print(f"\nDone. Processed: {processed}, Skipped: {skipped}, Failed: {failed}")


if __name__ == "__main__":
    main()
