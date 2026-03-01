"""ghtraf init — copy workflow and dashboard templates into target repo.

Copies package-embedded template files from src/ghtraf/templates/ to the
target repository directory. This is the local file setup step that
prepares the directory structure before ``ghtraf create`` handles the
cloud-side configuration (gists, variables, secrets).

Templates copied::

    .github/workflows/traffic-badges.yml
    docs/stats/index.html
    docs/stats/README.md
    docs/stats/favicon.svg
"""

import shutil
import sys
from importlib.resources import as_file, files
from pathlib import Path

from ghtraf.config import find_project_config
from ghtraf.lib.log_lib import get_output
from ghtraf.output import (
    print_dry, print_ok, print_skip, print_step, print_warn,
)


# Template files relative to the templates root.
TEMPLATE_FILES = [
    Path(".github") / "workflows" / "traffic-badges.yml",
    Path("docs") / "stats" / "index.html",
    Path("docs") / "stats" / "README.md",
    Path("docs") / "stats" / "favicon.svg",
]


def register(subparsers, parents):
    """Register the 'init' subcommand."""
    p = subparsers.add_parser(
        "init",
        parents=parents,
        help="Copy template files into the target repository",
        description=(
            "Copy the workflow and dashboard template files from the ghtraf\n"
            "package into your repository directory. Run this before\n"
            "'ghtraf create --configure' to set up the local file structure."
        ),
        formatter_class=__import__("argparse").RawDescriptionHelpFormatter,
    )

    overwrite = p.add_mutually_exclusive_group()
    overwrite.add_argument(
        "--force", action="store_true", default=False,
        help="Overwrite existing files without prompting",
    )
    overwrite.add_argument(
        "--skip-existing", action="store_true", default=False,
        help="Skip files that already exist (only copy new ones)",
    )

    p.set_defaults(func=run)


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
                    print(f"\n  No .ghtraf.json found in current directory.")
                    print(f"  Found git repository at: {current}")
                    response = input(
                        "  Use this directory? [Y/n]: "
                    ).strip().lower()
                    if response in ('n', 'no'):
                        print(f"  Using current directory instead: {cwd}")
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
        print("  Please enter y, n, or a.")


def run(args):
    """Execute the init command."""
    dry_run = args.dry_run
    force = args.force
    skip_existing = args.skip_existing
    non_interactive = args.non_interactive
    out = get_output()

    # Discover target directory
    repo_dir = _discover_repo_dir(args)
    out.emit(1, "  [setup] Target directory: {d}", channel='setup', d=repo_dir)

    print()
    print("ghtraf init — Copy template files")
    print("=" * 40)
    if dry_run:
        print("[DRY RUN MODE — no files will be written]")
    print(f"  Target: {repo_dir}")
    print()

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
    print()
    if dry_run:
        print(f"  Would copy {copied} file(s), skip {skipped} file(s).")
    else:
        print(f"  Copied {copied} file(s), skipped {skipped} file(s).")

    if copied > 0 and not dry_run:
        import ghtraf.hints  # noqa: F401
        out.hint('setup.configure', 'result')
        print()
        print("  Next: Run 'ghtraf create --configure' to fill in project values.")

    print()
    return 0
