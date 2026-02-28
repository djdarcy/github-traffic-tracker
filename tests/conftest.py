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
