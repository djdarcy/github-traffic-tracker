#!/usr/bin/env python3
"""Retroactive gist rename — apply [GTT] naming convention to existing gists.

Enumerates all gists via `gh api`, identifies GTT gists by file signature
(state.json → badges, archive.json/archive-init.json → archive), and
renames them to the `[GTT] owner/repo · badges/archive` convention.

Handles three categories:
  1. Properly-named GTT gists (have real owner/repo in description) → rename
  2. Placeholder gists ("myorg/myproject") → report separately, skip by default
  3. Non-GTT gists → skip

Usage:
    python tests/one-offs/rename_gists.py                  # dry-run by default
    python tests/one-offs/rename_gists.py --execute        # actually rename
    python tests/one-offs/rename_gists.py --include-placeholders  # also show placeholder gists
"""

import argparse
import json
import re
import subprocess
import sys


def run_gh(args, input_data=None):
    """Run a gh CLI command and return stdout."""
    cmd = ["gh"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=input_data,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def fetch_all_gists():
    """Fetch all gists for the authenticated user."""
    raw = run_gh([
        "api", "gists", "--paginate",
        "--jq", '[ .[] | {id: .id, description: .description, files: [.files | keys[]]} ]',
    ])
    # --paginate with --jq may produce multiple JSON arrays; merge them
    arrays = []
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(raw):
        # Skip whitespace
        while pos < len(raw) and raw[pos] in ' \t\n\r':
            pos += 1
        if pos >= len(raw):
            break
        obj, end = decoder.raw_decode(raw, pos)
        if isinstance(obj, list):
            arrays.extend(obj)
        else:
            arrays.append(obj)
        pos = end
    return arrays


def classify_gist(gist):
    """Classify a gist as badge, archive, or non-GTT.

    Returns:
        ("badges", current_repo) — badge gist with identifiable repo
        ("archive", current_repo) — archive gist with identifiable repo
        ("placeholder-badges", None) — badge gist with myorg/myproject placeholder
        ("placeholder-archive", None) — archive gist with myorg/myproject placeholder
        (None, None) — not a GTT gist
    """
    files = set(gist.get("files", []))
    desc = gist.get("description", "")

    is_badge = "state.json" in files
    is_archive = "archive.json" in files or "archive-init.json" in files

    if not is_badge and not is_archive:
        return None, None

    kind = "badges" if is_badge else "archive"

    # Check if description has a real repo or is a placeholder
    if "myorg/myproject" in desc:
        return f"placeholder-{kind}", None

    # Try to extract owner/repo from current description
    # Patterns: "owner/repo traffic badges", "owner/repo traffic archive",
    #           "owner/repo traffic archives (private)"
    match = re.match(r'^(?:\[GTT\]\s+)?(\S+/\S+)\s+traffic\s+', desc)
    if match:
        repo = match.group(1)
        return kind, repo

    # Description doesn't match expected pattern — might be a GTT gist
    # that was manually renamed. Skip it.
    return None, None


def compute_expected_description(repo, kind):
    """Build the expected [GTT] description."""
    return f"[GTT] {repo} \u00b7 {kind}"


def rename_gist(gist_id, new_description, execute=False):
    """Rename a gist's description via the GitHub API."""
    if not execute:
        return True

    payload = json.dumps({"description": new_description})
    try:
        run_gh(
            ["api", "--method", "PATCH", f"gists/{gist_id}", "--input", "-"],
            input_data=payload,
        )
        return True
    except RuntimeError as e:
        print(f"  ERROR: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Rename GTT gists to [GTT] owner/repo \u00b7 kind convention",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Actually rename gists (default is dry-run)",
    )
    parser.add_argument(
        "--include-placeholders", action="store_true",
        help="Show placeholder gists (myorg/myproject) in the report",
    )
    args = parser.parse_args()

    mode = "EXECUTE" if args.execute else "DRY RUN"
    print(f"[{mode}] Scanning gists for GTT naming convention...\n")

    gists = fetch_all_gists()
    print(f"Found {len(gists)} total gists.\n")

    renamed = 0
    already_correct = 0
    errors = 0
    skipped_non_gtt = 0
    placeholders = []

    for g in gists:
        gist_id = g["id"]
        desc = g.get("description", "")
        kind, repo = classify_gist(g)

        if kind is None:
            skipped_non_gtt += 1
            continue

        if kind.startswith("placeholder-"):
            placeholders.append((gist_id, desc, kind.replace("placeholder-", "")))
            continue

        expected = compute_expected_description(repo, kind)

        if desc == expected:
            already_correct += 1
            continue

        # Needs renaming
        print(f"  {gist_id}")
        print(f"    old: {desc}")
        print(f"    new: {expected}")

        if rename_gist(gist_id, expected, execute=args.execute):
            renamed += 1
            if args.execute:
                print(f"    -> renamed")
            else:
                print(f"    -> would rename")
        else:
            errors += 1
        print()

    # Summary
    print("=" * 60)
    print(f"Summary:")
    print(f"  Renamed:           {renamed}")
    print(f"  Already correct:   {already_correct}")
    print(f"  Errors:            {errors}")
    print(f"  Non-GTT (skipped): {skipped_non_gtt}")
    print(f"  Placeholders:      {len(placeholders)}")

    if placeholders:
        print(f"\n{'=' * 60}")
        print(f"Placeholder gists ({len(placeholders)} found):")
        print("These have 'myorg/myproject' descriptions and no real repo data.")
        if args.include_placeholders:
            for gist_id, desc, kind in placeholders:
                print(f"  {gist_id}  ({kind})  {desc}")
        else:
            print("  Use --include-placeholders to list them.")
        print("\nTo fix these, either:")
        print("  1. Delete them if they're unused test gists:")
        print("     gh api --method DELETE gists/GIST_ID")
        print("  2. Manually rename if you know which repo they belong to:")
        print('     gh api --method PATCH gists/GIST_ID -f description="[GTT] owner/repo \u00b7 badges"')

    if not args.execute and renamed > 0:
        print(f"\nRe-run with --execute to apply {renamed} rename(s).")


if __name__ == "__main__":
    main()
