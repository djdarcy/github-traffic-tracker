"""Tests for ghtraf.commands.create — the create subcommand.

These tests use the mock_gh fixture from conftest.py to avoid
real GitHub API calls. They exercise the full command flow
via ghtraf.cli.main().

Includes tests for the --files-only dispatch (merged from 'ghtraf init'),
plan-level unit tests for PEV (plan_files, make_files_executor),
and for verifying that init is no longer a recognized subcommand.
"""

import shutil
from datetime import date
from importlib.resources import as_file
from pathlib import Path

import pytest

from ghtraf.cli import main
from ghtraf.commands.create import (
    TEMPLATE_FILES, make_files_executor, plan_files, _get_template_root,
)
from ghtraf.lib.core_lib.types import (
    Action, ActionResult, ConflictResolution, FileCategory, Plan,
)
from ghtraf.lib.plan_lib.executor import execute_plan


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


class TestFilesOnlyDispatch:
    """Test that --files-only dispatches to template deployment, not cloud setup."""

    def test_files_only_skips_cloud_setup(self, tmp_path, capsys):
        """--files-only should deploy templates without any gh API calls.

        No mock_gh fixture needed — if cloud code ran, it would fail
        because gh functions aren't mocked. The test passing proves
        the dispatch works correctly.
        """
        result = main([
            "create", "--files-only",
            "--repo-dir", str(tmp_path),
            "--non-interactive",
        ])
        assert result == 0
        # Templates should exist
        for rel in TEMPLATE_FILES:
            assert (tmp_path / rel).exists(), f"Missing: {rel}"
        # Cloud setup output should NOT appear
        captured = capsys.readouterr()
        assert "badge gist" not in captured.out.lower()
        assert "repository variables" not in captured.out.lower()

    def test_files_only_dry_run(self, tmp_path, capsys):
        """--files-only --dry-run should preview without writing."""
        result = main([
            "create", "--files-only",
            "--dry-run",
            "--repo-dir", str(tmp_path),
        ])
        assert result == 0
        captured = capsys.readouterr()
        assert "DRY RUN" in captured.out
        assert "Would copy" in captured.out
        # No files should be written
        for rel in TEMPLATE_FILES:
            assert not (tmp_path / rel).exists()

    def test_files_only_with_force(self, tmp_path):
        """--files-only --force should overwrite existing files."""
        # Pre-create a file with sentinel content
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        sentinel = wf_dir / "traffic-badges.yml"
        sentinel.write_text("OLD CONTENT", encoding="utf-8")

        result = main([
            "create", "--files-only", "--force",
            "--repo-dir", str(tmp_path),
            "--non-interactive",
        ])
        assert result == 0
        content = sentinel.read_text(encoding="utf-8")
        assert content != "OLD CONTENT"
        assert len(content) > 50  # real template content

    def test_cloud_setup_still_works_without_files_only(self, mock_gh, capsys):
        """Without --files-only, create should still do cloud setup."""
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
        # Cloud setup output SHOULD appear
        assert "badge gist" in captured.out.lower()


# ---------------------------------------------------------------------------
# Plan-level unit tests (PEV infrastructure)
# ---------------------------------------------------------------------------

@pytest.fixture
def template_src(tmp_path):
    """Provide resolved template source directory with real package templates."""
    template_root = _get_template_root()
    with as_file(template_root) as src_root:
        # Copy to a stable temp dir so the context manager doesn't matter
        stable = tmp_path / "_templates"
        shutil.copytree(src_root, stable)
        yield stable


