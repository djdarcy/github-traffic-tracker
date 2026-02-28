#!/usr/bin/env python3
"""
Synchronize version numbers across all project files.

Single source of truth: version.py (MAJOR, MINOR, PATCH, PHASE).
This script reads those components and propagates to:
- version.py __version__ string (git metadata: branch, build, date, hash)
- src/ghtraf/_version.py (components + __version__ string)
- packages/ghtraf-alias/pyproject.toml (PEP 440 version + dependency pin)

Replaces the need for a separate update-version.sh — all version logic
lives here. Git hooks call this with --auto.

Usage:
    python scripts/sync-versions.py [OPTIONS]

Options:
    --check         Only check if versions are in sync (don't modify)
    --bump PART     Bump version before syncing (major, minor, patch)
    --demote PART   Demote version before syncing (major, minor, patch)
    --set X.Y.Z     Set version directly (e.g., --set 0.3.0)
    --phase PHASE   Set release phase (alpha, beta, rc1) or 'none' to clear
    --dry-run       Show what would change without modifying files
    --auto          Git hook mode (quiet, stages files, uses today's date)
    --no-git-ver    Skip __version__ string update (components only)
    --verbose       Show detailed output

Examples:
    # Check sync status
    python scripts/sync-versions.py --check

    # Bump patch version and sync everything
    python scripts/sync-versions.py --bump patch

    # Just sync (no version change) — useful after manual edits
    python scripts/sync-versions.py

    # Git hook mode (called by pre-commit)
    python scripts/sync-versions.py --auto
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path


# Files relative to project root
VERSION_SOURCE = "version.py"
VERSION_TARGETS = {
    "package": "src/ghtraf/_version.py",
    "alias": "packages/ghtraf-alias/pyproject.toml",
}

# Both of these files get __version__ strings with git metadata
VERSION_STRING_FILES = [
    VERSION_SOURCE,
    "src/ghtraf/_version.py",
]

# PEP 440 phase mapping
PEP440_PHASE_MAP = {
    "alpha": "a0",
    "beta": "b0",
    "rc1": "rc1",
    "rc2": "rc2",
}


# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------

def find_project_root() -> Path:
    """Find project root by looking for version.py."""
    if Path(VERSION_SOURCE).exists():
        return Path.cwd()
    parent = Path.cwd().parent
    if (parent / VERSION_SOURCE).exists():
        return parent
    raise FileNotFoundError(f"Cannot find {VERSION_SOURCE}. Run from project root.")


# ---------------------------------------------------------------------------
# Version component read/write
# ---------------------------------------------------------------------------

def read_version_components(file_path: Path) -> tuple[int, int, int, str | None]:
    """Read MAJOR, MINOR, PATCH, PHASE from a version.py file."""
    content = file_path.read_text(encoding="utf-8")

    major = re.search(r"^MAJOR\s*=\s*(\d+)", content, re.MULTILINE)
    minor = re.search(r"^MINOR\s*=\s*(\d+)", content, re.MULTILINE)
    patch = re.search(r"^PATCH\s*=\s*(\d+)", content, re.MULTILINE)

    if not all([major, minor, patch]):
        raise ValueError(f"Could not parse MAJOR, MINOR, PATCH from {file_path}")

    phase_match = re.search(r"^PHASE\s*=\s*(.+)$", content, re.MULTILINE)
    phase = None
    if phase_match:
        phase_value = phase_match.group(1).strip()
        if phase_value in ("None", "none", "null", '""', "''"):
            phase = None
        else:
            phase_value = re.sub(r"#.*$", "", phase_value).strip()
            phase_value = phase_value.strip("\"'")
            if phase_value and phase_value.lower() not in ("none", "null"):
                phase = phase_value

    return int(major.group(1)), int(minor.group(1)), int(patch.group(1)), phase


def write_version_components(
    file_path: Path,
    major: int,
    minor: int,
    patch: int,
    phase: str | None = None,
    update_phase: bool = False,
    dry_run: bool = False,
) -> bool:
    """Update MAJOR, MINOR, PATCH, and optionally PHASE in a version file."""
    content = file_path.read_text(encoding="utf-8")
    original = content

    content = re.sub(
        r"^(MAJOR\s*=\s*)\d+", f"\\g<1>{major}", content, flags=re.MULTILINE
    )
    content = re.sub(
        r"^(MINOR\s*=\s*)\d+", f"\\g<1>{minor}", content, flags=re.MULTILINE
    )
    content = re.sub(
        r"^(PATCH\s*=\s*)\d+", f"\\g<1>{patch}", content, flags=re.MULTILINE
    )

    if update_phase:
        phase_str = f'"{phase}"' if phase else "None"
        content = re.sub(
            r"^(PHASE\s*=\s*).*$", f"\\g<1>{phase_str}", content, flags=re.MULTILINE
        )

    if content != original:
        if not dry_run:
            file_path.write_text(content, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------------------
# __version__ string (git metadata)
# ---------------------------------------------------------------------------

def get_git_info(root: Path, auto_mode: bool = False) -> dict:
    """Gather git metadata for the __version__ string.

    Returns dict with keys: branch, build_count, date, commit_hash.
    """
    info = {
        "branch": "unknown",
        "build_count": "0",
        "date": datetime.date.today().strftime("%Y%m%d"),
        "commit_hash": "unknown",
    }

    try:
        # Check if we're in a git repo
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(root), capture_output=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return info

    # Branch
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(root), capture_output=True, text=True, check=True,
        )
        branch = result.stdout.strip()
        if branch:
            info["branch"] = branch.replace("/", "-")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Build count
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=str(root), capture_output=True, text=True, check=True,
        )
        count = int(result.stdout.strip())
        if auto_mode:
            count += 1  # pre-commit: about to create a new commit
        info["build_count"] = str(count)
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        pass

    # Commit hash
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=str(root), capture_output=True, text=True, check=True,
        )
        info["commit_hash"] = result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Date — in auto mode use today, otherwise use smart default
    if not auto_mode:
        try:
            # Check if only version files are modified
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(root), capture_output=True, text=True, check=True,
            )
            modified = result.stdout.strip()

            if modified:
                # Filter out version files
                other_changes = [
                    line for line in modified.split("\n")
                    if "_version.py" not in line and "version.py" not in line
                ]
                if not other_changes:
                    # Only version files changed — use last commit date
                    result = subprocess.run(
                        ["git", "log", "-1", "--format=%cd", "--date=format:%Y%m%d"],
                        cwd=str(root), capture_output=True, text=True, check=True,
                    )
                    info["date"] = result.stdout.strip()
                # else: other files changed, keep today's date
            else:
                # Clean working dir — use last commit date
                result = subprocess.run(
                    ["git", "log", "-1", "--format=%cd", "--date=format:%Y%m%d"],
                    cwd=str(root), capture_output=True, text=True, check=True,
                )
                info["date"] = result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    return info


def build_version_string(
    major: int,
    minor: int,
    patch: int,
    phase: str | None,
    git_info: dict,
) -> str:
    """Build the full __version__ string.

    Format: MAJOR.MINOR.PATCH[-PHASE]_BRANCH_BUILD-YYYYMMDD-HASH
    Example: 0.2.8-alpha_main_12-20260228-4691eea
    """
    base = f"{major}.{minor}.{patch}"
    if phase:
        base = f"{base}-{phase}"

    return (
        f"{base}_{git_info['branch']}_{git_info['build_count']}"
        f"-{git_info['date']}-{git_info['commit_hash']}"
    )


def read_version_string(file_path: Path) -> str | None:
    """Read the current __version__ value from a file."""
    content = file_path.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    return match.group(1) if match else None


def write_version_string(
    file_path: Path, new_version: str, dry_run: bool = False
) -> bool:
    """Update the __version__ string in a file."""
    content = file_path.read_text(encoding="utf-8")
    original = content

    content = re.sub(
        r'(__version__\s*=\s*")[^"]+(")',
        f"\\g<1>{new_version}\\g<2>",
        content,
    )

    if content != original:
        if not dry_run:
            file_path.write_text(content, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------------------
# PEP 440 + alias toml
# ---------------------------------------------------------------------------

def to_pep440(major: int, minor: int, patch: int, phase: str | None = None) -> str:
    """Convert version components to PEP 440 string.

    Examples:
        (0, 2, 8, "alpha") -> "0.2.8a0"
        (1, 0, 0, None)    -> "1.0.0"
    """
    base = f"{major}.{minor}.{patch}"
    if phase:
        suffix = PEP440_PHASE_MAP.get(phase, phase)
        base += suffix
    return base


def update_alias_toml(
    file_path: Path, pip_version: str, dry_run: bool = False
) -> bool:
    """Update version and dependency pin in the alias package pyproject.toml."""
    content = file_path.read_text(encoding="utf-8")
    original = content

    content = re.sub(
        r'^(version\s*=\s*")[^"]+(")',
        f"\\g<1>{pip_version}\\g<2>",
        content,
        flags=re.MULTILINE,
    )

    content = re.sub(
        r'(github-traffic-tracker==)[^"]+',
        f"\\g<1>{pip_version}",
        content,
    )

    if content != original:
        if not dry_run:
            file_path.write_text(content, encoding="utf-8")
        return True
    return False


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_version_string(
    major: int, minor: int, patch: int, phase: str | None = None
) -> str:
    """Format as human-readable string (e.g., 0.2.8-alpha)."""
    base = f"{major}.{minor}.{patch}"
    if phase:
        return f"{base}-{phase}"
    return base


def bump_version(
    major: int, minor: int, patch: int, part: str
) -> tuple[int, int, int]:
    """Bump the specified version part."""
    if part == "major":
        return major + 1, 0, 0
    elif part == "minor":
        return major, minor + 1, 0
    elif part == "patch":
        return major, minor, patch + 1
    raise ValueError(f"Unknown version part: {part}")


def demote_version(
    major: int, minor: int, patch: int, part: str
) -> tuple[int, int, int]:
    """Demote the specified version part."""
    if part == "major" and major > 0:
        return major - 1, 0, 0
    elif part == "minor" and minor > 0:
        return major, minor - 1, 0
    elif part == "patch" and patch > 0:
        return major, minor, patch - 1
    raise ValueError(
        f"Cannot demote {part} below 0 (current: {major}.{minor}.{patch})"
    )


def parse_version_string(version_str: str) -> tuple[int, int, int]:
    """Parse 'X.Y.Z' into (major, minor, patch)."""
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version_str.strip())
    if not match:
        raise ValueError(
            f"Invalid version format: '{version_str}'. Expected X.Y.Z (e.g., 0.3.0)"
        )
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def check_changelog(root: Path, version: str) -> bool:
    """Check if CHANGELOG.md has an entry for this version."""
    changelog = root / "CHANGELOG.md"
    if not changelog.exists():
        return False
    content = changelog.read_text(encoding="utf-8")
    pattern = rf"##\s*\[{re.escape(version)}\]"
    return bool(re.search(pattern, content))


def git_stage(root: Path, *files: str) -> None:
    """Stage files for commit."""
    try:
        subprocess.run(
            ["git", "add"] + list(files),
            cwd=str(root), capture_output=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sync versions across GitHub Traffic Tracker project files"
    )
    parser.add_argument(
        "--check", action="store_true", help="Only check, don't modify"
    )
    parser.add_argument(
        "--bump", choices=["major", "minor", "patch"], help="Bump version part"
    )
    parser.add_argument(
        "--demote", choices=["major", "minor", "patch"], help="Demote version part"
    )
    parser.add_argument("--set", metavar="X.Y.Z", help="Set version directly")
    parser.add_argument(
        "--phase", metavar="PHASE",
        help="Set release phase (alpha, beta, rc1) or 'none' to clear",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show changes without modifying"
    )
    parser.add_argument(
        "--auto", action="store_true",
        help="Git hook mode (quiet, stages files, uses today's date)",
    )
    parser.add_argument(
        "--no-git-ver", action="store_true",
        help="Skip __version__ string update (components only)",
    )
    parser.add_argument(
        "--force", "-f", action="store_true", help="Skip confirmation prompts"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )
    args = parser.parse_args()

    quiet = args.auto

    try:
        root = find_project_root()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Read current version from source of truth
    major, minor, patch, phase = read_version_components(root / VERSION_SOURCE)
    current_version = format_version_string(major, minor, patch, phase)
    update_phase = False

    # Handle --phase
    if args.phase:
        update_phase = True
        if args.phase.lower() in ("none", "null", "stable", "release", ""):
            phase = None
        else:
            phase = args.phase

    if args.verbose:
        print(f"Project root: {root}")
        print(f"Source: {VERSION_SOURCE}")
        if phase:
            print(f"Phase: {phase}")

    # Handle --set, --bump, or --demote (mutually exclusive)
    version_ops = [args.set, args.bump, args.demote]
    if sum(1 for op in version_ops if op) > 1:
        print("Error: Cannot use --set, --bump, and --demote together", file=sys.stderr)
        return 1

    if args.set:
        try:
            new_major, new_minor, new_patch = parse_version_string(args.set)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        new_version = format_version_string(new_major, new_minor, new_patch, phase)

        if new_major != major and not args.force and not args.dry_run and not args.check:
            print(f"\n  WARNING: Major version change: {current_version} -> {new_version}")
            try:
                confirm = input("\n  Type 'yes' to confirm: ")
                if confirm.lower() != "yes":
                    print("  Aborted.")
                    return 1
            except (EOFError, KeyboardInterrupt):
                print("\n  Aborted.")
                return 1

        if not quiet:
            print(f"Setting version: {current_version} -> {new_version}")

        if not args.check and not args.dry_run:
            write_version_components(
                root / VERSION_SOURCE, new_major, new_minor, new_patch, phase, update_phase
            )

        major, minor, patch = new_major, new_minor, new_patch
        current_version = new_version

    elif args.bump:
        new_major, new_minor, new_patch = bump_version(major, minor, patch, args.bump)
        new_version = format_version_string(new_major, new_minor, new_patch, phase)

        if args.bump == "major" and not args.force and not args.dry_run and not args.check:
            print(f"\n  WARNING: Major version bump: {current_version} -> {new_version}")
            try:
                confirm = input("\n  Type 'yes' to confirm: ")
                if confirm.lower() != "yes":
                    print("  Aborted.")
                    return 1
            except (EOFError, KeyboardInterrupt):
                print("\n  Aborted.")
                return 1

        if not quiet:
            print(f"Bumping {args.bump}: {current_version} -> {new_version}")

        if not args.check and not args.dry_run:
            write_version_components(
                root / VERSION_SOURCE, new_major, new_minor, new_patch, phase, update_phase
            )

        major, minor, patch = new_major, new_minor, new_patch
        current_version = new_version

    elif args.demote:
        try:
            new_major, new_minor, new_patch = demote_version(major, minor, patch, args.demote)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        new_version = format_version_string(new_major, new_minor, new_patch, phase)
        if not quiet:
            print(f"Demoting {args.demote}: {current_version} -> {new_version}")

        if not args.check and not args.dry_run:
            write_version_components(
                root / VERSION_SOURCE, new_major, new_minor, new_patch, phase, update_phase
            )

        major, minor, patch = new_major, new_minor, new_patch
        current_version = new_version

    elif update_phase:
        new_version = format_version_string(major, minor, patch, phase)
        if not quiet:
            print(f"Setting phase: {current_version} -> {new_version}")

        if not args.check and not args.dry_run:
            write_version_components(
                root / VERSION_SOURCE, major, minor, patch, phase, update_phase
            )

        current_version = new_version

    pip_version = to_pep440(major, minor, patch, phase)

    if not quiet:
        print(f"Version: {current_version}  (PEP 440: {pip_version})")

    # Track status
    all_synced = True
    files_updated = []

    # --- Sync __version__ strings with git metadata ---
    if not args.no_git_ver:
        git_info = get_git_info(root, auto_mode=args.auto)
        new_ver_string = build_version_string(major, minor, patch, phase, git_info)

        for ver_file in VERSION_STRING_FILES:
            ver_path = root / ver_file
            if not ver_path.exists():
                if args.verbose:
                    print(f"  [--] {ver_file}: not found (skipped)")
                continue

            current_str = read_version_string(ver_path)
            if current_str != new_ver_string:
                all_synced = False
                if args.check:
                    print(f"  [X] {ver_file}: __version__ out of date")
                    if args.verbose:
                        print(f"       current: {current_str}")
                        print(f"       expected: {new_ver_string}")
                else:
                    updated = write_version_string(ver_path, new_ver_string, args.dry_run)
                    if updated:
                        action = "would update" if args.dry_run else "updated"
                        if not quiet:
                            print(f"  [OK] {ver_file}: __version__ {action}")
                        files_updated.append(ver_file)
            else:
                if args.verbose:
                    print(f"  [OK] {ver_file}: __version__ in sync")

    # --- Sync components to src/ghtraf/_version.py ---
    pkg_path = root / VERSION_TARGETS["package"]
    if pkg_path.exists():
        pkg_major, pkg_minor, pkg_patch, _ = read_version_components(pkg_path)

        needs_update = (
            pkg_major != major or pkg_minor != minor or pkg_patch != patch
        )

        if needs_update:
            all_synced = False
            if args.check:
                print(
                    f"  [X] {VERSION_TARGETS['package']}: "
                    f"{pkg_major}.{pkg_minor}.{pkg_patch} "
                    f"(expected {major}.{minor}.{patch})"
                )
            else:
                updated = write_version_components(
                    pkg_path, major, minor, patch, phase, update_phase, args.dry_run
                )
                if updated:
                    action = "would update" if args.dry_run else "updated"
                    if not quiet:
                        print(f"  [OK] {VERSION_TARGETS['package']}: components {action}")
                    if VERSION_TARGETS["package"] not in files_updated:
                        files_updated.append(VERSION_TARGETS["package"])
        else:
            if args.verbose:
                print(f"  [OK] {VERSION_TARGETS['package']}: components in sync")
    else:
        if args.verbose:
            print(f"  Warning: {VERSION_TARGETS['package']} not found")

    # --- Sync alias package pyproject.toml ---
    alias_path = root / VERSION_TARGETS["alias"]
    if alias_path.exists():
        alias_content = alias_path.read_text(encoding="utf-8")

        ver_match = re.search(r'^version\s*=\s*"([^"]+)"', alias_content, re.MULTILINE)
        dep_match = re.search(r"github-traffic-tracker==([^\"]+)", alias_content)

        current_alias_ver = ver_match.group(1) if ver_match else "???"
        current_dep_ver = dep_match.group(1) if dep_match else "???"

        needs_update = current_alias_ver != pip_version or current_dep_ver != pip_version

        if needs_update:
            all_synced = False
            if args.check:
                print(
                    f"  [X] {VERSION_TARGETS['alias']}: "
                    f"version={current_alias_ver}, dep={current_dep_ver} "
                    f"(expected {pip_version})"
                )
            else:
                updated = update_alias_toml(alias_path, pip_version, args.dry_run)
                if updated:
                    action = "would update" if args.dry_run else "updated"
                    if not quiet:
                        print(
                            f"  [OK] {VERSION_TARGETS['alias']}: {action} "
                            f"(version + dep -> {pip_version})"
                        )
                    files_updated.append(VERSION_TARGETS["alias"])
        else:
            if args.verbose:
                print(f"  [OK] {VERSION_TARGETS['alias']}: in sync ({pip_version})")
    else:
        if args.verbose:
            print(f"  [--] {VERSION_TARGETS['alias']}: not found (skipped)")

    # Stage files in auto mode
    if args.auto and files_updated and not args.dry_run:
        git_stage(root, *files_updated)

    # Check CHANGELOG (not in auto/quiet mode)
    if not quiet and not check_changelog(root, current_version):
        print(f"\n  Note: No CHANGELOG.md entry found for [{current_version}]")

    # Summary
    if args.check:
        if all_synced:
            if not quiet:
                print("\nAll versions are in sync.")
            return 0
        else:
            if not quiet:
                print("\nVersions are out of sync. Run without --check to fix.")
            return 1
    elif files_updated:
        if not quiet:
            if args.dry_run:
                print(f"\nDry run: would update {len(files_updated)} file(s)")
            else:
                print(f"\nUpdated {len(files_updated)} file(s)")
    else:
        if not quiet:
            print("\nAll versions already in sync.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
