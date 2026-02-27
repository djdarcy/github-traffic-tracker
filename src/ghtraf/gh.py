"""GitHub CLI (gh) wrapper utilities.

Provides authenticated access to the GitHub API via the gh CLI tool.
All ghtraf operations that touch GitHub go through this module.
"""

import shutil
import subprocess
import sys


def run_gh(args, input_data=None, check=True):
    """Run a gh CLI command, return stdout.

    Args:
        args: List of arguments to pass to gh.
        input_data: Optional string to pipe to stdin.
        check: If True (default), exit on failure.

    Returns:
        Stripped stdout string.

    Raises:
        SystemExit: If check=True and the command fails.
    """
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True, text=True, encoding="utf-8",
        input=input_data
    )
    if check and result.returncode != 0:
        print(f"  ERROR: gh {' '.join(args[:3])}...", file=sys.stderr)
        print(f"  {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def check_gh_installed():
    """Verify gh CLI exists on PATH.

    Returns:
        Version string if found.

    Raises:
        SystemExit: If gh is not installed.
    """
    if shutil.which("gh") is None:
        print("ERROR: gh CLI not found.")
        print()
        print("  Install it from: https://cli.github.com")
        print("  Or via package manager:")
        print("    Windows:  winget install GitHub.cli")
        print("    macOS:    brew install gh")
        print("    Linux:    See https://github.com/cli/cli/blob/trunk/docs/install_linux.md")
        sys.exit(1)

    version = subprocess.run(
        ["gh", "--version"], capture_output=True, text=True, encoding="utf-8"
    ).stdout.strip().split("\n")[0]
    return version


def check_gh_authenticated():
    """Verify gh auth status.

    Returns:
        Raw auth output string (for scope checking).

    Raises:
        SystemExit: If not authenticated.
    """
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True, text=True, encoding="utf-8"
    )
    output = result.stdout + result.stderr
    if result.returncode != 0:
        print("ERROR: Not authenticated with GitHub CLI.")
        print()
        print("  Run: gh auth login")
        print("  Then re-run this command.")
        sys.exit(1)
    return output


def check_gh_scopes(auth_output):
    """Check if the gh token has gist scope.

    Returns:
        True if gist scope is available.
    """
    result = subprocess.run(
        ["gh", "api", "gists", "--method", "GET", "-q", ".[0].id"],
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0 and "403" in result.stderr:
        return False
    return True


def resolve_github_username():
    """Get the authenticated user's GitHub username."""
    return run_gh(["api", "user", "--jq", ".login"])


def set_repo_variable(name, value, gh_repo, dry_run=False):
    """Set a GitHub repository variable.

    Args:
        name: Variable name.
        value: Variable value.
        gh_repo: Repository in owner/repo format.
        dry_run: If True, only print what would happen.

    Returns:
        True if successful (or dry run), False on failure.
    """
    if dry_run:
        return True

    result = subprocess.run(
        ["gh", "variable", "set", name, "--body", value, "-R", gh_repo],
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        return False
    return True


def set_repo_secret(name, value, gh_repo):
    """Set a GitHub repository secret.

    Args:
        name: Secret name.
        value: Secret value.
        gh_repo: Repository in owner/repo format.

    Returns:
        True if successful, False on failure.
    """
    result = subprocess.run(
        ["gh", "secret", "set", name, "-R", gh_repo],
        capture_output=True, text=True, encoding="utf-8",
        input=value
    )
    return result.returncode == 0


def check_repo_exists(gh_repo):
    """Check if a repository exists on GitHub.

    Returns:
        The repo full_name if it exists, None otherwise.
    """
    result = subprocess.run(
        ["gh", "api", f"repos/{gh_repo}", "--jq", ".full_name"],
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def get_repo_created_date(gh_repo):
    """Get the creation date of a repository.

    Returns:
        Date string (YYYY-MM-DD) or None.
    """
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{gh_repo}", "--jq", ".created_at"],
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode != 0:
            return None
        raw = result.stdout.strip()
        # Validate it looks like a date (YYYY-MM-DD...)
        if raw and len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
            return raw[:10]
    except Exception:
        pass
    return None
