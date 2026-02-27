"""
Merge a gold .claude.json backup with a fresh-login .claude.json.

Context: During oracle skill/agent creation (2026-02-26), .claude.json
entered a corruption cascade (truncated from 58→11 keys). After restoring
from gold backup, a relogin overwrote it with a fresh 33-key config.
This script merges gold (history, projects, stats) with fresh (auth tokens,
feature flags, caches).

Usage:
    python merge_claude_json.py                    # Uses default paths
    python merge_claude_json.py --gold <path> --fresh <path> --output <path>
    python merge_claude_json.py --dry-run          # Show what would change
"""

import json
import os
import sys
from pathlib import Path

HOME = Path(os.environ.get("USERPROFILE", os.environ.get("HOME")))
SAFE_COPIES = HOME / ".claude" / "backups" / "manual-safe-copies"

# Default paths
DEFAULT_GOLD = SAFE_COPIES / ".claude.json.GOLD.1772136821429"
DEFAULT_FRESH = HOME / ".claude.json"
DEFAULT_OUTPUT = HOME / ".claude.json"

# Keys to overlay from fresh login (auth, caches, feature flags)
OVERLAY_KEYS = [
    "oauthAccount",
    "userID",
    "cachedGrowthBookFeatures",
    "changelogLastFetched",
    "clientDataCache",
    "groveConfigCache",
    "lastOnboardingVersion",
    "passesEligibilityCache",
    "s1mAccessCache",
]


def merge(gold_path: Path, fresh_path: Path, dry_run: bool = False) -> dict:
    """Merge gold base with fresh auth overlay."""
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    fresh = json.loads(fresh_path.read_text(encoding="utf-8"))

    print(f"Gold:  {gold_path} ({gold_path.stat().st_size:,} bytes, {len(gold)} keys, "
          f"{len(gold.get('projects', {}))} projects)")
    print(f"Fresh: {fresh_path} ({fresh_path.stat().st_size:,} bytes, {len(fresh)} keys, "
          f"{len(fresh.get('projects', {}))} projects)")
    print()

    # Start with gold (full history)
    merged = dict(gold)

    # Overlay auth/cache keys from fresh
    print("=== Overlaid from fresh ===")
    for k in OVERLAY_KEYS:
        if k in fresh:
            old_val = str(gold.get(k, "<missing>"))[:60]
            new_val = str(fresh[k])[:60]
            changed = gold.get(k) != fresh.get(k)
            marker = "CHANGED" if changed else "same"
            print(f"  {k}: {marker}")
            if not dry_run:
                merged[k] = fresh[k]

    # Add new keys from fresh that don't exist in gold
    print()
    print("=== New keys from fresh ===")
    new_keys = [k for k in fresh if k not in gold]
    if new_keys:
        for k in new_keys:
            print(f"  {k}: {type(fresh[k]).__name__} = {str(fresh[k])[:80]}")
            if not dry_run:
                merged[k] = fresh[k]
    else:
        print("  (none)")

    # Merge projects — gold base + any new from fresh
    if not dry_run:
        merged["projects"] = dict(gold["projects"])
    new_projects = []
    for pk, pv in fresh.get("projects", {}).items():
        if pk not in gold.get("projects", {}):
            new_projects.append(pk)
            if not dry_run:
                merged["projects"][pk] = pv

    if new_projects:
        print()
        print("=== New projects from fresh ===")
        for pk in new_projects:
            print(f"  {pk}")

    # Summary
    print()
    print("=== Result ===")
    print(f"  Keys: {len(merged)}")
    print(f"  Projects: {len(merged.get('projects', {}))}")
    print(f"  numStartups: {merged.get('numStartups', '?')}")
    print(f"  firstStartTime: {merged.get('firstStartTime', '?')}")
    print(f"  has oauthAccount: {'oauthAccount' in merged}")
    print(f"  skillUsage entries: {len(merged.get('skillUsage', {}))}")
    print(f"  toolUsage entries: {len(merged.get('toolUsage', {}))}")

    return merged


def validate(merged: dict, gold: dict):
    """Validate merged result against gold baseline."""
    errors = []

    if len(merged.get("projects", {})) < len(gold.get("projects", {})):
        errors.append(f"Projects lost: {len(merged['projects'])} < {len(gold['projects'])}")

    if merged.get("numStartups", 0) < gold.get("numStartups", 0):
        errors.append(f"numStartups decreased: {merged['numStartups']} < {gold['numStartups']}")

    if merged.get("firstStartTime") != gold.get("firstStartTime"):
        errors.append(f"firstStartTime changed: {merged['firstStartTime']} != {gold['firstStartTime']}")

    if len(merged.get("tipsHistory", {})) < len(gold.get("tipsHistory", {})):
        errors.append(f"tipsHistory shrunk: {len(merged['tipsHistory'])} < {len(gold['tipsHistory'])}")

    if "oauthAccount" not in merged:
        errors.append("Missing oauthAccount (auth will fail)")

    return errors


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Merge gold .claude.json with fresh login")
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD, help="Gold backup path")
    parser.add_argument("--fresh", type=Path, default=DEFAULT_FRESH, help="Fresh login path")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output path")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    args = parser.parse_args()

    if not args.gold.exists():
        print(f"ERROR: Gold file not found: {args.gold}")
        sys.exit(1)
    if not args.fresh.exists():
        print(f"ERROR: Fresh file not found: {args.fresh}")
        sys.exit(1)

    merged = merge(args.gold, args.fresh, dry_run=args.dry_run)

    if args.dry_run:
        print("\n[DRY RUN — no files written]")
        return

    # Validate
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    errors = validate(merged, gold)
    if errors:
        print("\n=== VALIDATION ERRORS ===")
        for e in errors:
            print(f"  ERROR: {e}")
        print("\nAborting write. Fix errors or use --force.")
        sys.exit(1)
    else:
        print("\nAll validations passed.")

    # Write
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    print(f"Wrote: {args.output} ({args.output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
