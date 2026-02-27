#!/usr/bin/env python3
"""
Set up GitHub traffic tracking gists for your repository.

Creates the public badge gist and unlisted archive gist needed by the
traffic-badges.yml workflow, then optionally configures repository
variables/secrets and updates dashboard files with your values.

Usage:
    python setup-gists.py                                    # interactive
    python setup-gists.py --owner myorg --repo myproject     # partial CLI
    python setup-gists.py --owner myorg --repo myproject \\
        --created 2025-01-15 --display-name "My Project" --configure # full CLI
    python setup-gists.py --dry-run                          # preview only

Requires: Python 3.10+, gh CLI (https://cli.github.com)

If ghtraf is installed (pip install github-traffic-tracker), this script
delegates to `ghtraf create`. Otherwise it runs standalone.
"""

# Try to delegate to the ghtraf package if installed
try:
    from ghtraf.cli import main as _ghtraf_main
    import sys

    def _delegate():
        """Delegate to ghtraf create with the same arguments."""
        sys.exit(_ghtraf_main(["create"] + sys.argv[1:]))

    if __name__ == "__main__":
        _delegate()
        # If we get here, _delegate raised or returned
except ImportError:
    pass  # ghtraf not installed — run standalone below

import argparse
import html as html_module
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths (relative to project root)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent

