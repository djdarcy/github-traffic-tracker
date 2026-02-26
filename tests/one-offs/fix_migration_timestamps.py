#!/usr/bin/env python3
"""
Fix timestamps on files migrated from source projects to GTT.

Uses os.utime() to set modified/accessed times on destination files
to match source files, following the pattern from preserve/preservelib/metadata.py.

Usage:
    python tests/one-offs/fix_migration_timestamps.py [--dry-run]
"""

import os
import sys
import datetime
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv

GTT = Path(r"C:\code\github-traffic-tracker\local")
TRITON = Path(r"C:\code\comfyui-triton-sageattention-installer\local")
NCSI = Path(r"C:\code\Windows-No-Internet-Secured-BUGFIX")

# Map: (source_base, source_relative) -> dest_relative
# Tier 1: Foundational docs
TIER1_TRITON = [
    "private/claude/2026-02-24__13-20-41__clone-download-badge-analysis.md",
    "private/claude/2026-02-24__16-02-18__context-postmortem_triton-badges-dashboard-setup.md",
    "private/claude/2026-02-24__16-54-32__full-postmortem_v0.8.1-badges-dashboard-enhanced-stats-plan.md",
    "private/claude/2026-02-25__19-26-05__stats-migration-and-standalone-extraction.md",
    "private/claude/2026-02-25__23-09-16__full-postmortem_stats-migration-phase1.md",
]

TIER1_NCSI = [
    "private/claude/2026-02-24__14-41-49__full-postmortem_traffic-badges-and-version-consolidation.md",
    "private/claude/2026-02-25__02-55-42__full-postmortem_v0.7.8-tabbed-dashboard-port-and-ci-clone-inflation.md",
    "private/claude/2026-02-25__03-08-58__ci-clone-subtraction-precision-analysis.md",
    "private/claude/2026-02-25__12-30-18__full-postmortem_v0.7.9-traffic-workflow-fixes.md",
    "private/claude/2026-02-25__14-08-29__full-postmortem_v0.7.9-organic-clones-and-dashboard-accuracy.md",
    "private/claude/2026-02-25__15-06-13__projection-fix-dev-tab-referrer-chart.md",
    "private/claude/2026-02-25__15-29-09__dev-audit-tab-implementation.md",
    "private/claude/2026-02-25__15-52-18__full-postmortem_v0.7.10-projection-and-data-expansion.md",
    "private/claude/2026-02-25__16-37-53__full-postmortem_v0.7.10-phase2-dashboard-enhancements.md",
    "private/claude/2026-02-25__17-23-23__full-postmortem_v0.7.11-phase3-dev-tab.md",
]

# Tier 2: Notes & Ideas
TIER2_NOTES = [
    # (source_base, source_rel, dest_rel)
    (NCSI, "private/claude/notes/ideas/2026-02-24__14-24-35__both_cascading-recency-badge.md",
           "private/claude/notes/ideas/2026-02-24__14-24-35__both_cascading-recency-badge.md"),
    (NCSI, "private/claude/notes/ideas/2026-02-24__15-29-38__both_interactive-dashboard-cards.md",
           "private/claude/notes/ideas/2026-02-24__15-29-38__both_interactive-dashboard-cards.md"),
    (TRITON, "private/claude/notes/2026-02-25__22-08-39__both_feb24-clone-anomaly.md",
             "private/claude/notes/2026-02-25__22-08-39__both_feb24-clone-anomaly.md"),
    (TRITON, "private/claude/notes/2026-02-26__02-26-32__both_github-api-middot-encoding.md",
             "private/claude/notes/2026-02-26__02-26-32__both_github-api-middot-encoding.md"),
]

# Tier 3: Commit records (source_base, source_filename, dest_filename)
TIER3_TRITON_COMMITS = [
    ("commit_fix-false-zeros-stars-badge.txt", "triton_commit_fix-false-zeros-stars-badge.txt"),
    ("commit_v0.8.1_badges-dashboard-issue27.txt", "triton_commit_v0.8.1_badges-dashboard-issue27.txt"),
    ("commit_v0.8.2_tabbed-dashboard.txt", "triton_commit_v0.8.2_tabbed-dashboard.txt"),
    ("commit_v0.8.3_organic-unique-clones.txt", "triton_commit_v0.8.3_organic-unique-clones.txt"),
]

TIER3_NCSI_COMMITS = [
    ("commit_fix-data-quality.txt", "ncsi_commit_fix-data-quality.txt"),
    ("commit_traffic-badges.txt", "ncsi_commit_traffic-badges.txt"),
    ("commit_v0.7.10_phase2-dashboard.txt", "ncsi_commit_v0.7.10_phase2-dashboard.txt"),
    ("commit_v0.7.10_projection-fix.txt", "ncsi_commit_v0.7.10_projection-fix.txt"),
    ("commit_v0.7.10_unique-tracking.txt", "ncsi_commit_v0.7.10_unique-tracking.txt"),
    ("commit_v0.7.11_loading-indicators.txt", "ncsi_commit_v0.7.11_loading-indicators.txt"),
    ("commit_v0.7.11_phase3-dev-tab.txt", "ncsi_commit_v0.7.11_phase3-dev-tab.txt"),
    ("commit_v0.7.6_cascading-recency.txt", "ncsi_commit_v0.7.6_cascading-recency.txt"),
    ("commit_v0.7.7_stats-dashboard.txt", "ncsi_commit_v0.7.7_stats-dashboard.txt"),
    ("commit_v0.7.8_tabbed-dashboard.txt", "ncsi_commit_v0.7.8_tabbed-dashboard.txt"),
    ("commit_v0.7.9_organic-badges.txt", "ncsi_commit_v0.7.9_organic-badges.txt"),
    ("commit_v0.7.9_traffic-fixes.txt", "ncsi_commit_v0.7.9_traffic-fixes.txt"),
]

