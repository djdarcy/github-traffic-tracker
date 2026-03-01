"""Shared test fixtures for ghtraf test suite."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_DATA_DIR = PROJECT_ROOT / "tests" / "test-data"
REPOS_DIR = TEST_DATA_DIR / "repos"
TEST_RUNS_DIR = PROJECT_ROOT / "tests" / "test-runs"
LEGACY_TEST_DATA_DIR = PROJECT_ROOT / "tests" / "one-offs" / "test_dashboard_data"


# ---------------------------------------------------------------------------
# Temporary directory fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_config_home(tmp_path):
    """Provide a temporary home directory for ~/.ghtraf/config.json."""
    home = tmp_path / "home"
    home.mkdir()
    with patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
        with patch("pathlib.Path.home", return_value=home):
            yield home


@pytest.fixture
def tmp_repo(tmp_path):
    """Provide a temporary repo directory with basic structure."""
    repo = tmp_path / "myrepo"
    repo.mkdir()
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / "docs" / "stats").mkdir(parents=True)
    return repo


# ---------------------------------------------------------------------------
# Sample file fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_dashboard_html(tmp_repo):
    """Copy the dashboard template into tmp_repo for configure tests."""
    src = TEST_DATA_DIR / "dashboard-template.html"
    dest = tmp_repo / "docs" / "stats" / "index.html"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


@pytest.fixture
def sample_dashboard_readme(tmp_repo):
    """Copy the dashboard README template into tmp_repo for configure tests."""
    src = TEST_DATA_DIR / "dashboard-readme-template.md"
    dest = tmp_repo / "docs" / "stats" / "README.md"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


@pytest.fixture
def sample_workflow_yml(tmp_repo):
    """Copy the workflow template into tmp_repo for configure tests."""
    src = TEST_DATA_DIR / "workflow-template.yml"
    dest = tmp_repo / ".github" / "workflows" / "traffic-badges.yml"
    dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_project_config(tmp_repo):
    """Write a .ghtraf.json file in the tmp repo."""
    config = {
        "owner": "testorg",
        "repo": "testrepo",
        "created": "2026-01-15",
        "display_name": "Test Repo",
        "badge_gist_id": "abc123",
        "archive_gist_id": "def456",
        "dashboard_dir": "docs/stats",
        "schema_version": 1,
    }
    path = tmp_repo / ".ghtraf.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path, config


@pytest.fixture
def sample_global_config(tmp_config_home):
    """Write a global config file in the tmp home."""
    config_dir = tmp_config_home / ".ghtraf"
    config_dir.mkdir()
    config = {
        "version": 1,
        "repos": {
            "globalorg/globalrepo": {
                "badge_gist_id": "global111",
                "archive_gist_id": "global222",
                "repo_dir": "/some/path",
                "display_name": "Global Repo",
            }
        }
    }
    path = config_dir / "config.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path, config


# ---------------------------------------------------------------------------
# Real-repo fixtures (snapshot-based integration tests)
# ---------------------------------------------------------------------------
@pytest.fixture
def papers_repo(tmp_path):
    """Copy the Way-of-Scarcity/papers snapshot into a temporary directory.

    Returns a tmp_path copy that tests can freely modify (run init against,
    add .git, etc.) without touching the committed fixture.

    Source: https://github.com/Way-of-Scarcity/papers
    See tests/test-data/repos/papers/SOURCE.md for details.
    """
    import shutil

    src = REPOS_DIR / "papers"
    dest = tmp_path / "papers"
    shutil.copytree(src, dest)
    return dest


# ---------------------------------------------------------------------------
# Integration test fixtures (persistent output in test-runs/)
# ---------------------------------------------------------------------------
def _force_rmtree(path):
    """Remove a directory tree, handling Windows read-only files.

    Git pack files (.idx, .pack) are marked read-only on Windows,
    causing shutil.rmtree to fail with PermissionError. This handler
    clears the read-only flag before retrying the delete.
    """
    import shutil
    import stat

    def _on_error(func, fpath, exc_info):
        os.chmod(fpath, stat.S_IWRITE)
        func(fpath)

    shutil.rmtree(path, onexc=_on_error)


@pytest.fixture
def integration_output():
    """Provide a persistent output directory in tests/test-runs/.

    Unlike tmp_path, this directory survives across test runs so the
    user can browse results in their file explorer. Each test gets a
    named subdirectory. Cleans the subdirectory at the START of the
    run (so stale results from a previous run don't mislead), but
    leaves the results after the test finishes.
    """
    def _make_output_dir(name):
        dest = (TEST_RUNS_DIR / name).resolve()
        assert str(dest).startswith(str(TEST_RUNS_DIR.resolve())), (
            f"integration_output name {name!r} escapes test-runs/: {dest}"
        )
        if dest.exists():
            _force_rmtree(dest)
        dest.mkdir(parents=True)
        return dest

    return _make_output_dir


@pytest.fixture(scope="class")
def live_papers_repo():
    """Clone Way-of-Scarcity/papers from GitHub into test-runs/.

    This fixture requires network access and is only used by tests
    marked with @pytest.mark.integration. The clone is shallow
    (--depth 1) to minimize download size.

    Scoped to class so the clone happens once for all tests in
    TestInitLiveRepo. Results are retained in test-runs/papers-live/
    for manual inspection after the test run.
    """
    import subprocess

    dest = TEST_RUNS_DIR / "papers-live"
    if dest.exists():
        _force_rmtree(dest)
    dest.mkdir(parents=True)

    result = subprocess.run(
        ["git", "clone", "--depth", "1",
         "https://github.com/Way-of-Scarcity/papers.git",
         str(dest)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        pytest.skip(f"Could not clone papers repo: {result.stderr.strip()}")

    return dest


# ---------------------------------------------------------------------------
# Mock gh CLI fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_gh(monkeypatch):
    """Mock the gh module functions to avoid real API calls.

    Returns a dict of call records for assertion.
    """
    calls = {"run_gh": [], "variables_set": [], "secrets_set": []}

    def fake_check_gh_installed():
        return "gh version 2.78.0 (mock)"

    def fake_check_gh_authenticated():
        return "Logged in to github.com account testuser (mock)"

    def fake_check_gh_scopes(auth_output):
        return True

    def fake_resolve_github_username():
        return "testuser"

    def fake_run_gh(args, input_data=None, check=True):
        calls["run_gh"].append({"args": args, "input_data": input_data})
        # Fake gist creation response
        if "gists" in args and "--method" in args and "POST" in args:
            return json.dumps({
                "id": "fake_gist_id_" + str(len(calls["run_gh"])),
                "html_url": "https://gist.github.com/testuser/fake",
            })
        return ""

    def fake_set_repo_variable(name, value, gh_repo, dry_run=False):
        calls["variables_set"].append({
            "name": name, "value": value,
            "gh_repo": gh_repo, "dry_run": dry_run,
        })
        return True

    def fake_set_repo_secret(name, value, gh_repo):
        calls["secrets_set"].append({
            "name": name, "gh_repo": gh_repo,
        })
        return True

    def fake_check_repo_exists(gh_repo):
        return gh_repo  # pretend it exists

    def fake_get_repo_created_date(gh_repo):
        return "2026-01-01"

    import ghtraf.gh as gh_mod
    import ghtraf.gist as gist_mod
    monkeypatch.setattr(gh_mod, "check_gh_installed", fake_check_gh_installed)
    monkeypatch.setattr(gh_mod, "check_gh_authenticated", fake_check_gh_authenticated)
    monkeypatch.setattr(gh_mod, "check_gh_scopes", fake_check_gh_scopes)
    monkeypatch.setattr(gh_mod, "resolve_github_username", fake_resolve_github_username)
    monkeypatch.setattr(gh_mod, "run_gh", fake_run_gh)
    monkeypatch.setattr(gh_mod, "set_repo_variable", fake_set_repo_variable)
    monkeypatch.setattr(gh_mod, "set_repo_secret", fake_set_repo_secret)
    monkeypatch.setattr(gh_mod, "check_repo_exists", fake_check_repo_exists)
    monkeypatch.setattr(gh_mod, "get_repo_created_date", fake_get_repo_created_date)
    # Also patch the already-imported binding in gist.py — since gist.py uses
    # `from ghtraf.gh import run_gh`, its local name still points to the real
    # function unless we patch gist_mod.run_gh directly.
    monkeypatch.setattr(gist_mod, "run_gh", fake_run_gh)

    return calls
