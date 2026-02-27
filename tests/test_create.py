"""Tests for ghtraf.commands.create — the create subcommand.

These tests use the mock_gh fixture from conftest.py to avoid
real GitHub API calls. They exercise the full command flow
via ghtraf.cli.main().
"""

from datetime import date

import pytest

from ghtraf.cli import main


class TestCreateDryRun:
    """Test ghtraf create with --dry-run flag."""

    def test_dry_run_full_flow(self, mock_gh, capsys):
        """Full dry-run should exercise all steps without API calls."""
        result = main([
            "create",
            "--dry-run",
            "--non-interactive",
            "--owner", "testorg",
            "--repo", "testrepo",
            "--created", "2026-01-01",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
        assert "testorg" in captured.out
        assert "testrepo" in captured.out

    def test_dry_run_with_configure(self, mock_gh, tmp_repo, capsys):
        """--configure should attempt file updates in dry-run."""
        result = main([
            "create",
            "--dry-run",
            "--non-interactive",
            "--owner", "testorg",
            "--repo", "testrepo",
            "--created", "2026-01-01",
            "--configure",
            "--repo-dir", str(tmp_repo),
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "Configure project files" in captured.out


class TestCreateConfigure:
    """Test --configure with actual placeholder files."""

    def test_configure_replaces_placeholders(
        self, mock_gh, tmp_repo,
        sample_dashboard_html, sample_dashboard_readme,
        sample_workflow_yml, capsys,
    ):
        """Full create --configure should replace placeholders in all files."""
        result = main([
            "create",
            "--dry-run",
            "--non-interactive",
            "--owner", "myorg",
            "--repo", "myproject",
            "--created", "2026-06-15",
            "--configure",
            "--repo-dir", str(tmp_repo),
        ])
        assert result == 0

        # Dry-run: files should NOT be modified
        html = sample_dashboard_html.read_text()
        assert "= 'OWNER'" in html  # placeholders still present
        assert "myorg" not in html

    def test_configure_writes_files_without_dry_run(
        self, mock_gh, tmp_repo, tmp_config_home,
        sample_dashboard_html, sample_dashboard_readme,
        sample_workflow_yml, capsys,
    ):
        """Without --dry-run, --configure should actually write files."""
        result = main([
            "create",
            "--non-interactive",
            "--owner", "myorg",
            "--repo", "myproject",
            "--created", "2026-06-15",
            "--configure",
            "--repo-dir", str(tmp_repo),
        ])
        assert result == 0

        # Dashboard HTML should have real values
        html = sample_dashboard_html.read_text()
        assert "myorg" in html
        assert "myproject" in html
        assert "2026-06-15" in html
        assert "= 'OWNER'" not in html  # placeholder value replaced

        # README should have real values
        readme = sample_dashboard_readme.read_text()
        assert "myorg" in readme

        # Workflow should have updated version
        workflow = sample_workflow_yml.read_text()
        assert "0.1.0" in workflow

    def test_configure_creates_project_config(
        self, mock_gh, tmp_repo, tmp_config_home, capsys,
    ):
        """Without --dry-run, should write .ghtraf.json to repo dir."""
        result = main([
            "create",
            "--non-interactive",
            "--owner", "myorg",
            "--repo", "myproject",
            "--created", "2026-06-15",
            "--repo-dir", str(tmp_repo),
        ])
        assert result == 0

        import json
        config_file = tmp_repo / ".ghtraf.json"
        assert config_file.exists()
        config = json.loads(config_file.read_text())
        assert config["owner"] == "myorg"
        assert config["repo"] == "myproject"
        assert config["created"] == "2026-06-15"
        assert "badge_gist_id" in config
        assert "archive_gist_id" in config


class TestCreateValidation:
    """Test input validation for the create command."""

    def test_requires_owner_non_interactive(self, mock_gh):
        """--non-interactive without --owner should fail."""
        # _gather_config calls sys.exit(1) when owner missing
        result = main([
            "create",
            "--non-interactive",
            "--repo", "testrepo",
            "--created", "2026-01-01",
        ])
        assert result == 1

    def test_requires_repo_non_interactive(self, mock_gh):
        """--non-interactive without --repo should fail."""
        result = main([
            "create",
            "--non-interactive",
            "--owner", "testorg",
            "--created", "2026-01-01",
        ])
        assert result == 1

    def test_bad_date_format_fails(self, mock_gh):
        """Invalid date format should fail."""
        result = main([
            "create",
            "--non-interactive",
            "--owner", "testorg",
            "--repo", "testrepo",
            "--created", "not-a-date",
        ])
        assert result == 1

    def test_created_auto_detects_from_api(self, mock_gh, capsys):
        """Omitting --created should auto-detect from repo API."""
        # mock_gh's get_repo_created_date returns "2026-01-01"
        result = main([
            "create",
            "--dry-run",
            "--non-interactive",
            "--owner", "testorg",
            "--repo", "testrepo",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "2026-01-01" in captured.out

    def test_created_defaults_to_today_when_no_repo(self, mock_gh, capsys,
                                                     monkeypatch):
        """When repo doesn't exist and --created omitted, default to today."""
        import ghtraf.gh as gh_mod
        monkeypatch.setattr(gh_mod, "get_repo_created_date", lambda _: None)
        result = main([
            "create",
            "--dry-run",
            "--non-interactive",
            "--owner", "testorg",
            "--repo", "testrepo",
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert date.today().isoformat() in captured.out


class TestCreateSkipVariables:
    """Test --skip-variables flag."""

    def test_skip_variables_skips_repo_setup(self, mock_gh, capsys):
        """--skip-variables should skip variable/secret steps."""
        result = main([
            "create",
            "--dry-run",
            "--non-interactive",
            "--skip-variables",
            "--owner", "testorg",
            "--repo", "testrepo",
            "--created", "2026-01-01",
        ])
        assert result == 0
        captured = capsys.readouterr()
        # Should NOT contain the "Set repository variables" step header
        assert "Set repository variables" not in captured.out
        # But Next Steps should remind user to set them manually
        assert "gh variable set TRAFFIC_GIST_ID" in captured.out
        # Should still have gist creation steps
        assert "badge gist" in captured.out.lower()
        # No actual variable-setting calls should have been made
        assert len(mock_gh["variables_set"]) == 0
