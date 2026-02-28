#!/usr/bin/env python3
"""Delete placeholder gists after verifying they contain no real data.

Safety checks before each deletion:
  - state.json: all traffic counters must be 0, dailyHistory must be empty
  - archive.json: archives list must be empty, repo must be "myorg/myproject"
  - No unexpected files (only the standard badge or archive file sets)

If ANY check fails, the gist is flagged as suspicious and skipped.
The script aborts entirely if --abort-on-suspicious is set (default).

Requires backups to exist in private/gist-baks/ (run backup_placeholder_gists.py first).

Usage:
    python tests/one-offs/cleanup_placeholder_gists.py                # dry-run
    python tests/one-offs/cleanup_placeholder_gists.py --execute      # delete
    python tests/one-offs/cleanup_placeholder_gists.py --execute --no-abort-on-suspicious
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


BADGE_FILES = {"state.json", "installs.json", "downloads.json", "clones.json", "views.json"}
ARCHIVE_FILES = {"archive.json"}

# Counters that must be zero for a gist to be considered empty
STATE_COUNTERS = [
    "totalClones", "totalUniqueClones", "totalDownloads",
    "totalViews", "totalUniqueViews", "totalCiCheckouts",
    "totalCiUniqueClones", "totalOrganicUniqueClones",
    "stars", "forks", "openIssues",
    "previousTotalDownloads", "_previousCiUniqueToday",
]

# Lists that must be empty
STATE_LISTS = [
    "lastSeenDates", "lastSeenViewDates", "dailyHistory",
    "referrers", "popularPaths",
]


def run_gh(args, input_data=None):
    """Run a gh CLI command and return stdout."""
    cmd = ["gh"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, input=input_data)
    if result.returncode != 0:
        raise RuntimeError(f"gh failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def verify_badge_gist_empty(gist_data):
    """Verify a badge gist has no real traffic data.

    Returns (is_empty, reasons) where reasons lists why it's NOT empty.
    """
    reasons = []
    files = gist_data.get("files", {})
    file_names = set(files.keys())

    # Check for unexpected files
    extra_files = file_names - BADGE_FILES
    if extra_files:
        reasons.append(f"unexpected files: {extra_files}")

    # Check state.json
    state_file = files.get("state.json", {})
    content = state_file.get("content", "")
    if not content:
        reasons.append("state.json has no content")
        return len(reasons) == 0, reasons

    try:
        state = json.loads(content)
    except json.JSONDecodeError:
        reasons.append("state.json is not valid JSON")
        return False, reasons

    # Check all counters are zero
    for key in STATE_COUNTERS:
        val = state.get(key, 0)
        if val != 0:
            reasons.append(f"{key} = {val} (expected 0)")

    # Check all lists are empty
    for key in STATE_LISTS:
        val = state.get(key, [])
        if isinstance(val, list) and len(val) > 0:
            reasons.append(f"{key} has {len(val)} entries (expected empty)")
        elif isinstance(val, dict) and len(val) > 0:
            reasons.append(f"{key} has {len(val)} keys (expected empty)")

    # Check ciCheckouts dict is empty
    ci = state.get("ciCheckouts", {})
    if isinstance(ci, dict) and len(ci) > 0:
        reasons.append(f"ciCheckouts has {len(ci)} entries (expected empty)")

    return len(reasons) == 0, reasons


def verify_archive_gist_empty(gist_data):
    """Verify an archive gist has no real archive data.

    Returns (is_empty, reasons) where reasons lists why it's NOT empty.
    """
    reasons = []
    files = gist_data.get("files", {})
    file_names = set(files.keys())

    # Check for unexpected files (allow archive-init.json as variant)
    expected = {"archive.json", "archive-init.json"}
    extra_files = file_names - expected
    if extra_files:
        reasons.append(f"unexpected files: {extra_files}")

    # Find the archive file
    archive_file = files.get("archive.json") or files.get("archive-init.json")
    if not archive_file:
        reasons.append("no archive.json or archive-init.json found")
        return False, reasons

    content = archive_file.get("content", "")
    if not content:
        reasons.append("archive file has no content")
        return False, reasons

    try:
        archive = json.loads(content)
    except json.JSONDecodeError:
        reasons.append("archive file is not valid JSON")
        return False, reasons

    # Check repo is placeholder
    repo = archive.get("repo", "")
    if repo and repo != "myorg/myproject":
        reasons.append(f"repo = \"{repo}\" (not myorg/myproject — may be real!)")

    # Check archives list is empty
    archives = archive.get("archives", [])
    if len(archives) > 0:
        reasons.append(f"archives has {len(archives)} monthly snapshots (not empty!)")

    return len(reasons) == 0, reasons


def verify_gist_empty(gist_data):
    """Verify a gist has no real data, regardless of type."""
    files = gist_data.get("files", {})
    file_names = set(files.keys())

    if "state.json" in file_names:
        return verify_badge_gist_empty(gist_data)
    elif "archive.json" in file_names or "archive-init.json" in file_names:
        return verify_archive_gist_empty(gist_data)
    else:
        return False, [f"unrecognized file set: {file_names}"]


def main():
    parser = argparse.ArgumentParser(
        description="Delete placeholder gists after verifying they're empty",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually delete gists (default is dry-run)",
    )
    parser.add_argument(
        "--no-abort-on-suspicious", action="store_true",
        help="Skip suspicious gists instead of aborting entirely",
    )
    args = parser.parse_args()

    abort_on_suspicious = not args.no_abort_on_suspicious
    mode = "EXECUTE" if args.execute else "DRY RUN"

    # Verify backups exist
    bak_dir = Path(__file__).resolve().parents[2] / "private" / "gist-baks"
    inventory_file = bak_dir / "gist_inventory.json"
    if not inventory_file.exists():
        print("ERROR: No gist inventory found. Run backup_placeholder_gists.py first.")
        sys.exit(1)

    with open(inventory_file) as f:
        inventory = json.load(f)

    placeholders = inventory.get("placeholders", [])
    if not placeholders:
        print("No placeholder gists in inventory. Nothing to do.")
        return

    print(f"[{mode}] Cleaning up {len(placeholders)} placeholder gists")
    if abort_on_suspicious:
        print("  (will ABORT if any gist looks suspicious — use --no-abort-on-suspicious to skip instead)")
    print()

    # Pre-verify ALL gists before deleting any
    print("Phase 1: Verifying all backups contain empty data...\n")
    verified = []
    suspicious = []

    for entry in placeholders:
        gist_id = entry["id"]
        bak_file = bak_dir / f"{gist_id}.json"

        if not bak_file.exists():
            print(f"  {gist_id}  MISSING BACKUP — skipping")
            suspicious.append((gist_id, ["backup file missing"]))
            continue

        with open(bak_file) as f:
            gist_data = json.load(f)

        is_empty, reasons = verify_gist_empty(gist_data)

        if is_empty:
            verified.append(gist_id)
        else:
            suspicious.append((gist_id, reasons))
            desc = gist_data.get("description", "?")
            print(f"  !!! SUSPICIOUS: {gist_id}")
            print(f"      description: {desc}")
            for r in reasons:
                print(f"      - {r}")
            print()

    print(f"  Verified empty:  {len(verified)}")
    print(f"  Suspicious:      {len(suspicious)}")
    print()

    if suspicious and abort_on_suspicious:
        print("ABORTING: Suspicious gists detected and --no-abort-on-suspicious not set.")
        print("Review the suspicious gists above before proceeding.")
        sys.exit(1)

    if not verified:
        print("No gists verified for deletion.")
        return

    # Phase 2: Delete verified gists
    print(f"Phase 2: {'Deleting' if args.execute else 'Would delete'} {len(verified)} verified-empty gists...\n")

    deleted = 0
    errors = 0

    for gist_id in verified:
        if args.execute:
            try:
                run_gh(["api", "--method", "DELETE", f"gists/{gist_id}"])
                deleted += 1
                print(f"  DELETED {gist_id}")
            except RuntimeError as e:
                errors += 1
                print(f"  ERROR   {gist_id}: {e}")
        else:
            deleted += 1
            print(f"  would delete {gist_id}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  {'Deleted' if args.execute else 'Would delete'}: {deleted}")
    print(f"  Errors:      {errors}")
    print(f"  Suspicious (skipped): {len(suspicious)}")

    if not args.execute and deleted > 0:
        print(f"\nRe-run with --execute to delete {deleted} gist(s).")

    if suspicious:
        print(f"\nSuspicious gists that were NOT deleted:")
        for gist_id, reasons in suspicious:
            print(f"  {gist_id}: {'; '.join(reasons)}")


if __name__ == "__main__":
    main()
