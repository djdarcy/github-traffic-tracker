"""ghtraf create — Bootstrap a repository for GitHub traffic tracking.

Creates the badge and archive gists, sets repository variables/secrets,
copies template files, and optionally configures dashboard and workflow
files with project-specific values.

Use --files-only to deploy template files without cloud setup
(replaces the former 'ghtraf init' command).

Equivalent to the standalone setup-gists.py script.
"""

import html as html_module
import re
import shutil
import sys
from datetime import date
from importlib.resources import as_file, files
from pathlib import Path

from ghtraf import gh, gist, configure
from ghtraf.config import find_project_config, register_repo_globally, save_project_config
from ghtraf.lib.log_lib import get_output
from ghtraf.output import (
    print_banner, print_dry, print_error, print_info, print_ok,
    print_skip, print_step, print_warn, prompt,
)


# Template files relative to the package templates root.
TEMPLATE_FILES = [
    Path(".github") / "workflows" / "traffic-badges.yml",
    Path("docs") / "stats" / "index.html",
    Path("docs") / "stats" / "README.md",
    Path("docs") / "stats" / "favicon.svg",
]


def register(subparsers, parents):
    """Register the 'create' subcommand."""
    p = subparsers.add_parser(
        "create",
        parents=parents,
        help="Create gists, deploy templates, and configure a repository",
        description=(
            "Bootstrap a repository for traffic tracking. By default, creates\n"
            "the public badge gist and unlisted archive gist needed by the\n"
            "traffic-badges.yml workflow, then optionally configures repository\n"
            "variables/secrets and updates dashboard files.\n"
            "\n"
            "Use --files-only to deploy template files without cloud setup\n"
            "(replaces the former 'ghtraf init' command)."
        ),
        formatter_class=__import__("argparse").RawDescriptionHelpFormatter,
    )

    # Phase flag
    p.add_argument("--files-only", action="store_true", default=False,
                   help="Only copy template files (skip cloud setup)")

    # File deployment flags (used with --files-only)
    overwrite = p.add_mutually_exclusive_group()
    overwrite.add_argument(
        "--force", action="store_true", default=False,
        help="Overwrite existing template files without prompting",
    )
    overwrite.add_argument(
        "--skip-existing", action="store_true", default=False,
        help="Skip template files that already exist (only copy new ones)",
    )

    # Cloud setup args
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


# ---------------------------------------------------------------------------
# Template deployment helpers (absorbed from former 'ghtraf init')
# ---------------------------------------------------------------------------
def _discover_repo_dir(args):
    """Discover the target repository directory.

    Priority: --repo-dir > .ghtraf.json walk-up > .git walk-up > cwd.

    When .git is found in a parent directory (not cwd), the user is
    prompted for confirmation in interactive mode, or warned in
    non-interactive mode. This prevents silently deploying templates
    into a parent repo (monorepo, submodule, dotfiles repo in ~).
    """
    # 1. Explicit --repo-dir
    if args.repo_dir:
        return Path(args.repo_dir).resolve()

    # 2. Walk up for .ghtraf.json (project-specific — safe, no confirmation)
    cfg_path = find_project_config()
    if cfg_path:
        return cfg_path.parent

    cwd = Path.cwd().resolve()

    # 3. Walk up for .git
    current = cwd
    for _ in range(20):
        if (current / ".git").exists():
            if current != cwd:
                # .git found in a parent dir — confirm before using
                non_interactive = getattr(args, 'non_interactive', False)
                if not non_interactive:
                    print_info(
                                f"\n  No .ghtraf.json found in current directory.\n"
                                f"  Found git repository at: {current}"
                    )
                    response = input(
                        "  Use this directory? [Y/n]: "
                    ).strip().lower()
                    if response in ('n', 'no'):
                        print_info(f"  Using current directory instead: {cwd}")
                        return cwd
                else:
                    print_warn(
                        f"Using parent git repo: {current} (no .ghtraf.json in cwd)"
                    )
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    # 4. Fall back to cwd
    return cwd


def _get_template_root():
    """Return the package templates root as a Traversable.

    Separated for testability — tests can mock this to provide
    a temporary directory instead of the installed package.
    """
    return files('ghtraf') / 'templates'


def _prompt_overwrite(rel_path, non_interactive):
    """Prompt user about overwriting an existing file.

    Returns: 'y' (overwrite this file), 'n' (skip), 'a' (overwrite all remaining).
    """
    if non_interactive:
        return 'n'  # skip in non-interactive mode

    while True:
        response = input(
            f"  {rel_path} already exists. Overwrite? [y/N/a(ll)]: "
        ).strip().lower()
        if response in ('', 'n'):
            return 'n'
        if response == 'y':
            return 'y'
        if response in ('a', 'all'):
            return 'a'
        print_info("  Please enter y, n, or a.")


