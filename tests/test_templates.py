"""Tests for package-embedded templates (Issue #27).

Verifies that template files:
- Exist in the expected directory structure
- Contain placeholder tokens (not GTT-specific values)
- Include bug fixes (organic formula, beginAtZero)
- Round-trip through configure.py without leftover placeholders
"""

import re
import shutil
from importlib.resources import files
from pathlib import Path

import pytest

from ghtraf.configure import configure_dashboard, configure_readme, configure_workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
TEMPLATES_ROOT = files("ghtraf") / "templates"

# Placeholder tokens that must be present in templates
DASHBOARD_PLACEHOLDERS = ["PLACEHOLDER", "OWNER", "REPO", "USER", "GISTID",
                          "ARCHIVEID"]
README_PLACEHOLDERS = ["PLACEHOLDER", "OWNER", "REPO", "USER", "GISTID"]

# GTT-specific values that must NOT be present in templates
GTT_SPECIFIC = ["djdarcy", "fffb1b8632243b40ad183a161ff0f32e",
                "e5b433950e400fb713109a90ab49a2f7",
                "github-traffic-tracker"]


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------
class TestTemplateStructure:
    """Template directory has the expected files."""

    def test_dashboard_exists(self):
        assert (TEMPLATES_ROOT / "docs" / "stats" / "index.html").is_file()

    def test_readme_exists(self):
        assert (TEMPLATES_ROOT / "docs" / "stats" / "README.md").is_file()

    def test_workflow_exists(self):
        wf = TEMPLATES_ROOT / ".github" / "workflows" / "traffic-badges.yml"
        assert wf.is_file()

    def test_favicon_exists(self):
        assert (TEMPLATES_ROOT / "docs" / "stats" / "favicon.svg").is_file()

    def test_exactly_four_template_files(self):
        """No stray files in the template tree."""
        all_files = []
        for item in _walk_traversable(TEMPLATES_ROOT):
            if item.is_file():
                all_files.append(item.name)
        assert len(all_files) == 4


# ---------------------------------------------------------------------------
# Placeholder content tests
# ---------------------------------------------------------------------------
class TestDashboardPlaceholders:
    """Template dashboard contains placeholder tokens, not real values."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = (TEMPLATES_ROOT / "docs" / "stats" / "index.html").read_text(
            encoding="utf-8"
        )

    @pytest.mark.parametrize("token", DASHBOARD_PLACEHOLDERS)
    def test_placeholder_present(self, token):
        assert token in self.content, f"Missing placeholder: {token}"

    @pytest.mark.parametrize("value", GTT_SPECIFIC)
    def test_no_gtt_specific_value(self, value):
        assert value not in self.content, f"GTT-specific value found: {value}"


class TestReadmePlaceholders:
    """Template README contains placeholder tokens, not real values."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = (TEMPLATES_ROOT / "docs" / "stats" / "README.md").read_text(
            encoding="utf-8"
        )

    @pytest.mark.parametrize("token", README_PLACEHOLDERS)
    def test_placeholder_present(self, token):
        assert token in self.content, f"Missing placeholder: {token}"

    @pytest.mark.parametrize("value", GTT_SPECIFIC)
    def test_no_gtt_specific_value(self, value):
        assert value not in self.content, f"GTT-specific value found: {value}"


class TestWorkflowTemplate:
    """Template workflow is generic (no GTT-specific values)."""

    @pytest.fixture(autouse=True)
    def _load(self):
        wf = TEMPLATES_ROOT / ".github" / "workflows" / "traffic-badges.yml"
        self.content = wf.read_text(encoding="utf-8")

    def test_workflow_run_commented_out(self):
        assert "# workflow_run:" in self.content

    @pytest.mark.parametrize("value", GTT_SPECIFIC)
    def test_no_gtt_specific_value(self, value):
        assert value not in self.content, f"GTT-specific value found: {value}"


