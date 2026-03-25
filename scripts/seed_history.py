"""
Seed ghtraf dailyHistory from GitHub's 14-day traffic API window.

When ghtraf is first set up on a repository, only today's data is captured.
GitHub retains 14 days of clone/view traffic data via its API. This script
fetches that historical data and creates dailyHistory entries for days that
have no entry yet, so the dashboard shows the full available history.

This is a ROW-level operation (creates new entries for missing days).
For COLUMN-level patching (adding fields to existing entries), use
backfill_stats_fields.py instead.

Recommended order for new installations:
  1. Run ghtraf create (sets up gists, workflow, etc.)
  2. Run seed_history.py (backfills 14 days of traffic data)
  3. Run backfill_stats_fields.py (patches any missing fields)

Usage:
    python scripts/seed_history.py --gist-id GIST --owner OWNER --repo REPO
    python scripts/seed_history.py --gist-id GIST --owner OWNER --repo REPO --write
    python scripts/seed_history.py                     (reads from .ghtraf.json)
    python scripts/seed_history.py --write             (reads from .ghtraf.json)

Requires: gh CLI authenticated with gist access.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def run_gh(args):
    """Run a gh CLI command and return stdout. Exits on failure."""
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: gh {' '.join(args)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def load_ghtraf_config():
    """Try to load .ghtraf.json from current directory or parents."""
    path = Path.cwd()
    while path != path.parent:
        config_file = path / ".ghtraf.json"
        if config_file.exists():
            try:
                with open(config_file, encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        path = path.parent
    return {}


def main():
    parser = argparse.ArgumentParser(
        description="Seed ghtraf dailyHistory from GitHub's 14-day traffic API window"
    )
    parser.add_argument("--gist-id", default=None,
                        help="Badge gist ID (reads from .ghtraf.json if not set)")
    parser.add_argument("--owner", default=None,
                        help="GitHub repo owner (reads from .ghtraf.json if not set)")
    parser.add_argument("--repo", default=None,
                        help="GitHub repo name (reads from .ghtraf.json if not set)")
    parser.add_argument("--write", action="store_true",
                        help="Apply changes (default: dry-run)")
    args = parser.parse_args()

    # Resolve config: CLI args > .ghtraf.json
    gist_id = args.gist_id
    owner = args.owner
    repo = args.repo

    if not all([gist_id, owner, repo]):
        config = load_ghtraf_config()
        gist_id = gist_id or config.get("badge_gist_id")
        owner = owner or config.get("owner")
        repo = repo or config.get("repo")

    if not all([gist_id, owner, repo]):
        print("ERROR: Could not determine gist-id, owner, and repo.", file=sys.stderr)
        print("", file=sys.stderr)
        print("  Run this script from a directory with .ghtraf.json (created by", file=sys.stderr)
        print("  'ghtraf create'), or provide all three flags explicitly:", file=sys.stderr)
        print("    --gist-id GIST --owner OWNER --repo REPO", file=sys.stderr)
        print("", file=sys.stderr)
        print("  Tip: 'gh repo view --json nameWithOwner' can help identify", file=sys.stderr)
        print("  the owner/repo for the current git directory.", file=sys.stderr)
        sys.exit(1)

    mode = "WRITE" if args.write else "DRY RUN"
    print(f"Seed History [{mode}]")
    print(f"  Gist:  {gist_id}")
    print(f"  Repo:  {owner}/{repo}")
    print()

    # Fetch current state from gist
    print("Fetching gist state.json...")
    state_raw = run_gh(["api", f"gists/{gist_id}", "--jq",
                        '.files["state.json"].content'])
    state = json.loads(state_raw)

    # Save pre-seed backup
    backup_path = Path(tempfile.gettempdir()) / f"ghtraf_pre_seed_{gist_id[:8]}.json"
    backup_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"  Pre-seed backup: {backup_path}")

    existing = {e["date"] for e in state.get("dailyHistory", [])}
    print(f"  Existing dailyHistory entries: {len(existing)}")

    # Fetch traffic data from GitHub API (14-day window)
    print("\nFetching clone traffic (14-day window)...")
    clones_data = json.loads(run_gh(["api", f"repos/{owner}/{repo}/traffic/clones"]))

    print("Fetching view traffic (14-day window)...")
    views_data = json.loads(run_gh(["api", f"repos/{owner}/{repo}/traffic/views"]))

    clone_by_date = {c["timestamp"]: c for c in clones_data.get("clones", [])}
    view_by_date = {v["timestamp"]: v for v in views_data.get("views", [])}

    api_clone_total = clones_data.get("count", 0)
    api_clone_uniques = clones_data.get("uniques", 0)
    api_view_total = views_data.get("count", 0)
    api_view_uniques = views_data.get("uniques", 0)

    print(f"  Clone data: {len(clone_by_date)} days, "
          f"{api_clone_total} total, {api_clone_uniques} unique")
    print(f"  View data:  {len(view_by_date)} days, "
          f"{api_view_total} total, {api_view_uniques} unique")

    # Build missing entries
    all_dates = sorted(set(list(clone_by_date.keys()) + list(view_by_date.keys())))
    added = 0
    seeded_clones = 0
    seeded_views = 0
    seeded_unique_clones = 0
    seeded_unique_views = 0

    print("\nSeeding missing days...")
    for date in all_dates:
        if date in existing:
            continue

        c = clone_by_date.get(date, {})
        v = view_by_date.get(date, {})

        clone_count = c.get("count", 0)
        clone_uniques = c.get("uniques", 0)
        view_count = v.get("count", 0)
        view_uniques = v.get("uniques", 0)

        entry = {
            "date": date,
            "capturedAt": date,
            "clones": clone_count,
            "downloads": 0,
            "views": view_count,
            "total": clone_count + view_count,
            "ciCheckouts": 0,
            "organicClones": clone_count,
            "stars": 0,
            "forks": 0,
            "openIssues": 0,
            "uniqueClones": clone_uniques,
            "uniqueViews": view_uniques,
            "ciRuns": 0,
            "organicUniqueClones": clone_uniques,
        }
        state["dailyHistory"].append(entry)
        added += 1
        seeded_clones += clone_count
        seeded_views += view_count
        seeded_unique_clones += clone_uniques
        seeded_unique_views += view_uniques
        print(f"  + {date[:10]}: {clone_count} clones ({clone_uniques} unique), "
              f"{view_count} views ({view_uniques} unique)")

    if added == 0:
        print("  (no missing days found)")
        return

    # Sort by date
    state["dailyHistory"].sort(key=lambda x: x["date"])

    # Update trackingSince
    if state["dailyHistory"]:
        state["trackingSince"] = state["dailyHistory"][0]["date"]

    # Update top-level totals to include seeded data
    state["totalClones"] = state.get("totalClones", 0) + seeded_clones
    state["totalViews"] = state.get("totalViews", 0) + seeded_views
    state["totalUniqueClones"] = state.get("totalUniqueClones", 0) + seeded_unique_clones
    state["totalUniqueViews"] = state.get("totalUniqueViews", 0) + seeded_unique_views
    state["totalOrganicClones"] = state.get("totalOrganicClones", 0) + seeded_clones
    state["totalOrganicUniqueClones"] = state.get("totalOrganicUniqueClones", 0) + seeded_unique_clones

    # Summary
    print(f"\n{'='*50}")
    print(f"Summary:")
    print(f"  Days seeded:         {added}")
    print(f"  Total dailyHistory:  {len(state['dailyHistory'])} entries")
    print(f"  Tracking since:      {state.get('trackingSince', 'unknown')}")
    print(f"  Seeded clones:       {seeded_clones} ({seeded_unique_clones} unique)")
    print(f"  Seeded views:        {seeded_views} ({seeded_unique_views} unique)")
    print(f"  totalClones:         {state.get('totalClones', 0)}")
    print(f"  totalViews:          {state.get('totalViews', 0)}")
    print(f"  totalUniqueClones:   {state.get('totalUniqueClones', 0)}")
    print(f"  totalUniqueViews:    {state.get('totalUniqueViews', 0)}")

    if not args.write:
        print(f"\n[DRY RUN] No changes written to gist.")
        print(f"  Run with --write to apply changes.")
        print(f"  Backup at: {backup_path}")
        return

    # Write back to gist
    print(f"\nUpdating gist...")
    state_json = json.dumps(state, indent=2)
    result = subprocess.run(
        ["gh", "gist", "edit", gist_id, "-f", "state.json", "-"],
        input=state_json, capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"Gist updated at {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
        print(f"Backup at: {backup_path}")
        print("Done!")
    else:
        print(f"ERROR: {result.stderr}", file=sys.stderr)
        print(f"Backup at: {backup_path}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
