"""ghtraf create — Create gists and configure repository for traffic tracking.

This is the bootstrap command. It creates the badge and archive gists,
sets repository variables/secrets, and optionally configures dashboard
and workflow files with project-specific values.

Equivalent to the standalone setup-gists.py script.
"""

import html as html_module
import re
import sys
from datetime import date
from pathlib import Path

from ghtraf import gh, gist, configure
from ghtraf.config import register_repo_globally, save_project_config
from ghtraf.lib.log_lib import get_output
from ghtraf.output import (
    print_dry, print_ok, print_skip, print_step, print_warn, prompt,
)


def register(subparsers, parents):
    """Register the 'create' subcommand."""
    p = subparsers.add_parser(
        "create",
        parents=parents,
        help="Create gists and set repository variables for traffic tracking",
        description=(
            "Create the public badge gist and unlisted archive gist needed by the\n"
            "traffic-badges.yml workflow, then optionally configure repository\n"
            "variables/secrets and update dashboard files."
        ),
        formatter_class=__import__("argparse").RawDescriptionHelpFormatter,
    )

    # create-specific args
    p.add_argument("--created", metavar="DATE",
                   help="Repository creation date (YYYY-MM-DD)")
    p.add_argument("--display-name", metavar="NAME",
                   help="Display name for dashboard title/banner")
    p.add_argument("--ci-workflows", nargs="*", default=None,
                   help="CI workflow names for workflow_run trigger "
                        "(omit to comment out trigger)")
    p.add_argument("--configure", action="store_true", dest="configure_files",
                   help="Also update dashboard and workflow files with your values")
    p.add_argument("--skip-variables", action="store_true",
                   help="Skip setting repository variables/secrets")
    p.add_argument("--gist-token-name", default="TRAFFIC_GIST_TOKEN",
                   help="Name for the gist token secret "
                        "(default: TRAFFIC_GIST_TOKEN)")

    p.set_defaults(func=run)


def _gather_config(args):
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

    # Created date — try auto-detect, fall back to today
    if args.created:
        config["created"] = args.created
    else:
        auto_date = gh.get_repo_created_date(config["gh_repo"])
        if non_interactive:
            config["created"] = auto_date or date.today().isoformat()
        elif auto_date:
            config["created"] = prompt(
                "Repository creation date (YYYY-MM-DD)", default=auto_date)
        else:
            config["created"] = prompt(
                "Repository creation date (YYYY-MM-DD)",
                default=date.today().isoformat())

    # Display name
    if args.display_name:
        config["display_name"] = args.display_name
    elif non_interactive:
        config["display_name"] = (config["repo"]
                                  .replace("-", " ")
                                  .replace("_", " ")
                                  .title())
    else:
        default_name = (config["repo"]
                        .replace("-", " ")
                        .replace("_", " ")
                        .title())
        config["display_name"] = prompt(
            "Display name for dashboard", default=default_name)

    # CI workflows
    if args.ci_workflows is not None:
        config["ci_workflows"] = args.ci_workflows
    elif non_interactive:
        config["ci_workflows"] = []
    else:
        ci_input = input(
            "  CI workflow names to trigger after "
            "(comma-separated, Enter to skip): "
        ).strip()
        if ci_input:
            config["ci_workflows"] = [
                w.strip() for w in ci_input.split(",") if w.strip()
            ]
        else:
            config["ci_workflows"] = []

    config["display_name_html"] = html_module.escape(config["display_name"])

    return config


