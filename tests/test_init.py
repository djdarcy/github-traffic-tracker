"""Tests for ghtraf.commands.init — the init subcommand.

Tests use tmp_path fixtures to avoid touching real filesystems.
Template access is via importlib.resources (the real package templates),
validating that package data is configured correctly.

The TestInitRealRepo class uses a snapshot of Way-of-Scarcity/papers
(see tests/test-data/repos/papers/SOURCE.md) to verify init works
against a real repository layout.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from ghtraf.cli import main
from ghtraf.commands.init import (
    _discover_repo_dir, TEMPLATE_FILES,
)
from ghtraf.lib.log_lib import manager as _manager_mod


@pytest.fixture(autouse=True)
def _reset_manager():
    """Reset OutputManager singleton between tests."""
    old = _manager_mod._manager
    yield
    _manager_mod._manager = old


# ---------------------------------------------------------------------------
# Template copying
# ---------------------------------------------------------------------------
class TestInitCopiesTemplates:
    """ghtraf init copies all 4 template files."""

    def test_init_copies_all_templates(self, tmp_path):
        """All 4 template files should be copied to the target dir."""
        result = main([
            "init",
            "--repo-dir", str(tmp_path),
            "--non-interactive",
        ])
        assert result == 0
        for rel in TEMPLATE_FILES:
            dest = tmp_path / rel
            assert dest.exists(), f"Missing: {rel}"

    def test_init_creates_parent_dirs(self, tmp_path):
        """init should create .github/workflows/ and docs/stats/."""
        result = main([
            "init",
            "--repo-dir", str(tmp_path),
            "--non-interactive",
        ])
        assert result == 0
        assert (tmp_path / ".github" / "workflows").is_dir()
        assert (tmp_path / "docs" / "stats").is_dir()

    def test_copied_files_are_not_empty(self, tmp_path):
        """Copied files should have real content, not be empty."""
        main(["init", "--repo-dir", str(tmp_path), "--non-interactive"])
        for rel in TEMPLATE_FILES:
            content = (tmp_path / rel).read_text(encoding="utf-8")
            assert len(content) > 10, f"{rel} appears empty"


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------
class TestInitDryRun:
    """--dry-run should not write any files."""

    def test_dry_run_no_files_written(self, tmp_path):
        """No files should exist after --dry-run."""
        result = main([
            "init",
            "--dry-run",
            "--repo-dir", str(tmp_path),
        ])
        assert result == 0
        for rel in TEMPLATE_FILES:
            assert not (tmp_path / rel).exists(), f"File written in dry run: {rel}"

    def test_dry_run_shows_preview(self, tmp_path, capsys):
        """--dry-run output should mention what would be copied."""
        main(["init", "--dry-run", "--repo-dir", str(tmp_path)])
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
        assert "Would copy" in captured.out


# ---------------------------------------------------------------------------
# Skip existing
# ---------------------------------------------------------------------------
class TestInitSkipExisting:
    """--skip-existing skips files that already exist."""

    def test_skip_existing_preserves_file(self, tmp_path):
        """Existing files should not be overwritten."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        sentinel = wf_dir / "traffic-badges.yml"
        sentinel.write_text("ORIGINAL CONTENT", encoding="utf-8")

        result = main([
            "init",
            "--skip-existing",
            "--repo-dir", str(tmp_path),
            "--non-interactive",
        ])
        assert result == 0
        assert sentinel.read_text(encoding="utf-8") == "ORIGINAL CONTENT"

    def test_skip_existing_copies_new_files(self, tmp_path):
        """Files that don't exist should still be copied."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "traffic-badges.yml").write_text("EXISTING", encoding="utf-8")

        main([
            "init", "--skip-existing",
            "--repo-dir", str(tmp_path), "--non-interactive",
        ])

        assert (tmp_path / "docs" / "stats" / "index.html").exists()
        assert (tmp_path / "docs" / "stats" / "README.md").exists()
        assert (tmp_path / "docs" / "stats" / "favicon.svg").exists()

    def test_skip_existing_reports_skipped_count(self, tmp_path, capsys):
        """Output should report how many files were skipped."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "traffic-badges.yml").write_text("EXISTING", encoding="utf-8")

        main([
            "init", "--skip-existing",
            "--repo-dir", str(tmp_path), "--non-interactive",
        ])
        captured = capsys.readouterr()
        assert "skip" in captured.out.lower()