def _run_deploy_templates(args):
    """Deploy template files to target repo (formerly 'ghtraf init')."""
    dry_run = args.dry_run
    force = getattr(args, 'force', False)
    skip_existing = getattr(args, 'skip_existing', False)
    non_interactive = args.non_interactive
    out = get_output()

    # Discover target directory
    repo_dir = _discover_repo_dir(args)
    out.emit(1, "  [setup] Target directory: {d}", channel='setup', d=repo_dir)

    print_banner("\nghtraf create --files-only — Deploy template files\n" + "=" * 40)
    if dry_run:
        print_info("[DRY RUN MODE — no files will be written]")
    print_info(f"  Target: {repo_dir}\n")

    # Copy each template file
    template_root = _get_template_root()
    overwrite_all = force
    copied = 0
    skipped = 0

    with as_file(template_root) as src_root:
        for rel_path in TEMPLATE_FILES:
            src_file = src_root / rel_path
            dest_file = repo_dir / rel_path

            out.emit(2, "  [setup] Processing: {f}", channel='setup',
                     f=str(rel_path))

            if not src_file.is_file():
                print_warn(f"Template not found: {rel_path}")
                continue

            if dest_file.exists() and not overwrite_all:
                if skip_existing:
                    print_skip(f"{rel_path} (already exists)")
                    skipped += 1
                    continue

                if dry_run:
                    print_dry(f"Would prompt: {rel_path} already exists")
                    skipped += 1
                    continue

                choice = _prompt_overwrite(rel_path, non_interactive)
                if choice == 'n':
                    print_skip(f"{rel_path} (kept existing)")
                    skipped += 1
                    continue
                elif choice == 'a':
                    overwrite_all = True
                    # Fall through to copy

            # Copy the file
            if dry_run:
                print_dry(f"Would copy: {rel_path}")
            else:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dest_file)
                print_ok(f"{rel_path}")
                out.emit(2, "  [setup] Copied {src} -> {dst}",
                         channel='setup', src=str(src_file),
                         dst=str(dest_file))
            copied += 1

    # Summary
    print_info("")
    if dry_run:
        print_info(f"  Would copy {copied} file(s), skip {skipped} file(s).")
    else:
        print_info(f"  Copied {copied} file(s), skipped {skipped} file(s).")

    if copied > 0 and not dry_run:
        import ghtraf.hints  # noqa: F401
        out.hint('setup.configure', 'result')
        print_info("")
        print_info("  Next: Run 'ghtraf create --configure' to fill in project values.")

    print_info("")
    return 0


# ---------------------------------------------------------------------------
# Cloud setup helpers
# ---------------------------------------------------------------------------
def _gather_config(args):
    """Build config dict, prompting for any missing values."""
    config = {}
    non_interactive = args.non_interactive

    # Owner
    if args.owner:
        config["owner"] = args.owner
    elif non_interactive:
        print_error("--owner is required in non-interactive mode.")
        sys.exit(1)
    else:
        config["owner"] = prompt("GitHub owner (username or org)")

    # Repo
    if args.repo:
        config["repo"] = args.repo
    elif non_interactive:
        print_error("--repo is required in non-interactive mode.")
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
        print_error(f"Invalid date format '{config['created']}'. "
                    "Expected YYYY-MM-DD.")
        sys.exit(1)

    repo_exists = gh.check_repo_exists(config["gh_repo"])
    if not repo_exists:
        print_warn(f"Repository {config['gh_repo']} not found on GitHub.")
        print_info(
                    "  This is OK if you haven't created it yet.\n"
                    "  Repository variables/secrets will be set once it exists."
        )


def _guide_token_setup(config, dry_run=False):
    """Guide user through PAT creation and offer to set the secret."""
    token_name = config.get("gist_token_name", "TRAFFIC_GIST_TOKEN")
    gh_repo = config["gh_repo"]

    print_info( "\n"
                "  The workflow needs a Personal Access Token (PAT) with 'gist' scope\n"
                "  to update your gists. This is SEPARATE from your gh CLI token.\n"
                "\n"
                "  To create one:\n"
                f"    1. Go to: https://github.com/settings/tokens/new\n"
                f"    2. Name it: \"Traffic Tracker - {gh_repo}\"\n"
                "    3. Check ONLY the 'gist' scope\n"
                "    4. Set expiration (recommended: no expiration, or 1 year)\n"
                "    5. Click 'Generate token' and copy the value\n"
    )

    if dry_run:
        print_dry(f"Would prompt for PAT and set secret {token_name}")
        return

    if config.get("non_interactive"):
        print_info(f"  Then run: gh secret set {token_name} -R {gh_repo}")
        return

    token = input("  Paste your PAT here (or press Enter to skip): ").strip()
    if token:
        success = gh.set_repo_secret(token_name, token, gh_repo)
        if not success:
            print_warn("Could not set secret.")
            print_info(f"  Run manually: gh secret set {token_name} -R {gh_repo}")
        else:
            print_ok(f"Secret {token_name} set successfully")
    else:
        print_skip("PAT not provided")
        print_info(f"  Remember to run: gh secret set {token_name} -R {gh_repo}")