def _validate_config(config):
    """Validate configuration values."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", config["created"]):
        print(f"ERROR: Invalid date format '{config['created']}'. "
              "Expected YYYY-MM-DD.")
        sys.exit(1)

    repo_exists = gh.check_repo_exists(config["gh_repo"])
    if not repo_exists:
        print_warn(f"Repository {config['gh_repo']} not found on GitHub.")
        print("  This is OK if you haven't created it yet.")
        print("  Repository variables/secrets will be set once it exists.")


def _guide_token_setup(config, dry_run=False):
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
        success = gh.set_repo_secret(token_name, token, gh_repo)
        if not success:
            print_warn("Could not set secret.")
            print(f"  Run manually: gh secret set {token_name} -R {gh_repo}")
        else:
            print_ok(f"Secret {token_name} set successfully")
    else:
        print_skip("PAT not provided")
        print(f"  Remember to run: gh secret set {token_name} -R {gh_repo}")


def run(args):
    """Execute the create command."""
    dry_run = args.dry_run

    # Header
    print()
    print("GitHub Traffic Tracker Setup")
    print("=" * 40)
    if dry_run:
        print("[DRY RUN MODE - no changes will be made]")

    # Prerequisites
    import ghtraf.hints  # noqa: F401 — register domain hints
    out = get_output()
    print("\nChecking prerequisites...")
    out.emit(1, "  [setup] Checking gh CLI installation...", channel='setup')
    version = gh.check_gh_installed()
    print_ok(f"gh CLI found ({version})")

    out.emit(1, "  [api] Checking GitHub authentication...", channel='api')
    auth_output = gh.check_gh_authenticated()
    # Extract login line for display
    for line in auth_output.split("\n"):
        if "Logged in to" in line and "account" in line:
            print_ok(line.strip().lstrip("\u2713").strip())
            break

    has_gist_scope = gh.check_gh_scopes(auth_output)
    if not has_gist_scope:
        print_warn("Your gh CLI token may not have 'gist' scope.")
        print("  Run: gh auth refresh -s gist")
        if not args.non_interactive:
            resp = input("  Continue anyway? (y/N): ").strip().lower()
            if resp != "y":
                sys.exit(1)
    else:
        print_ok("Token has gist access")

    gh_username = gh.resolve_github_username()
    print_ok(f"GitHub username: {gh_username}")

    # Configuration
    print("\nGathering configuration...")
    out.emit(1, "  [setup] Gathering configuration (interactive={interactive})",
             channel='setup', interactive=not args.non_interactive)
    config = _gather_config(args)
    config["gh_username"] = gh_username
    config["gist_token_name"] = args.gist_token_name
    config["non_interactive"] = args.non_interactive

    _validate_config(config)
    out.emit(2, "  [config] Resolved: owner={owner}, repo={repo}, created={created}",
             channel='config', owner=config['owner'], repo=config['repo'],
             created=config['created'])
    out.emit(2, "  [config] display_name={dn}, ci_workflows={ci}",
             channel='config', dn=config['display_name'],
             ci=config['ci_workflows'])

    total_steps = 3
    if args.configure_files:
        total_steps += 1
    if not args.skip_variables:
        total_steps += 1

    print(f"\n  Owner:        {config['owner']}")
    print(f"  Repository:   {config['repo']}")
    print(f"  Created:      {config['created']}")
    print(f"  Display Name: {config['display_name']}")
    if config["ci_workflows"]:
        print(f"  CI Workflows: {', '.join(config['ci_workflows'])}")
    else:
        print("  CI Workflows: (none)")
    print(f"  Configure:    {'yes' if args.configure_files else 'no'}")

    if not args.non_interactive and not dry_run:
        print()
        resp = input("  Proceed? (Y/n): ").strip().lower()
        if resp == "n":
            print("  Setup cancelled.")
            return 0

    # Step 1: Create badge gist
    step = 1
    print_step(step, total_steps, "Create badge gist (public)")
    out.emit(1, "  [gist] Creating public badge gist for {repo}",
             channel='gist', repo=config['gh_repo'])
    badge_gist_id = gist.create_badge_gist(config, dry_run=dry_run)
    out.emit(2, "  [gist] Badge gist ID: {gid}", channel='gist', gid=badge_gist_id)
    config["badge_gist_id"] = badge_gist_id

    # Step 2: Create archive gist
    step += 1
    print_step(step, total_steps, "Create archive gist (unlisted)")
    out.emit(1, "  [gist] Creating unlisted archive gist for {repo}",
             channel='gist', repo=config['gh_repo'])
    archive_gist_id = gist.create_archive_gist(config, dry_run=dry_run)
    out.emit(2, "  [gist] Archive gist ID: {gid}", channel='gist', gid=archive_gist_id)
    config["archive_gist_id"] = archive_gist_id

    # Step 3: Set repository variables
    if not args.skip_variables:
        step += 1
        print_step(step, total_steps, "Set repository variables")
        out.emit(1, "  [api] Setting repository variables on {repo}",
                 channel='api', repo=config['gh_repo'])

        success = gh.set_repo_variable(
            "TRAFFIC_GIST_ID", badge_gist_id, config["gh_repo"], dry_run)
        if dry_run:
            print_dry(f"Would set variable TRAFFIC_GIST_ID = {badge_gist_id}")
        elif success:
            print_ok(f"TRAFFIC_GIST_ID = {badge_gist_id}")
        else:
            print_warn("Could not set TRAFFIC_GIST_ID")
            print(f"  Run manually: gh variable set TRAFFIC_GIST_ID "
                  f"--body \"{badge_gist_id}\" -R {config['gh_repo']}")

        success = gh.set_repo_variable(
            "TRAFFIC_ARCHIVE_GIST_ID", archive_gist_id,
            config["gh_repo"], dry_run)
        if dry_run:
            print_dry(f"Would set variable TRAFFIC_ARCHIVE_GIST_ID = "
                      f"{archive_gist_id}")
        elif success:
            print_ok(f"TRAFFIC_ARCHIVE_GIST_ID = {archive_gist_id}")
        else:
            print_warn("Could not set TRAFFIC_ARCHIVE_GIST_ID")
            print(f"  Run manually: gh variable set TRAFFIC_ARCHIVE_GIST_ID "
                  f"--body \"{archive_gist_id}\" -R {config['gh_repo']}")

        # PAT guidance
        step += 1
        print_step(step, total_steps,
                   f"Repository secret ({config['gist_token_name']})")
        _guide_token_setup(config, dry_run=dry_run)
        out.hint('setup.pat', 'verbose')

    # Step 4: Configure files (optional)
    if args.configure_files:
        step += 1
        print_step(step, total_steps, "Configure project files")

        repo_dir = Path(args.repo_dir or ".").resolve()
        dashboard_path = repo_dir / "docs" / "stats" / "index.html"
        readme_path = repo_dir / "docs" / "stats" / "README.md"
        workflow_path = repo_dir / ".github" / "workflows" / "traffic-badges.yml"

        configure.configure_dashboard(config, dashboard_path, dry_run=dry_run)
        configure.configure_readme(config, readme_path, dry_run=dry_run)
        configure.configure_workflow(config, workflow_path, dry_run=dry_run)

    # Write config files
    out.emit(1, "  [config] Writing project configuration...", channel='config')
    if not dry_run:
        repo_dir = Path(args.repo_dir or ".").resolve()
        project_cfg = {
            "owner": config["owner"],
            "repo": config["repo"],
            "created": config["created"],
            "display_name": config["display_name"],
            "badge_gist_id": badge_gist_id,
            "archive_gist_id": archive_gist_id,
            "dashboard_dir": "docs/stats",
            "schema_version": 1,
        }
        if config["ci_workflows"]:
            project_cfg["ci_workflows"] = config["ci_workflows"]

        save_project_config(project_cfg, repo_dir)
        register_repo_globally(
            owner=config["owner"],
            repo=config["repo"],
            badge_gist_id=badge_gist_id,
            archive_gist_id=archive_gist_id,
            repo_dir=str(repo_dir),
            display_name=config["display_name"],
            created=config["created"],
        )

    # Summary
    print()
    print("=" * 40)
    if dry_run:
        print("Dry run complete! Re-run without --dry-run to apply.")
    else:
        print("Setup complete!")
        out.hint('config.remember', 'result')

    print(f"\n  Badge Gist ID:   {badge_gist_id}")
    print(f"  Archive Gist ID: {archive_gist_id}")

    gist_base = (f"https://gist.githubusercontent.com/"
                 f"{gh_username}/{badge_gist_id}/raw")
    print(f"\nBadge URLs:")
    print(f"  Installs:  https://img.shields.io/endpoint?url="
          f"{gist_base}/installs.json")
    print(f"  Downloads: https://img.shields.io/endpoint?url="
          f"{gist_base}/downloads.json")
    print(f"  Clones:    https://img.shields.io/endpoint?url="
          f"{gist_base}/clones.json")
    print(f"  Views:     https://img.shields.io/endpoint?url="
          f"{gist_base}/views.json")

    print(f"\nBadge Markdown (copy-paste for README):")
    shield_base = "https://img.shields.io/endpoint?url=" + gist_base
    owner_lower = config["owner"].lower()
    stats_url = f"https://{owner_lower}.github.io/{config['repo']}/stats/"
    print(f'  [![Installs]({shield_base}/installs.json)]({stats_url}#installs)')

    print(f"\nNext steps:")
    if args.skip_variables:
        print(f"  1. Set repo variables:")
        print(f"     gh variable set TRAFFIC_GIST_ID "
              f"--body \"{badge_gist_id}\" -R {config['gh_repo']}")
        print(f"     gh variable set TRAFFIC_ARCHIVE_GIST_ID "
              f"--body \"{archive_gist_id}\" -R {config['gh_repo']}")
        print(f"  2. Set repo secret with a PAT (gist scope):")
        print(f"     gh secret set {config['gist_token_name']} "
              f"-R {config['gh_repo']}")
    if not args.configure_files:
        print("  - Run again with --configure to update dashboard/workflow files")
        out.hint('setup.configure', 'result')
    print("  - Commit and push your changes")
    print("  - Enable GitHub Pages (Settings > Pages > Deploy from branch "
          "> main, /docs)")
    print("  - Trigger the workflow manually or wait for the 3am UTC schedule:")
    print(f"    gh workflow run \"Track Downloads & Clones\" "
          f"-R {config['gh_repo']}")
    print()

    return 0
