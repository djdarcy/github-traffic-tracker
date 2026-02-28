#!/usr/bin/env python3
"""Backup all placeholder gists before cleanup.

Saves full gist data (metadata + file contents) for each "myorg/myproject"
placeholder gist to private/gist-baks/. Also generates a summary of all
GTT gists showing which are active vs placeholder.

Usage:
    python tests/one-offs/backup_placeholder_gists.py
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_gh(args, input_data=None):
    """Run a gh CLI command and return stdout."""
    cmd = ["gh"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, input=input_data)
    if result.returncode != 0:
        raise RuntimeError(f"gh failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def fetch_all_gists():
    """Fetch all gists with full metadata."""
    raw = run_gh([
        "api", "gists", "--paginate",
        "--jq", '[ .[] | {id: .id, description: .description, '
                'html_url: .html_url, public: .public, '
                'created_at: .created_at, updated_at: .updated_at, '
                'files: (.files | to_entries | map({name: .key, size: .value.size, '
                'type: .value.type, language: .value.language})) } ]',
    ])
    arrays = []
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(raw):
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


def fetch_gist_content(gist_id):
    """Fetch full gist data including file contents."""
    raw = run_gh(["api", f"gists/{gist_id}"])
    return json.loads(raw)


def main():
    backup_dir = Path(__file__).resolve().parents[2] / "private" / "gist-baks"
    backup_dir.mkdir(parents=True, exist_ok=True)

    print("Fetching gist list...")
    gists = fetch_all_gists()
    print(f"Found {len(gists)} total gists.\n")

    # Classify gists
    placeholders = []
    active_gtt = []
    non_gtt = []

    for g in gists:
        desc = g.get("description", "")
        file_names = [f["name"] for f in g.get("files", [])]
        has_state = "state.json" in file_names
        has_archive = "archive.json" in file_names or "archive-init.json" in file_names

        if not has_state and not has_archive:
            non_gtt.append(g)
        elif "myorg/myproject" in desc:
            placeholders.append(g)
        else:
            active_gtt.append(g)

    # Back up placeholder gists
    print(f"Backing up {len(placeholders)} placeholder gists...")
    for i, g in enumerate(placeholders, 1):
        gist_id = g["id"]
        print(f"  [{i}/{len(placeholders)}] {gist_id} — {g['description'][:60]}")

        try:
            full_data = fetch_gist_content(gist_id)

            # Save full gist data
            backup_file = backup_dir / f"{gist_id}.json"
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(full_data, f, indent=2)

        except RuntimeError as e:
            print(f"    ERROR: {e}")

    # Generate summary
    summary = {
        "generated": datetime.now().isoformat(),
        "total_gists": len(gists),
        "active_gtt": [],
        "placeholders": [],
        "non_gtt": [],
    }

    for g in active_gtt:
        file_names = [f["name"] for f in g.get("files", [])]
        summary["active_gtt"].append({
            "id": g["id"],
            "description": g["description"],
            "public": g["public"],
            "created": g["created_at"],
            "updated": g["updated_at"],
            "files": file_names,
        })

    for g in placeholders:
        file_names = [f["name"] for f in g.get("files", [])]
        summary["placeholders"].append({
            "id": g["id"],
            "description": g["description"],
            "public": g["public"],
            "created": g["created_at"],
            "updated": g["updated_at"],
            "files": file_names,
        })

    for g in non_gtt:
        file_names = [f["name"] for f in g.get("files", [])]
        summary["non_gtt"].append({
            "id": g["id"],
            "description": g["description"],
            "public": g["public"],
            "files": file_names,
        })

    summary_file = backup_dir / "gist_inventory.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'=' * 60}")
    print(f"Backup complete!")
    print(f"  Backup dir:    {backup_dir}")
    print(f"  Files saved:   {len(placeholders)} gist backups + 1 inventory")
    print(f"\nInventory:")
    print(f"  Active GTT:    {len(active_gtt)}")
    for g in active_gtt:
        vis = "public" if g["public"] else "unlisted"
        print(f"    {g['id']}  ({vis})  {g['description']}")
    print(f"  Placeholders:  {len(placeholders)}")
    print(f"  Non-GTT:       {len(non_gtt)}")
    for g in non_gtt:
        print(f"    {g['id']}  {g['description'][:60]}")

    print(f"\nSummary saved to: {summary_file}")


if __name__ == "__main__":
    main()