def run(args):
    """Execute the create command."""
    # Dispatch to template deployment if --files-only
    if getattr(args, 'files_only', False):
        return _run_deploy_templates(args)

    dry_run = args.dry_run

    # Header
    print_banner("\nGitHub Traffic Tracker Setup\n" + "=" * 40)
    if dry_run:
        print_info("[DRY RUN MODE - no changes will be made]")

    # Prerequisites
    import ghtraf.hints  # noqa: F401 — register domain hints
    out = get_output()
    out.set_channel_fd('setup', sys.stdout)  # setup is user-facing in create
    print_info("\nChecking prerequisites...")
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
        print_warn("Your gh CLI token may not have 'gist' scope.\n"
                   "  Run: gh auth refresh -s gist")
        if not args.non_interactive:
            resp = input("  Continue anyway? (y/N): ").strip().lower()
            if resp != "y":
                sys.exit(1)
    else:
        print_ok("Token has gist access")

    gh_username = gh.resolve_github_username()
    print_ok(f"GitHub username: {gh_username}")

    # Configuration
    print_info("\nGathering configuration...")
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

    ci_display = (', '.join(config['ci_workflows'])
                   if config['ci_workflows'] else '(none)')
    will_configure = 'yes' if args.configure_files else 'no'
    print_info( f"\n"
                f"  Owner:        {config['owner']}\n"
                f"  Repository:   {config['repo']}\n"
                f"  Created:      {config['created']}\n"
                f"  Display Name: {config['display_name']}\n"
                f"  CI Workflows: {ci_display}\n"
                f"  Configure:    {will_configure}"
    )

    if not args.non_interactive and not dry_run:
        print_info("")
        resp = input("  Proceed? (Y/n): ").strip().lower()
        if resp == "n":
            print_info("  Setup cancelled.")
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
            print_info(f"  Run manually: gh variable set TRAFFIC_GIST_ID "
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
            print_info(f"  Run manually: gh variable set TRAFFIC_ARCHIVE_GIST_ID "
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
    print_banner("\n" + "=" * 40)
    if dry_run:
        print_info("Dry run complete! Re-run without --dry-run to apply.")
    else:
        print_info("Setup complete!")
        out.hint('config.remember', 'result')

    gist_base = (f"https://gist.githubusercontent.com/"
                 f"{gh_username}/{badge_gist_id}/raw")
    shield_base = "https://img.shields.io/endpoint?url=" + gist_base
    owner_lower = config["owner"].lower()
    stats_url = f"https://{owner_lower}.github.io/{config['repo']}/stats/"

    print_info( f"\n"
                f"  Badge Gist ID:   {badge_gist_id}\n"
                f"  Archive Gist ID: {archive_gist_id}\n"
                f"\n"
                f"Badge URLs:\n"
                f"  Installs:  {shield_base}/installs.json\n"
                f"  Downloads: {shield_base}/downloads.json\n"
                f"  Clones:    {shield_base}/clones.json\n"
                f"  Views:     {shield_base}/views.json\n"
                f"\n"
                f"Badge Markdown (copy-paste for README):\n"
                f"  [![Installs]({shield_base}/installs.json)]({stats_url}#installs)"
    )

    print_info("\nNext steps:")
    if args.skip_variables:
        print_info(
                    f"  1. Set repo variables:\n"
                    f"     gh variable set TRAFFIC_GIST_ID "
                    f"--body \"{badge_gist_id}\" -R {config['gh_repo']}\n"
                    f"     gh variable set TRAFFIC_ARCHIVE_GIST_ID "
                    f"--body \"{archive_gist_id}\" -R {config['gh_repo']}\n"
                    f"  2. Set repo secret with a PAT (gist scope):\n"
                    f"     gh secret set {config['gist_token_name']} "
                    f"-R {config['gh_repo']}"
        )
    if not args.configure_files:
        print_info("  - Run again with --configure to update dashboard/workflow files")
        out.hint('setup.configure', 'result')
    print_info(
                f"  - Commit and push your changes\n"
                f"  - Enable GitHub Pages (Settings > Pages > Deploy from branch "
                f"> main, /docs)\n"
                f"  - Trigger the workflow manually or wait for the 3am UTC schedule:\n"
                f"    gh workflow run \"Track Downloads & Clones\" "
                f"-R {config['gh_repo']}\n"
    )

    return 0
