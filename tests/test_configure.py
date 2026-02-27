"""Tests for ghtraf.configure — file configuration via regex replacement."""

from ghtraf.configure import (
    apply_replacements,
    configure_dashboard,
    configure_readme,
    configure_workflow,
)


class TestApplyReplacements:
    """Test the generic regex replacement engine."""

    def test_single_replacement(self, tmp_path):
        """Should replace a single pattern match."""
        f = tmp_path / "test.txt"
        f.write_text("Hello PLACEHOLDER world")
        replacements = [
            (r"PLACEHOLDER", "{name}", "name replacement"),
        ]
        count = apply_replacements(f, replacements, {"name": "ghtraf"})
        assert count == 1
        assert "Hello ghtraf world" in f.read_text()

    def test_multiple_replacements(self, tmp_path):
        """Should apply multiple replacements in one pass."""
        f = tmp_path / "test.txt"
        f.write_text("AAA and BBB")
        replacements = [
            (r"AAA", "{first}", "first"),
            (r"BBB", "{second}", "second"),
        ]
        count = apply_replacements(f, replacements,
                                   {"first": "111", "second": "222"})
        assert count == 2
        assert "111 and 222" in f.read_text()

    def test_no_match_returns_zero(self, tmp_path):
        """Pattern not found should skip gracefully and return 0."""
        f = tmp_path / "test.txt"
        f.write_text("nothing to match")
        replacements = [
            (r"NOTHERE", "{x}", "missing pattern"),
        ]
        count = apply_replacements(f, replacements, {"x": "y"})
        assert count == 0
        assert f.read_text() == "nothing to match"  # unchanged

    def test_dry_run_no_modification(self, tmp_path):
        """Dry run should not modify the file."""
        f = tmp_path / "test.txt"
        original = "Hello PLACEHOLDER world"
        f.write_text(original)
        replacements = [
            (r"PLACEHOLDER", "{name}", "name replacement"),
        ]
        count = apply_replacements(f, replacements, {"name": "ghtraf"},
                                   dry_run=True)
        assert count == 1  # still counts the match
        assert f.read_text() == original  # file unchanged

    def test_missing_file_returns_zero(self, tmp_path):
        """Nonexistent file should warn and return 0."""
        count = apply_replacements(
            tmp_path / "nope.html", [], {})
        assert count == 0

    def test_partial_matches(self, tmp_path):
        """Should count only matching patterns, not total patterns."""
        f = tmp_path / "test.txt"
        f.write_text("AAA stays but BBB is missing")
        replacements = [
            (r"AAA", "{x}", "first"),
            (r"CCC", "{y}", "second"),  # won't match
        ]
        count = apply_replacements(f, replacements, {"x": "111", "y": "222"})
        assert count == 1
        content = f.read_text()
        assert "111" in content
        assert "222" not in content  # CCC never matched


class TestConfigureDashboard:
    """Test dashboard HTML configuration."""

    def test_all_fields_replaced(self, sample_dashboard_html):
        """Should replace all placeholder values in dashboard HTML."""
        config = {
            "owner": "myorg",
            "repo": "myrepo",
            "display_name_html": "My Repo",
            "gh_username": "myuser",
            "badge_gist_id": "abc123",
            "archive_gist_id": "def456",
            "created": "2026-06-15",
        }
        count = configure_dashboard(config, sample_dashboard_html)
        content = sample_dashboard_html.read_text()

        assert "myorg" in content
        assert "myrepo" in content
        assert "abc123" in content
        assert "def456" in content
        assert "2026-06-15" in content
        assert count >= 5  # at least 5 successful replacements

    def test_dry_run_preserves_file(self, sample_dashboard_html):
        """Dry run should not modify the dashboard file."""
        original = sample_dashboard_html.read_text()
        config = {
            "owner": "x", "repo": "y", "display_name_html": "Z",
            "gh_username": "u", "badge_gist_id": "g",
            "archive_gist_id": "a", "created": "2026-01-01",
        }
        configure_dashboard(config, sample_dashboard_html, dry_run=True)
        assert sample_dashboard_html.read_text() == original


class TestConfigureWorkflow:
    """Test workflow YAML configuration."""

    def test_ci_workflows_set(self, sample_workflow_yml):
        """Should update workflow_run trigger with CI workflow names."""
        config = {"ci_workflows": ["Build", "Test"]}
        count = configure_workflow(config, sample_workflow_yml)
        content = sample_workflow_yml.read_text()
        assert '["Build", "Test"]' in content
        assert count >= 1

    def test_no_ci_workflows_comments_out(self, sample_workflow_yml):
        """Should comment out workflow_run when no CI workflows given."""
        config = {"ci_workflows": []}
        count = configure_workflow(config, sample_workflow_yml)
        content = sample_workflow_yml.read_text()
        assert "# workflow_run:" in content
        assert count >= 1

    def test_missing_workflow_file(self, tmp_path):
        """Should handle missing workflow file gracefully."""
        config = {"ci_workflows": ["CI"]}
        count = configure_workflow(config, tmp_path / "nope.yml")
        assert count == 0


class TestConfigureReadme:
    """Test dashboard README.md configuration."""

    def test_all_fields_replaced(self, sample_dashboard_readme):
        """Should replace project link, badge gist link, and dashboard URL."""
        config = {
            "owner": "myorg",
            "repo": "myrepo",
            "display_name": "My Repo",
            "gh_username": "myuser",
            "badge_gist_id": "abc123",
        }
        count = configure_readme(config, sample_dashboard_readme)
        content = sample_dashboard_readme.read_text()

        assert "myorg" in content
        assert "myrepo" in content
        assert "abc123" in content
        assert "myuser" in content
        assert count >= 2  # at least project link + badge gist link

    def test_owner_lowercased_in_dashboard_url(self, sample_dashboard_readme):
        """Dashboard URL should use lowercase owner for GitHub Pages."""
        config = {
            "owner": "MyOrg",
            "repo": "myrepo",
            "display_name": "My Repo",
            "gh_username": "myuser",
            "badge_gist_id": "abc123",
        }
        configure_readme(config, sample_dashboard_readme)
        content = sample_dashboard_readme.read_text()
        assert "myorg.github.io" in content  # lowercase
        assert "MyOrg.github.io" not in content

    def test_dry_run_preserves_file(self, sample_dashboard_readme):
        """Dry run should not modify the README file."""
        original = sample_dashboard_readme.read_text()
        config = {
            "owner": "x", "repo": "y", "display_name": "Z",
            "gh_username": "u", "badge_gist_id": "g",
        }
        configure_readme(config, sample_dashboard_readme, dry_run=True)
        assert sample_dashboard_readme.read_text() == original

    def test_missing_readme_file(self, tmp_path):
        """Should handle missing README file gracefully."""
        config = {
            "owner": "x", "repo": "y", "display_name": "Z",
            "gh_username": "u", "badge_gist_id": "g",
        }
        count = configure_readme(config, tmp_path / "nope.md")
        assert count == 0

    def test_does_not_mutate_caller_config(self, sample_dashboard_readme):
        """configure_readme copies config — should not add owner_lower to caller's dict."""
        config = {
            "owner": "MyOrg",
            "repo": "myrepo",
            "display_name": "My Repo",
            "gh_username": "myuser",
            "badge_gist_id": "abc123",
        }
        configure_readme(config, sample_dashboard_readme)
        assert "owner_lower" not in config  # internal key not leaked