# ---------------------------------------------------------------------------
# Bug-fix regression tests
# ---------------------------------------------------------------------------
class TestDashboardBugFixes:
    """Template includes fixes from v0.2.6."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.content = (TEMPLATES_ROOT / "docs" / "stats" / "index.html").read_text(
            encoding="utf-8"
        )

    def test_organic_formula_uses_field(self):
        """Should use state.totalOrganicClones, not inline subtraction."""
        assert "state.totalOrganicClones" in self.content
        # The old inline formula should not appear
        assert "totalClones || 0) - (state.totalCiCheckouts" not in self.content

    def test_no_begin_at_zero_false(self):
        """All y-axes should start at zero."""
        assert "beginAtZero: false" not in self.content


# ---------------------------------------------------------------------------
# pyproject.toml glob test
# ---------------------------------------------------------------------------
class TestPackageConfig:
    """pyproject.toml includes templates with recursive glob."""

    def test_recursive_glob(self):
        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        content = pyproject.read_text(encoding="utf-8")
        assert 'templates/**/*' in content


# ---------------------------------------------------------------------------
# Round-trip: template → configure → verify no placeholders remain
# ---------------------------------------------------------------------------
class TestConfigureRoundTrip:
    """Copy templates to tmp dir, run configure functions, verify clean output."""

    @pytest.fixture
    def configured_repo(self, tmp_path):
        """Copy all templates into a tmp repo and run all configure functions."""
        repo = tmp_path / "myrepo"
        repo.mkdir()

        # Copy template files into repo structure
        dst_wf = repo / ".github" / "workflows"
        dst_wf.mkdir(parents=True)
        dst_dash = repo / "docs" / "stats"
        dst_dash.mkdir(parents=True)

        src_wf = TEMPLATES_ROOT / ".github" / "workflows" / "traffic-badges.yml"
        src_dash = TEMPLATES_ROOT / "docs" / "stats" / "index.html"
        src_readme = TEMPLATES_ROOT / "docs" / "stats" / "README.md"

        (dst_wf / "traffic-badges.yml").write_text(
            src_wf.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (dst_dash / "index.html").write_text(
            src_dash.read_text(encoding="utf-8"), encoding="utf-8"
        )
        (dst_dash / "README.md").write_text(
            src_readme.read_text(encoding="utf-8"), encoding="utf-8"
        )

        # Configure with test values
        dash_config = {
            "owner": "testorg",
            "repo": "testrepo",
            "display_name_html": "Test Repo",
            "gh_username": "testuser",
            "badge_gist_id": "aaa111bbb222ccc333ddd444eee555ff",
            "archive_gist_id": "fff555eee444ddd333ccc222bbb111aa",
            "created": "2025-06-15",
        }
        readme_config = {
            "owner": "testorg",
            "repo": "testrepo",
            "display_name": "Test Repo",
            "gh_username": "testuser",
            "badge_gist_id": "aaa111bbb222ccc333ddd444eee555ff",
        }
        wf_config = {"ci_workflows": ["Tests", "Lint"]}

        d_count = configure_dashboard(dash_config, dst_dash / "index.html")
        r_count = configure_readme(readme_config, dst_dash / "README.md")
        w_count = configure_workflow(wf_config, dst_wf / "traffic-badges.yml")

        return repo, d_count, r_count, w_count

    def test_dashboard_replacements_count(self, configured_repo):
        _, d_count, _, _ = configured_repo
        assert d_count >= 8, f"Expected >=8 dashboard replacements, got {d_count}"

    def test_readme_replacements_count(self, configured_repo):
        _, _, r_count, _ = configured_repo
        assert r_count >= 2, f"Expected >=2 readme replacements, got {r_count}"

    def test_workflow_replacements_count(self, configured_repo):
        _, _, _, w_count = configured_repo
        assert w_count >= 1, f"Expected >=1 workflow replacements, got {w_count}"

    def test_no_placeholders_remain_in_dashboard(self, configured_repo):
        repo, _, _, _ = configured_repo
        content = (repo / "docs" / "stats" / "index.html").read_text(encoding="utf-8")
        for token in ["PLACEHOLDER", "USER/GISTID", "ARCHIVEID",
                       "'OWNER'", "'REPO'"]:
            assert token not in content, f"Placeholder not replaced: {token}"

    def test_no_placeholders_remain_in_readme(self, configured_repo):
        repo, _, _, _ = configured_repo
        content = (repo / "docs" / "stats" / "README.md").read_text(encoding="utf-8")
        for token in ["PLACEHOLDER", "USER/GISTID"]:
            assert token not in content, f"Placeholder not replaced: {token}"

    def test_configured_values_present_in_dashboard(self, configured_repo):
        repo, _, _, _ = configured_repo
        content = (repo / "docs" / "stats" / "index.html").read_text(encoding="utf-8")
        assert "testorg" in content
        assert "testrepo" in content
        assert "aaa111bbb222ccc333ddd444eee555ff" in content
        assert "2025-06-15" in content

    def test_configured_values_present_in_readme(self, configured_repo):
        repo, _, _, _ = configured_repo
        content = (repo / "docs" / "stats" / "README.md").read_text(encoding="utf-8")
        assert "testorg" in content
        assert "testrepo" in content

    def test_workflow_has_ci_names(self, configured_repo):
        repo, _, _, _ = configured_repo
        content = (repo / ".github" / "workflows" / "traffic-badges.yml").read_text(
            encoding="utf-8"
        )
        assert '["Tests", "Lint"]' in content


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def _walk_traversable(root):
    """Recursively yield all items in a Traversable tree."""
    for item in root.iterdir():
        yield item
        if not item.is_file():
            yield from _walk_traversable(item)