# Tier 4: Screenshots
TIER4_SCREENSHOTS = [
    "2026-02-24__16-18-XX__banner-h1-text-to-link-back-to-project.jpg",
    "2026-02-24__17-11-XX__dashboard-Feb24-repeated-twice.jpg",
    "2026-02-26__01-34-xx__new-unique-clones-adjusted-from-raw-unique-clones-prediction-issue.jpg",
    "2026-02-26__01-34-xx__new-unique-clones-adjusted-from-raw-unique-clones-prediction-issue2.jpg",
    "2026-02-26__03-51-xx__test_dashboard_data__installs-all-history.jpg",
    "2026-02-26__03-51-xx__test_dashboard_data__overview-tab.jpg",
]

# Tier 5: One-off scripts
TIER5_TRITON_ONEOFFS = [
    "backfill_ciruns.py",
    "backfill_organic_unique.py",
    "test_merge_logic.py",
    "_pre_backfill_state.json",
    "_backfill_preview.json",
    "_pre_star_fix_state.json",
]

TIER5_NCSI_ONEOFFS = [
    "backfill_unique_counts.py",
    "fix_false_organic_zeros.py",
    "verify_dashboard_ids.py",
    "verify_week_alignment.py",
]

# Tier 6: Reference data
TIER6_REFDATA = [
    (NCSI, "private/claude/ncsi_state_raw.json", "private/claude/reference-data/ncsi_state_raw.json"),
    (NCSI, "private/claude/ncsi_state_with_cumulative_ci.json", "private/claude/reference-data/ncsi_state_with_cumulative_ci.json"),
    (NCSI, "private/claude/triton_state_raw.json", "private/claude/reference-data/triton_state_raw.json"),
    (TRITON, "private/claude/current_gist_state.json", "private/claude/reference-data/triton_current_gist_state.json"),
    (TRITON, "private/claude/backfill_state.json", "private/claude/reference-data/triton_backfill_state.json"),
    (NCSI, "private/claude/backups/gist_payload_unique_seeding.json", "private/claude/reference-data/ncsi_gist_payload_unique_seeding.json"),
]


def fix_timestamp(src_path, dst_path):
    """Copy mtime and atime from source to destination using os.utime()."""
    if not src_path.exists():
        print(f"  SKIP (src missing): {src_path}")
        return False
    if not dst_path.exists():
        print(f"  SKIP (dst missing): {dst_path}")
        return False

    src_stat = src_path.stat()
    dst_stat = dst_path.stat()

    src_mtime = datetime.datetime.fromtimestamp(src_stat.st_mtime)
    dst_mtime = datetime.datetime.fromtimestamp(dst_stat.st_mtime)

    if DRY_RUN:
        print(f"  DRY-RUN: {dst_path.name}")
        print(f"    src mtime: {src_mtime.isoformat()}")
        print(f"    dst mtime: {dst_mtime.isoformat()} -> would set to src")
        return True

    os.utime(dst_path, (src_stat.st_atime, src_stat.st_mtime))
    print(f"  OK: {dst_path.name}  ({dst_mtime.strftime('%H:%M')} -> {src_mtime.strftime('%m/%d %H:%M')})")
    return True


def main():
    mode = "DRY-RUN" if DRY_RUN else "LIVE"
    print(f"=== Fix Migration Timestamps ({mode}) ===\n")

    count = 0

    # Tier 1: Foundational docs (same relative path)
    print("Tier 1: Foundational documents")
    for rel in TIER1_TRITON:
        if fix_timestamp(TRITON / rel, GTT / rel):
            count += 1
    for rel in TIER1_NCSI:
        if fix_timestamp(NCSI / rel, GTT / rel):
            count += 1

    # Tier 2: Notes
    print("\nTier 2: Notes & Ideas")
    for src_base, src_rel, dst_rel in TIER2_NOTES:
        if fix_timestamp(src_base / src_rel, GTT / dst_rel):
            count += 1

    # Tier 3: Commits
    print("\nTier 3: Commit records")
    for src_name, dst_name in TIER3_TRITON_COMMITS:
        src = TRITON / "private/claude/commits" / src_name
        dst = GTT / "private/claude/commits" / dst_name
        if fix_timestamp(src, dst):
            count += 1
    for src_name, dst_name in TIER3_NCSI_COMMITS:
        src = NCSI / "private/claude/commits" / src_name
        dst = GTT / "private/claude/commits" / dst_name
        if fix_timestamp(src, dst):
            count += 1

    # Tier 4: Screenshots
    print("\nTier 4: Screenshots")
    for fname in TIER4_SCREENSHOTS:
        src = TRITON / "private/claude" / fname
        dst = GTT / "private/claude" / fname
        if fix_timestamp(src, dst):
            count += 1

    # Tier 5: One-off scripts
    print("\nTier 5: One-off scripts & fixtures")
    for fname in TIER5_TRITON_ONEOFFS:
        src = TRITON / "tests/one-offs" / fname
        dst = GTT / "tests/one-offs" / fname
        if fix_timestamp(src, dst):
            count += 1
    for fname in TIER5_NCSI_ONEOFFS:
        src = NCSI / "tests/one-offs" / fname
        dst = GTT / "tests/one-offs" / fname
        if fix_timestamp(src, dst):
            count += 1

    # Tier 6: Reference data
    print("\nTier 6: Reference data")
    for src_base, src_rel, dst_rel in TIER6_REFDATA:
        if fix_timestamp(src_base / src_rel, GTT / dst_rel):
            count += 1

    print(f"\n=== Done: {count} files updated ===")


if __name__ == "__main__":
    main()