class TestPlanFiles:
    """Unit tests for plan_files() — plan construction only, no execution."""

    def test_fresh_install_all_copy(self, tmp_path, template_src):
        """Empty destination → all SOURCE_ONLY → all file:copy:* actions."""
        dest = tmp_path / "repo"
        dest.mkdir()
        plan = plan_files(dest, template_src)

        assert len(plan.actions) == len(TEMPLATE_FILES)
        for action in plan.actions:
            assert action.id.startswith("file:copy:")
            assert action.operation == "copy"
            assert action.category == "file"

    def test_all_identical_all_skip(self, tmp_path, template_src):
        """Identical files → all file:skip:* actions."""
        dest = tmp_path / "repo"
        dest.mkdir()
        # Copy templates to dest first
        for rel in TEMPLATE_FILES:
            src = template_src / rel
            dst = dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        plan = plan_files(dest, template_src)

        assert len(plan.actions) == len(TEMPLATE_FILES)
        for action in plan.actions:
            assert action.id.startswith("file:skip:")
            assert action.operation == "skip"
        assert not plan.has_changes()

    def test_conflict_with_force(self, tmp_path, template_src):
        """Conflicts + force → file:overwrite:* with OVERWRITE resolution."""
        dest = tmp_path / "repo"
        dest.mkdir()
        # Create conflicting files
        for rel in TEMPLATE_FILES:
            dst = dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text("DIFFERENT CONTENT")

        plan = plan_files(dest, template_src, force=True)

        for action in plan.actions:
            assert action.id.startswith("file:overwrite:")
            assert action.operation == "overwrite"
            assert action.conflict == ConflictResolution.OVERWRITE

    def test_conflict_with_skip_existing(self, tmp_path, template_src):
        """Conflicts + skip_existing → file:skip:* with SKIP resolution."""
        dest = tmp_path / "repo"
        dest.mkdir()
        for rel in TEMPLATE_FILES:
            dst = dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text("DIFFERENT CONTENT")

        plan = plan_files(dest, template_src, skip_existing=True)

        for action in plan.actions:
            assert action.id.startswith("file:skip:")
            assert action.operation == "skip"
            assert action.conflict == ConflictResolution.SKIP

    def test_conflict_interactive(self, tmp_path, template_src):
        """Conflicts without flags → file:ask:* with ASK, requires_input."""
        dest = tmp_path / "repo"
        dest.mkdir()
        for rel in TEMPLATE_FILES:
            dst = dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text("DIFFERENT CONTENT")

        plan = plan_files(dest, template_src)

        for action in plan.actions:
            assert action.id.startswith("file:ask:")
            assert action.conflict == ConflictResolution.ASK
            assert action.requires_input is True

    def test_conflict_non_interactive(self, tmp_path, template_src):
        """Conflicts + non_interactive → file:skip:* (no prompt possible)."""
        dest = tmp_path / "repo"
        dest.mkdir()
        for rel in TEMPLATE_FILES:
            dst = dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text("DIFFERENT CONTENT")

        plan = plan_files(dest, template_src, non_interactive=True)

        for action in plan.actions:
            assert action.id.startswith("file:skip:")
            assert action.operation == "skip"

    def test_plan_validates(self, tmp_path, template_src):
        """Plan from plan_files() always passes validate()."""
        dest = tmp_path / "repo"
        dest.mkdir()
        plan = plan_files(dest, template_src)
        errors = plan.validate()
        assert errors == []

    def test_mixed_scenario(self, tmp_path, template_src):
        """Mix of new, identical, and conflict files."""
        dest = tmp_path / "repo"
        dest.mkdir()

        # Copy first template identically
        first_rel = TEMPLATE_FILES[0]
        src = template_src / first_rel
        dst = dest / first_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        # Create conflict for second template
        second_rel = TEMPLATE_FILES[1]
        dst2 = dest / second_rel
        dst2.parent.mkdir(parents=True, exist_ok=True)
        dst2.write_text("CONFLICT CONTENT")

        # Leave remaining templates as new (no dest file)

        plan = plan_files(dest, template_src, force=True)

        ops = {a.target: a.operation for a in plan.actions}
        assert ops[str(first_rel)] == "skip"       # identical
        assert ops[str(second_rel)] == "overwrite"  # conflict + force
        # Remaining should be copy
        for rel in TEMPLATE_FILES[2:]:
            assert ops[str(rel)] == "copy"