# ---------------------------------------------------------------------------
# Force overwrite
# ---------------------------------------------------------------------------
class TestInitForce:
    """--force overwrites without prompting."""

    def test_force_overwrites(self, tmp_path):
        """--force should overwrite existing files."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        sentinel = wf_dir / "traffic-badges.yml"
        sentinel.write_text("OLD CONTENT", encoding="utf-8")

        main([
            "init", "--force",
            "--repo-dir", str(tmp_path), "--non-interactive",
        ])

        content = sentinel.read_text(encoding="utf-8")
        assert content != "OLD CONTENT"
        assert len(content) > 50  # real template content


# ---------------------------------------------------------------------------
# Default prompt behavior
# ---------------------------------------------------------------------------
class TestInitDefaultPrompts:
    """Default behavior prompts on existing files."""

    def test_non_interactive_skips_existing(self, tmp_path):
        """--non-interactive without --force or --skip-existing skips files."""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        sentinel = wf_dir / "traffic-badges.yml"
        sentinel.write_text("EXISTING", encoding="utf-8")

        main([
            "init",
            "--repo-dir", str(tmp_path),
            "--non-interactive",
        ])

        assert sentinel.read_text(encoding="utf-8") == "EXISTING"


# ---------------------------------------------------------------------------
# Repo discovery
# ---------------------------------------------------------------------------
class TestInitRepoDiscovery:
    """Repo directory discovery priority."""

    def test_explicit_repo_dir(self, tmp_path):
        """--repo-dir takes highest priority."""
        import argparse
        args = argparse.Namespace(repo_dir=str(tmp_path))
        result = _discover_repo_dir(args)
        assert result == tmp_path.resolve()

    def test_ghtraf_json_walkup(self, tmp_path):
        """Finds .ghtraf.json walking upward."""
        import argparse
        (tmp_path / ".ghtraf.json").write_text('{"owner":"x"}', encoding="utf-8")

        args = argparse.Namespace(repo_dir=None)
        with patch("ghtraf.commands.init.find_project_config") as mock_find:
            mock_find.return_value = tmp_path / ".ghtraf.json"
            result = _discover_repo_dir(args)
        assert result == tmp_path

    def test_git_walkup(self, tmp_path):
        """Finds .git directory walking upward (in cwd, no prompt)."""
        import argparse
        (tmp_path / ".git").mkdir()

        args = argparse.Namespace(repo_dir=None, non_interactive=False)
        with patch("ghtraf.commands.init.find_project_config", return_value=None):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = _discover_repo_dir(args)
        assert result == tmp_path

    def test_parent_git_walkup_confirmed(self, tmp_path):
        """Walk-up to parent .git prompts user and respects 'yes'."""
        import argparse
        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / ".git").mkdir()
        child = parent / "subdir"
        child.mkdir()

        args = argparse.Namespace(repo_dir=None, non_interactive=False)
        with patch("ghtraf.commands.init.find_project_config", return_value=None):
            with patch("pathlib.Path.cwd", return_value=child):
                with patch("builtins.input", return_value="y"):
                    result = _discover_repo_dir(args)
        assert result == parent

    def test_parent_git_walkup_declined(self, tmp_path):
        """Walk-up to parent .git prompts user; 'n' falls back to cwd."""
        import argparse
        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / ".git").mkdir()
        child = parent / "subdir"
        child.mkdir()

        args = argparse.Namespace(repo_dir=None, non_interactive=False)
        with patch("ghtraf.commands.init.find_project_config", return_value=None):
            with patch("pathlib.Path.cwd", return_value=child):
                with patch("builtins.input", return_value="n"):
                    result = _discover_repo_dir(args)
        assert result == child

    def test_parent_git_walkup_non_interactive_warns(self, tmp_path, capsys):
        """Non-interactive mode uses parent .git but warns."""
        import argparse
        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / ".git").mkdir()
        child = parent / "subdir"
        child.mkdir()

        args = argparse.Namespace(repo_dir=None, non_interactive=True)
        with patch("ghtraf.commands.init.find_project_config", return_value=None):
            with patch("pathlib.Path.cwd", return_value=child):
                result = _discover_repo_dir(args)
        assert result == parent
        captured = capsys.readouterr()
        assert "parent git repo" in captured.out.lower() or "WARN" in captured.out

    def test_git_in_cwd_no_prompt(self, tmp_path):
        """When .git is in cwd itself, no confirmation prompt fires."""
        import argparse
        (tmp_path / ".git").mkdir()

        args = argparse.Namespace(repo_dir=None, non_interactive=False)
        with patch("ghtraf.commands.init.find_project_config", return_value=None):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                # If input() were called, it would raise (no mock)
                result = _discover_repo_dir(args)
        assert result == tmp_path

    def test_falls_back_to_cwd(self, tmp_path):
        """Falls back to cwd when no .ghtraf.json or .git found.

        Uses non-interactive to avoid prompt if a parent .git exists
        on the test machine. The key assertion is that a valid resolved
        path is returned (not None or error).
        """
        import argparse
        args = argparse.Namespace(repo_dir=None, non_interactive=True)
        with patch("ghtraf.commands.init.find_project_config", return_value=None):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = _discover_repo_dir(args)
        # Should return a valid resolved path (either from .git walk-up or cwd)
        assert result.is_absolute()
        assert result.exists()


# ---------------------------------------------------------------------------
# Real-repo integration tests (Way-of-Scarcity/papers snapshot)
# ---------------------------------------------------------------------------
class TestInitRealRepo:
    """Integration tests using a snapshot of a real GitHub repository.

    These tests verify ghtraf init works against a real repo layout,
    not just empty tmp_path directories. The fixture is a committed
    snapshot of Way-of-Scarcity/papers (README.md only, no PDFs).

    Source: https://github.com/Way-of-Scarcity/papers
    """

    def test_init_creates_github_dir(self, papers_repo):
        """Init should create .github/workflows/ in a repo without one."""
        assert not (papers_repo / ".github").exists()

        result = main([
            "init",
            "--repo-dir", str(papers_repo),
            "--non-interactive",
        ])
        assert result == 0
        assert (papers_repo / ".github" / "workflows").is_dir()
        assert (papers_repo / ".github" / "workflows" / "traffic-badges.yml").is_file()

    def test_init_creates_docs_stats(self, papers_repo):
        """Init should create docs/stats/ in a repo without one."""
        assert not (papers_repo / "docs").exists()

        main([
            "init",
            "--repo-dir", str(papers_repo),
            "--non-interactive",
        ])
        assert (papers_repo / "docs" / "stats" / "index.html").is_file()
        assert (papers_repo / "docs" / "stats" / "README.md").is_file()
        assert (papers_repo / "docs" / "stats" / "favicon.svg").is_file()

    def test_original_files_untouched(self, papers_repo):
        """Init should not modify existing repo files."""
        readme_before = (papers_repo / "README.md").read_text(encoding="utf-8")

        main([
            "init",
            "--repo-dir", str(papers_repo),
            "--non-interactive",
        ])

        readme_after = (papers_repo / "README.md").read_text(encoding="utf-8")
        assert readme_before == readme_after

    def test_skip_existing_on_real_repo(self, papers_repo):
        """--skip-existing preserves user-modified files in a real repo."""
        # First init to create all files
        main([
            "init",
            "--repo-dir", str(papers_repo),
            "--non-interactive",
        ])

        # Simulate user modification
        wf = papers_repo / ".github" / "workflows" / "traffic-badges.yml"
        wf.write_text("# User customized workflow\n", encoding="utf-8")

        # Second init with --skip-existing
        main([
            "init", "--skip-existing",
            "--repo-dir", str(papers_repo),
            "--non-interactive",
        ])

        assert wf.read_text(encoding="utf-8") == "# User customized workflow\n"

    def test_force_overwrites_on_real_repo(self, papers_repo):
        """--force replaces user-modified files in a real repo."""
        # First init
        main([
            "init",
            "--repo-dir", str(papers_repo),
            "--non-interactive",
        ])

        # Modify a file
        wf = papers_repo / ".github" / "workflows" / "traffic-badges.yml"
        wf.write_text("# User customized workflow\n", encoding="utf-8")

        # Force overwrite
        main([
            "init", "--force",
            "--repo-dir", str(papers_repo),
            "--non-interactive",
        ])

        content = wf.read_text(encoding="utf-8")
        assert content != "# User customized workflow\n"
        assert "Track Downloads" in content  # real template content


# ---------------------------------------------------------------------------
# Integration tests — live clone from GitHub (opt-in: pytest -m integration)
# ---------------------------------------------------------------------------
@pytest.mark.integration
class TestInitLiveRepo:
    """Integration tests that clone the real Way-of-Scarcity/papers repo.

    These tests require network access and write persistent results to
    tests/test-runs/ so the user can browse and inspect the output.
    They are excluded from normal pytest runs.

    Run with: pytest -m integration
    """

    def test_init_against_live_clone(self, live_papers_repo):
        """Init deploys all templates into a live GitHub repo clone.

        Results are retained in tests/test-runs/papers-live/ for
        manual inspection — open in your file explorer to see how
        the templates look alongside real repo content.
        """
        # Verify this is a real git repo with actual content
        assert (live_papers_repo / ".git").is_dir()
        assert (live_papers_repo / "README.md").is_file()
        # Should not have our dirs yet
        assert not (live_papers_repo / "docs" / "stats").exists()

        result = main([
            "init",
            "--repo-dir", str(live_papers_repo),
            "--non-interactive",
        ])
        assert result == 0

        # All 4 template files deployed
        for rel in TEMPLATE_FILES:
            dest = live_papers_repo / rel
            assert dest.is_file(), f"Missing: {rel}"
            content = dest.read_text(encoding="utf-8")
            assert len(content) > 10, f"{rel} appears empty"

        # Original content untouched
        readme = (live_papers_repo / "README.md").read_text(encoding="utf-8")
        assert "Scarcity Hypothesis" in readme

    def test_repo_discovery_finds_live_git(self, live_papers_repo):
        """Repo discovery should find .git in the live clone."""
        import argparse

        args = argparse.Namespace(repo_dir=None)
        with patch("ghtraf.commands.init.find_project_config", return_value=None):
            with patch("pathlib.Path.cwd", return_value=live_papers_repo):
                result = _discover_repo_dir(args)
        assert result == live_papers_repo

    def test_init_preserves_special_filenames(self, live_papers_repo):
        """Papers repo has filenames with spaces, brackets, ampersands.

        Verify init doesn't corrupt or interfere with them.
        """
        # Collect original filenames
        originals = set()
        for f in live_papers_repo.iterdir():
            if f.name != ".git":
                originals.add(f.name)

        main([
            "init",
            "--repo-dir", str(live_papers_repo),
            "--non-interactive",
        ])

        # All original files still present
        current = {f.name for f in live_papers_repo.iterdir() if f.name != ".git"}
        for orig in originals:
            assert orig in current, f"Original file missing after init: {orig}"


# ---------------------------------------------------------------------------
# Deploy tests — push to real GitHub repo (opt-in: pytest -m deploy)
# ---------------------------------------------------------------------------
@pytest.mark.deploy
class TestInitDeploy:
    """End-to-end deploy tests that push to a real GitHub repository.

    These tests create/use a private GitHub repo, run the full
    init → create → configure pipeline, push, and verify the
    workflow actually runs. They require GitHub auth and are
    excluded from all normal test runs.

    Run with: pytest -m deploy

    NOT YET IMPLEMENTED — these are stubs that document the
    intended test surface for when deploy testing is built.
    """

    def test_full_pipeline_placeholder(self):
        """Placeholder: init → create → configure → push → verify workflow."""
        pytest.skip(
            "Deploy tests not yet implemented. "
            "See tests/test-data/repos/papers/SOURCE.md for the plan."
        )