DASHBOARD_PATH = PROJECT_ROOT / "docs" / "stats" / "index.html"
DASHBOARD_README_PATH = PROJECT_ROOT / "docs" / "stats" / "README.md"
WORKFLOW_PATH = PROJECT_ROOT / ".github" / "workflows" / "traffic-badges.yml"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def run_gh(args, input_data=None):
    """Run a gh CLI command, return stdout. Raises SystemExit on failure."""
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True, text=True,
        input=input_data
    )
    if result.returncode != 0:
        print(f"  ERROR: gh {' '.join(args[:3])}...", file=sys.stderr)
        print(f"  {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def prompt(label, default=None, required=True):
    """Prompt user for input with optional default."""
    if default:
        value = input(f"  {label} [{default}]: ").strip()
        return value or default
    else:
        value = input(f"  {label}: ").strip()
        if not value and required:
            print(f"  ERROR: {label} is required.")
            sys.exit(1)
        return value


def print_step(n, total, msg):
    """Print a formatted step header."""
    print(f"\n== Step {n}/{total}: {msg} ==")


def print_ok(msg):
    """Print a success message."""
    print(f"  [OK] {msg}")


def print_dry(msg):
    """Print a dry-run message."""
    print(f"  [DRY RUN] {msg}")


def print_warn(msg):
    """Print a warning message."""
    print(f"  [WARN] {msg}")


def print_skip(msg):
    """Print a skip message."""
    print(f"  [SKIP] {msg}")


# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
def check_gh_installed():
    """Verify gh CLI exists on PATH."""
    if shutil.which("gh") is None:
        print("ERROR: gh CLI not found.")
        print()
        print("  Install it from: https://cli.github.com")
        print("  Or via package manager:")
        print("    Windows:  winget install GitHub.cli")
        print("    macOS:    brew install gh")
        print("    Linux:    See https://github.com/cli/cli/blob/trunk/docs/install_linux.md")
        sys.exit(1)
    # Get version for display
    version = subprocess.run(
        ["gh", "--version"], capture_output=True, text=True
    ).stdout.strip().split("\n")[0]
    print_ok(f"gh CLI found ({version})")


def check_gh_authenticated():
    """Verify gh auth status. Returns True if authenticated."""
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True, text=True
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        print("ERROR: Not authenticated with GitHub CLI.")
        print()
        print("  Run: gh auth login")
        print("  Then re-run this script.")
        sys.exit(1)
    # Extract username
    for line in output.split("\n"):
        if "Logged in to" in line and "account" in line:
            print_ok(line.strip().lstrip("✓").strip())
            break
    return output


def check_gh_scopes(auth_output):
    """Warn if gist scope might be missing."""
    # gh auth status doesn't reliably show scopes, so we test directly
    result = subprocess.run(
        ["gh", "api", "gists", "--method", "GET", "-q", ".[0].id"],
        capture_output=True, text=True
    )
    if result.returncode != 0 and "403" in result.stderr:
        print_warn("Your gh CLI token may not have 'gist' scope.")
        print("  Run: gh auth refresh -s gist")
        print("  This adds the gist scope to your existing token.")
        resp = input("  Continue anyway? (y/N): ").strip().lower()
        if resp != "y":
            sys.exit(1)
    else:
        print_ok("Token has gist access")


def resolve_github_username():
    """Get the authenticated user's GitHub username."""
    return run_gh(["api", "user", "--jq", ".login"])


# ---------------------------------------------------------------------------
# Config gathering
# ---------------------------------------------------------------------------
def gather_config(args):
    """Build config dict, prompting for any missing values."""
    config = {}
    non_interactive = args.non_interactive

    # Owner
    if args.owner:
        config["owner"] = args.owner
    elif non_interactive:
        print("ERROR: --owner is required in non-interactive mode.")
        sys.exit(1)
    else:
        config["owner"] = prompt("GitHub owner (username or org)")

    # Repo
    if args.repo:
        config["repo"] = args.repo
    elif non_interactive:
        print("ERROR: --repo is required in non-interactive mode.")
        sys.exit(1)
    else:
        config["repo"] = prompt("Repository name")

    config["gh_repo"] = f"{config['owner']}/{config['repo']}"

    # Created date — try auto-detect
    if args.created:
        config["created"] = args.created
    elif non_interactive:
        print("ERROR: --created is required in non-interactive mode.")
        sys.exit(1)
    else:
        auto_date = None
        try:
            raw = run_gh(["api", f"repos/{config['gh_repo']}", "--jq", ".created_at"])
            auto_date = raw[:10]
        except SystemExit:
            pass  # Repo may not exist yet
        if auto_date:
            config["created"] = prompt("Repository creation date (YYYY-MM-DD)", default=auto_date)
        else:
            config["created"] = prompt("Repository creation date (YYYY-MM-DD)")

    # Display name
    if args.display_name:
        config["display_name"] = args.display_name
    elif non_interactive:
        # Derive from repo name
        config["display_name"] = config["repo"].replace("-", " ").replace("_", " ").title()
    else:
        default_name = config["repo"].replace("-", " ").replace("_", " ").title()
        config["display_name"] = prompt("Display name for dashboard", default=default_name)

    # CI workflows
    if args.ci_workflows is not None:
        config["ci_workflows"] = args.ci_workflows
    elif non_interactive:
        config["ci_workflows"] = []
    else:
        ci_input = input("  CI workflow names to trigger after (comma-separated, Enter to skip): ").strip()
        if ci_input:
            config["ci_workflows"] = [w.strip() for w in ci_input.split(",") if w.strip()]
        else:
            config["ci_workflows"] = []

    config["display_name_html"] = html_module.escape(config["display_name"])

    return config


def validate_config(config):
    """Validate configuration values."""
    # Date format
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", config["created"]):
        print(f"ERROR: Invalid date format '{config['created']}'. Expected YYYY-MM-DD.")
        sys.exit(1)

    # Check repo exists (optional — it might not exist yet)
    result = subprocess.run(
        ["gh", "api", f"repos/{config['gh_repo']}", "--jq", ".full_name"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print_warn(f"Repository {config['gh_repo']} not found on GitHub.")
        print("  This is OK if you haven't created it yet.")
        print("  Repository variables/secrets will be set once it exists.")


# ---------------------------------------------------------------------------
# Gist creation
# ---------------------------------------------------------------------------
def build_initial_state():
    """Build the initial empty state.json structure."""
    return {
        "totalClones": 0,
        "totalUniqueClones": 0,
        "totalDownloads": 0,
        "totalViews": 0,
        "totalUniqueViews": 0,
        "totalCiCheckouts": 0,
        "totalCiUniqueClones": 0,
        "totalOrganicUniqueClones": 0,
        "previousTotalDownloads": 0,
        "_previousCiUniqueToday": 0,
        "stars": 0,
        "forks": 0,
        "openIssues": 0,
        "lastSeenDates": [],
        "lastSeenViewDates": [],
        "dailyHistory": [],
        "ciCheckouts": {},
        "referrers": [],
        "popularPaths": []
    }


def build_badge(label, message="0", color="blue"):
    """Build a shields.io endpoint badge JSON."""
    return {
        "schemaVersion": 1,
        "label": label,
        "message": message,
        "color": color
    }


def create_badge_gist(config, dry_run):
    """Create the public badge gist with initial state + badge files."""
    files = {
        "state.json": json.dumps(build_initial_state(), indent=2),
        "installs.json": json.dumps(build_badge("installs"), indent=2),
        "downloads.json": json.dumps(build_badge("downloads"), indent=2),
        "clones.json": json.dumps(build_badge("clones"), indent=2),
        "views.json": json.dumps(build_badge("views"), indent=2),
    }

    description = f"{config['gh_repo']} traffic badges"

    if dry_run:
        print_dry(f"Would create PUBLIC gist: \"{description}\"")
        for name in files:
            print(f"    - {name}")
        return "<DRY_RUN_BADGE_GIST_ID>"

    payload = json.dumps({
        "description": description,
        "public": True,
        "files": {name: {"content": content} for name, content in files.items()}
    })

    print("  Creating gist with 5 files...")
    result = run_gh(["api", "gists", "--method", "POST", "--input", "-"], input_data=payload)
    gist_data = json.loads(result)
    gist_id = gist_data["id"]
    gist_url = gist_data["html_url"]
    print_ok(f"Badge gist created: {gist_id}")
    print(f"       {gist_url}")
    return gist_id


def create_archive_gist(config, dry_run):
    """Create the unlisted archive gist with initial archive.json."""
    archive_content = json.dumps({
        "repo": config["gh_repo"],
        "description": f"Monthly traffic archive for {config['gh_repo']}",
        "archives": []
    }, indent=2)

    description = f"{config['gh_repo']} traffic archive"

    if dry_run:
        print_dry(f"Would create UNLISTED gist: \"{description}\"")
        print("    - archive.json")
        return "<DRY_RUN_ARCHIVE_GIST_ID>"

    payload = json.dumps({
        "description": description,
        "public": False,
        "files": {"archive.json": {"content": archive_content}}
    })

    print("  Creating unlisted gist...")
    result = run_gh(["api", "gists", "--method", "POST", "--input", "-"], input_data=payload)
    gist_data = json.loads(result)
    gist_id = gist_data["id"]
    print_ok(f"Archive gist created: {gist_id}")
    return gist_id


# ---------------------------------------------------------------------------
# Repository variables and secrets
# ---------------------------------------------------------------------------
def set_repo_variable(name, value, gh_repo, dry_run):
    """Set a GitHub repository variable."""
    if dry_run:
        print_dry(f"Would set variable {name} = {value}")
        return

    # Try to set — if it already exists, update it
    result = subprocess.run(
        ["gh", "variable", "set", name, "--body", value, "-R", gh_repo],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print_warn(f"Could not set {name}: {result.stderr.strip()}")
        print(f"  Run manually: gh variable set {name} --body \"{value}\" -R {gh_repo}")
    else:
        print_ok(f"{name} = {value}")


def guide_token_setup(config, dry_run):
    """Guide user through PAT creation and offer to set the secret."""
    token_name = config.get("gist_token_name", "TRAFFIC_GIST_TOKEN")
    gh_repo = config["gh_repo"]

    print()
    print("  The workflow needs a Personal Access Token (PAT) with 'gist' scope")
    print("  to update your gists. This is SEPARATE from your gh CLI token.")
    print()
    print("  To create one:")
    print(f"    1. Go to: https://github.com/settings/tokens/new")
    print(f"    2. Name it: \"Traffic Tracker - {gh_repo}\"")
    print("    3. Check ONLY the 'gist' scope")
    print("    4. Set expiration (recommended: no expiration, or 1 year)")
    print("    5. Click 'Generate token' and copy the value")
    print()

    if dry_run:
        print_dry(f"Would prompt for PAT and set secret {token_name}")
        return

    if config.get("non_interactive"):
        print(f"  Then run: gh secret set {token_name} -R {gh_repo}")
        return

    token = input("  Paste your PAT here (or press Enter to skip): ").strip()
    if token:
        result = subprocess.run(
            ["gh", "secret", "set", token_name, "-R", gh_repo],
            capture_output=True, text=True,
            input=token
        )
        if result.returncode != 0:
            print_warn(f"Could not set secret: {result.stderr.strip()}")
            print(f"  Run manually: gh secret set {token_name} -R {gh_repo}")
        else:
            print_ok(f"Secret {token_name} set successfully")
    else:
        print_skip("PAT not provided")
        print(f"  Remember to run: gh secret set {token_name} -R {gh_repo}")


# ---------------------------------------------------------------------------
# File configuration (--configure)
# ---------------------------------------------------------------------------
def apply_replacements(filepath, replacements, config, dry_run):
    """Apply a list of (pattern, template, description) replacements to a file.

    Returns count of successful replacements.
    """
    if not filepath.exists():
        print_warn(f"File not found: {filepath}")
        return 0

    content = filepath.read_text(encoding="utf-8")
    original = content
    success = 0

    for pattern, template, desc in replacements:
        formatted = template.format(**config)
        new_content, count = re.subn(pattern, formatted, content, count=1)
        if count > 0:
            content = new_content
            success += 1
            if dry_run:
                print_dry(f"{desc}")
            else:
                print_ok(f"{desc}")
        else:
            print_skip(f"{desc} (pattern not found)")

    if not dry_run and content != original:
        filepath.write_text(content, encoding="utf-8")

    return success


def configure_dashboard(config, dry_run):
    """Update docs/stats/index.html with project-specific values."""
    print(f"  Updating {DASHBOARD_PATH.relative_to(PROJECT_ROOT)}...")

    replacements = [
        # HTML title
        (r'<title>.*?- Project Statistics</title>',
         '<title>{display_name_html} - Project Statistics</title>',
         "HTML title"),
        # Banner link href
        (r'href="https://github\.com/[^"]+?" class="banner-link"',
         'href="https://github.com/{owner}/{repo}" class="banner-link"',
         "Banner link URL"),
        # Banner title text
        (r'<p class="banner-title">.*?</p>',
         '<p class="banner-title">{display_name_html}</p>',
         "Banner title"),
        # Footer repository link
        (r'<a href="https://github\.com/[^"]+?">Repository</a>',
         '<a href="https://github.com/{owner}/{repo}">Repository</a>',
         "Footer repo link"),
        # Footer releases link
        (r'<a href="https://github\.com/[^"]+?/releases">Releases</a>',
         '<a href="https://github.com/{owner}/{repo}/releases">Releases</a>',
         "Footer releases link"),
        # JS config: GIST_RAW_BASE
        (r"const GIST_RAW_BASE = '[^']+';",
         "const GIST_RAW_BASE = 'https://gist.githubusercontent.com/{gh_username}/{badge_gist_id}/raw';",
         "Gist raw base URL"),
        # JS config: ARCHIVE_GIST_ID
        (r"const ARCHIVE_GIST_ID = '[^']+';",
         "const ARCHIVE_GIST_ID = '{archive_gist_id}';",
         "Archive gist ID"),
        # JS config: REPO_OWNER
        (r"const REPO_OWNER = '[^']+';",
         "const REPO_OWNER = '{owner}';",
         "Repo owner"),
        # JS config: REPO_NAME
        (r"const REPO_NAME = '[^']+';",
         "const REPO_NAME = '{repo}';",
         "Repo name"),
        # JS config: REPO_CREATED
        (r"const REPO_CREATED = '[^']+';",
         "const REPO_CREATED = '{created}';",
         "Repo creation date"),
    ]

    return apply_replacements(DASHBOARD_PATH, replacements, config, dry_run)


def configure_readme(config, dry_run):
    """Update docs/stats/README.md with project-specific values."""
    print(f"  Updating {DASHBOARD_README_PATH.relative_to(PROJECT_ROOT)}...")

    # Need lowercase owner for GitHub Pages URL
    config["owner_lower"] = config["owner"].lower()

    replacements = [
        # Project name and link (line ~3)
        (r'\[.*?\]\(https://github\.com/[^)]+\)\.',
         '[{display_name}](https://github.com/{owner}/{repo}).',
         "Project link"),
        # Badge gist link
        (r'\[Badge Gist\]\(https://gist\.github\.com/[^)]+\)',
         '[Badge Gist](https://gist.github.com/{gh_username}/{badge_gist_id})',
         "Badge gist link"),
        # Dashboard URL
        (r'\*\*https://[^*]+/stats/\*\*',
         '**https://{owner_lower}.github.io/{repo}/stats/**',
         "Dashboard URL"),
    ]

    return apply_replacements(DASHBOARD_README_PATH, replacements, config, dry_run)


def configure_workflow(config, dry_run):
    """Update .github/workflows/traffic-badges.yml."""
    print(f"  Updating {WORKFLOW_PATH.relative_to(PROJECT_ROOT)}...")

    if not WORKFLOW_PATH.exists():
        print_warn(f"File not found: {WORKFLOW_PATH}")
        return 0

    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    original = content
    changes = 0

    # 1. Handle workflow_run trigger
    if config.get("ci_workflows"):
        names = json.dumps(config["ci_workflows"])
        new_content = re.sub(
            r'workflows: \[.*?\]',
            f'workflows: {names}',
            content
        )
        if new_content != content:
            content = new_content
            changes += 1
            msg = f"workflow_run trigger: {names}"
            print_dry(msg) if dry_run else print_ok(msg)
    else:
        # Comment out the workflow_run block
        new_content = re.sub(
            r'  workflow_run:.*?\n    workflows:.*?\n    types:.*?\n',
            '  # workflow_run:            # Uncomment and set your CI workflow name to run after CI\n'
            '  #   workflows: ["CI"]\n'
            '  #   types: [completed]\n',
            content
        )
        if new_content != content:
            content = new_content
            changes += 1
            msg = "workflow_run trigger: commented out (no CI workflows specified)"
            print_dry(msg) if dry_run else print_ok(msg)

    # 2. Update archive version string
    new_content = re.sub(
        r'version: "[^"]+",',
        'version: "0.1.0",',
        content
    )
    if new_content != content:
        content = new_content
        changes += 1
        msg = "Archive version: 0.1.0"
        print_dry(msg) if dry_run else print_ok(msg)

    if not dry_run and content != original:
        WORKFLOW_PATH.write_text(content, encoding="utf-8")

    return changes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        prog="setup-gists",
        description="Set up GitHub traffic tracking gists for your repository.",
        epilog=(
            "Examples:\n"
            "  python setup-gists.py\n"
            "  python setup-gists.py --owner myorg --repo myproject --configure\n"
            "  python setup-gists.py --dry-run --owner test --repo test --created 2025-01-01\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Required info (interactive prompts if not provided)
    parser.add_argument("--owner", help="GitHub username or organization")
    parser.add_argument("--repo", help="Repository name")
    parser.add_argument("--created", help="Repository creation date (YYYY-MM-DD)")
    parser.add_argument("--display-name", help="Display name for dashboard title/banner")

    # Optional CI workflow trigger
    parser.add_argument("--ci-workflows", nargs="*", default=None,
                        help="CI workflow names for workflow_run trigger "
                             "(omit to comment out trigger)")

    # Modes
    parser.add_argument("--configure", action="store_true",
                        help="Also update dashboard and workflow files with your values")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without creating gists or modifying files")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Fail on missing arguments instead of prompting")

    # Advanced
    parser.add_argument("--skip-variables", action="store_true",
                        help="Skip setting repository variables/secrets (just create gists)")
    parser.add_argument("--gist-token-name", default="TRAFFIC_GIST_TOKEN",
                        help="Name for the gist token secret (default: TRAFFIC_GIST_TOKEN)")

    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # Header
    # -----------------------------------------------------------------------
    print()
    print("GitHub Traffic Tracker Setup")
    print("=" * 40)

    if args.dry_run:
        print("[DRY RUN MODE — no changes will be made]")

    # -----------------------------------------------------------------------
    # Prerequisites
    # -----------------------------------------------------------------------
    print("\nChecking prerequisites...")
    check_gh_installed()
    auth_output = check_gh_authenticated()
    check_gh_scopes(auth_output)
    gh_username = resolve_github_username()
    print_ok(f"GitHub username: {gh_username}")

    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------
    print("\nGathering configuration...")
    config = gather_config(args)
    config["gh_username"] = gh_username
    config["gist_token_name"] = args.gist_token_name
    config["non_interactive"] = args.non_interactive

    validate_config(config)

    total_steps = 3  # gist creation (2) + variables (1)
    if args.configure:
        total_steps += 1
    if not args.skip_variables:
        total_steps += 1  # PAT guidance

    print(f"\n  Owner:        {config['owner']}")
    print(f"  Repository:   {config['repo']}")
    print(f"  Created:      {config['created']}")
    print(f"  Display Name: {config['display_name']}")
    if config["ci_workflows"]:
        print(f"  CI Workflows: {', '.join(config['ci_workflows'])}")
    else:
        print("  CI Workflows: (none)")
    print(f"  Configure:    {'yes' if args.configure else 'no'}")

    if not args.non_interactive and not args.dry_run:
        print()
        resp = input("  Proceed? (Y/n): ").strip().lower()
        if resp == "n":
            print("  Setup cancelled.")
            sys.exit(0)

    # -----------------------------------------------------------------------
    # Step 1: Create badge gist
    # -----------------------------------------------------------------------
    step = 1
    print_step(step, total_steps, "Create badge gist (public)")
    badge_gist_id = create_badge_gist(config, args.dry_run)
    config["badge_gist_id"] = badge_gist_id

    # -----------------------------------------------------------------------
    # Step 2: Create archive gist
    # -----------------------------------------------------------------------
    step += 1
    print_step(step, total_steps, "Create archive gist (unlisted)")
    archive_gist_id = create_archive_gist(config, args.dry_run)
    config["archive_gist_id"] = archive_gist_id

    # -----------------------------------------------------------------------
    # Step 3: Set repository variables
    # -----------------------------------------------------------------------
    if not args.skip_variables:
        step += 1
        print_step(step, total_steps, "Set repository variables")
        set_repo_variable("TRAFFIC_GIST_ID", badge_gist_id, config["gh_repo"], args.dry_run)
        set_repo_variable("TRAFFIC_ARCHIVE_GIST_ID", archive_gist_id, config["gh_repo"], args.dry_run)

        # -----------------------------------------------------------------------
        # Step 4: PAT guidance
        # -----------------------------------------------------------------------
        step += 1
        print_step(step, total_steps, f"Repository secret ({config['gist_token_name']})")
        guide_token_setup(config, args.dry_run)

    # -----------------------------------------------------------------------
    # Step 5: Configure files (optional)
    # -----------------------------------------------------------------------
    if args.configure:
        step += 1
        print_step(step, total_steps, "Configure project files")
        configure_dashboard(config, args.dry_run)
        configure_readme(config, args.dry_run)
        configure_workflow(config, args.dry_run)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print()
    print("=" * 40)
    if args.dry_run:
        print("Dry run complete! Re-run without --dry-run to apply.")
    else:
        print("Setup complete!")

    print(f"\n  Badge Gist ID:   {badge_gist_id}")
    print(f"  Archive Gist ID: {archive_gist_id}")

    gist_base = f"https://gist.githubusercontent.com/{gh_username}/{badge_gist_id}/raw"
    print(f"\nBadge URLs:")
    print(f"  Installs:  https://img.shields.io/endpoint?url={gist_base}/installs.json")
    print(f"  Downloads: https://img.shields.io/endpoint?url={gist_base}/downloads.json")
    print(f"  Clones:    https://img.shields.io/endpoint?url={gist_base}/clones.json")
    print(f"  Views:     https://img.shields.io/endpoint?url={gist_base}/views.json")

    print(f"\nBadge Markdown (copy-paste for README):")
    shield_base = "https://img.shields.io/endpoint?url=" + gist_base
    owner_lower = config["owner"].lower()
    stats_url = f"https://{owner_lower}.github.io/{config['repo']}/stats/"
    print(f'  [![Installs]({shield_base}/installs.json)]({stats_url}#installs)')

    print(f"\nNext steps:")
    if args.skip_variables:
        print(f"  1. Set repo variables:")
        print(f"     gh variable set TRAFFIC_GIST_ID --body \"{badge_gist_id}\" -R {config['gh_repo']}")
        print(f"     gh variable set TRAFFIC_ARCHIVE_GIST_ID --body \"{archive_gist_id}\" -R {config['gh_repo']}")
        print(f"  2. Set repo secret with a PAT (gist scope):")
        print(f"     gh secret set {config['gist_token_name']} -R {config['gh_repo']}")
    if not args.configure:
        print(f"  - Run again with --configure to update dashboard/workflow files")
    print(f"  - Commit and push your changes")
    print(f"  - Enable GitHub Pages (Settings > Pages > Deploy from branch > main, /docs)")
    print(f"  - Trigger the workflow manually or wait for the 3am UTC schedule:")
    print(f"    gh workflow run \"Track Downloads & Clones\" -R {config['gh_repo']}")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
        sys.exit(130)