class TestFilesExecutor:
    """Test make_files_executor() behavior."""

    def test_copy_action(self, tmp_path, template_src):
        """Executor copies file for copy action."""
        dest = tmp_path / "repo"
        dest.mkdir()
        executor = make_files_executor(template_src, dest)

        action = Action(
            id="file:copy:docs/stats/favicon.svg",
            category="file", operation="copy",
            target="docs/stats/favicon.svg",
            description="New template file",
        )
        result = executor(action)

        assert result.success is True
        assert not result.skipped
        assert (dest / "docs" / "stats" / "favicon.svg").exists()

    def test_skip_action(self, tmp_path, template_src):
        """Executor returns skipped result for skip action."""
        dest = tmp_path / "repo"
        dest.mkdir()
        executor = make_files_executor(template_src, dest)

        action = Action(
            id="file:skip:docs/stats/favicon.svg",
            category="file", operation="skip",
            target="docs/stats/favicon.svg",
            description="Identical",
        )
        result = executor(action)

        assert result.success is True
        assert result.skipped is True
        assert not (dest / "docs" / "stats" / "favicon.svg").exists()

    def test_overwrite_action(self, tmp_path, template_src):
        """Executor overwrites existing file for overwrite action."""
        dest = tmp_path / "repo"
        dest.mkdir()
        target = dest / "docs" / "stats" / "favicon.svg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("OLD CONTENT")

        executor = make_files_executor(template_src, dest)
        action = Action(
            id="file:overwrite:docs/stats/favicon.svg",
            category="file", operation="overwrite",
            target="docs/stats/favicon.svg",
            description="Overwrite (--force)",
            conflict=ConflictResolution.OVERWRITE,
        )
        result = executor(action)

        assert result.success is True
        assert not result.skipped
        assert target.read_text() != "OLD CONTENT"

    def test_ask_overwrite_yes(self, tmp_path, template_src, monkeypatch):
        """ASK conflict + user says yes → file overwritten."""
        dest = tmp_path / "repo"
        dest.mkdir()
        target = dest / "docs" / "stats" / "favicon.svg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("OLD CONTENT")

        monkeypatch.setattr(
            "ghtraf.commands.create._prompt_overwrite",
            lambda *a, **kw: 'y',
        )

        executor = make_files_executor(template_src, dest)
        action = Action(
            id="file:ask:docs/stats/favicon.svg",
            category="file", operation="overwrite",
            target="docs/stats/favicon.svg",
            description="File exists",
            conflict=ConflictResolution.ASK,
            requires_input=True,
        )
        result = executor(action)

        assert result.success is True
        assert not result.skipped
        assert target.read_text() != "OLD CONTENT"

    def test_ask_overwrite_no(self, tmp_path, template_src, monkeypatch):
        """ASK conflict + user says no → file skipped."""
        dest = tmp_path / "repo"
        dest.mkdir()
        target = dest / "docs" / "stats" / "favicon.svg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("OLD CONTENT")

        monkeypatch.setattr(
            "ghtraf.commands.create._prompt_overwrite",
            lambda *a, **kw: 'n',
        )

        executor = make_files_executor(template_src, dest)
        action = Action(
            id="file:ask:docs/stats/favicon.svg",
            category="file", operation="overwrite",
            target="docs/stats/favicon.svg",
            description="File exists",
            conflict=ConflictResolution.ASK,
            requires_input=True,
        )
        result = executor(action)

        assert result.success is True
        assert result.skipped is True
        assert target.read_text() == "OLD CONTENT"

    def test_ask_overwrite_all(self, tmp_path, template_src, monkeypatch):
        """ASK conflict + user says 'a' → all remaining overwritten."""
        dest = tmp_path / "repo"
        dest.mkdir()

        # Create two conflicting files
        for rel in TEMPLATE_FILES[:2]:
            t = dest / rel
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text("OLD CONTENT")

        call_count = [0]

        def fake_prompt(*a, **kw):
            call_count[0] += 1
            return 'a'  # overwrite all

        monkeypatch.setattr(
            "ghtraf.commands.create._prompt_overwrite", fake_prompt,
        )

        executor = make_files_executor(template_src, dest)

        # First action with ASK
        action1 = Action(
            id=f"file:ask:{TEMPLATE_FILES[0]}",
            category="file", operation="overwrite",
            target=str(TEMPLATE_FILES[0]),
            description="File exists",
            conflict=ConflictResolution.ASK,
            requires_input=True,
        )
        result1 = executor(action1)
        assert result1.success is True
        assert not result1.skipped

        # Second action — should NOT prompt (overwrite_all=True)
        action2 = Action(
            id=f"file:ask:{TEMPLATE_FILES[1]}",
            category="file", operation="overwrite",
            target=str(TEMPLATE_FILES[1]),
            description="File exists",
            conflict=ConflictResolution.ASK,
            requires_input=True,
        )
        result2 = executor(action2)
        assert result2.success is True
        assert not result2.skipped
        # Prompt was only called once (for the first file)
        assert call_count[0] == 1

    def test_ask_skip_all(self, tmp_path, template_src, monkeypatch):
        """ASK conflict + user says 's' → all remaining skipped without prompting."""
        dest = tmp_path / "repo"
        dest.mkdir()

        # Create two conflicting files
        for rel in TEMPLATE_FILES[:2]:
            t = dest / rel
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_text("OLD CONTENT")

        call_count = [0]

        def fake_prompt(*a, **kw):
            call_count[0] += 1
            return 's'  # skip all

        monkeypatch.setattr(
            "ghtraf.commands.create._prompt_overwrite", fake_prompt,
        )

        executor = make_files_executor(template_src, dest)

        # First action with ASK — user says 's'
        action1 = Action(
            id=f"file:ask:{TEMPLATE_FILES[0]}",
            category="file", operation="overwrite",
            target=str(TEMPLATE_FILES[0]),
            description="File exists",
            conflict=ConflictResolution.ASK,
            requires_input=True,
        )
        result1 = executor(action1)
        assert result1.success is True
        assert result1.skipped is True
        assert (dest / TEMPLATE_FILES[0]).read_text() == "OLD CONTENT"

        # Second action — should NOT prompt (skip_all=True)
        action2 = Action(
            id=f"file:ask:{TEMPLATE_FILES[1]}",
            category="file", operation="overwrite",
            target=str(TEMPLATE_FILES[1]),
            description="File exists",
            conflict=ConflictResolution.ASK,
            requires_input=True,
        )
        result2 = executor(action2)
        assert result2.success is True
        assert result2.skipped is True
        assert (dest / TEMPLATE_FILES[1]).read_text() == "OLD CONTENT"
        # Prompt was only called once (for the first file)
        assert call_count[0] == 1


class TestInitSubcommandRemoved:
    """Verify 'init' is no longer a recognized subcommand."""

    def test_init_subcommand_rejected(self):
        """'ghtraf init' should fail — init was merged into create."""
        with pytest.raises(SystemExit) as exc_info:
            main(["init", "--repo-dir", "/tmp/test"])
        assert exc_info.value.code != 0
