"""Integration test: plan_lib executor ↔ preserve_lib operations.

Validates the end-to-end pattern: scan → plan → execute → verify.
The executor_fn uses preserve_lib's compare/hash/metadata functions
to perform real file operations driven by plan_lib's dependency engine.
"""

import shutil
from pathlib import Path

import pytest

from ghtraf.lib.core_lib import Action, ActionResult, Plan, FileCategory
from ghtraf.lib.plan_lib import execute_plan
from ghtraf.lib.preserve_lib import (
    calculate_file_hash,
    verify_file_hash,
    compare_files,
    scan_destination,
    collect_file_metadata,
    FileComparison,
    DestinationScanResult,
)


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def install_scenario(tmp_path):
    """Simulate a file-install scenario with source templates and dest dir.

    source/
        config.yml   — new file (source-only)
        readme.txt   — identical at dest
        workflow.yml  — different at dest (conflict)
    dest/
        readme.txt   — same content as source
        workflow.yml  — different content (conflict)
        extra.log    — dest-only file
    """
    src = tmp_path / "source"
    dst = tmp_path / "dest"
    src.mkdir()
    dst.mkdir()

    (src / "config.yml").write_text("database: sqlite\nport: 5432\n")
    (src / "readme.txt").write_text("# My Project\n")
    (src / "workflow.yml").write_text("steps:\n  - build\n  - test\n")

    (dst / "readme.txt").write_text("# My Project\n")
    (dst / "workflow.yml").write_text("steps:\n  - deploy\n")
    (dst / "extra.log").write_text("log entry\n")

    return src, dst


# ── Scan → Plan → Execute → Verify ───────────────────────────────────

class TestScanToPlan:
    """Scan destination, then build a plan from the scan result."""

    def test_scan_produces_correct_categories(self, install_scenario):
        src, dst = install_scenario
        source_files = list(src.iterdir())

        result = scan_destination(
            source_files, dst,
            path_style="flat",
            quick_check=False,
        )

        assert result.source_only_count == 1   # config.yml
        assert result.identical_count == 1      # readme.txt
        assert result.conflict_count == 1       # workflow.yml

    def test_build_plan_from_scan(self, install_scenario):
        src, dst = install_scenario
        source_files = list(src.iterdir())

        scan = scan_destination(
            source_files, dst,
            path_style="flat",
            quick_check=False,
        )

        # Build a plan from scan results
        actions = []
        for fc in scan.source_only:
            actions.append(Action(
                id=f"copy:{fc.source_path.name}",
                category="file",
                operation="copy",
                target=str(fc.dest_path),
                description=f"Copy new file {fc.source_path.name}",
                details={"source": str(fc.source_path), "dest": str(fc.dest_path)},
            ))
        for fc in scan.identical:
            actions.append(Action(
                id=f"skip:{fc.source_path.name}",
                category="file",
                operation="skip",
                target=str(fc.dest_path),
                description=f"Skip identical {fc.source_path.name}",
            ))
        for fc in scan.conflicts:
            actions.append(Action(
                id=f"overwrite:{fc.source_path.name}",
                category="file",
                operation="overwrite",
                target=str(fc.dest_path),
                description=f"Overwrite conflicting {fc.source_path.name}",
                details={"source": str(fc.source_path), "dest": str(fc.dest_path)},
            ))

        plan = Plan(command="install", actions=actions)
        assert plan.validate() == []
        assert plan.has_changes()  # copy + overwrite actions
        assert plan.has_destructive()  # overwrite action


class TestExecutePlanWithPreserveLib:
    """Execute a plan using preserve_lib as the executor backend."""

    def _preserve_executor(self, action: Action) -> ActionResult:
        """Executor that uses preserve_lib for real file operations."""
        if action.operation == "skip":
            return ActionResult(action=action, success=True, message="skipped")

        src = Path(action.details["source"])
        dst = Path(action.details["dest"])

        if action.operation in ("copy", "overwrite"):
            # Collect metadata before copy
            meta = collect_file_metadata(src)
            # Hash before copy for verification
            pre_hash = calculate_file_hash(src)

            # Do the copy
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

            # Verify after copy
            ok, details = verify_file_hash(dst, pre_hash)
            if ok:
                return ActionResult(
                    action=action, success=True,
                    message=f"Copied and verified ({meta['size']} bytes)",
                )
            else:
                return ActionResult(
                    action=action, success=False,
                    error="Post-copy hash verification failed",
                )

        return ActionResult(
            action=action, success=False,
            error=f"Unknown operation: {action.operation}",
        )

    def test_execute_copy_and_verify(self, install_scenario):
        """End-to-end: scan → plan → execute → verify."""
        src, dst = install_scenario
        source_files = list(src.iterdir())

        # 1. Scan
        scan = scan_destination(
            source_files, dst, path_style="flat", quick_check=False,
        )

        # 2. Build plan
        actions = []
        for fc in scan.source_only:
            actions.append(Action(
                id=f"copy:{fc.source_path.name}",
                category="file", operation="copy",
                target=str(fc.dest_path),
                description=f"Copy {fc.source_path.name}",
                details={"source": str(fc.source_path), "dest": str(fc.dest_path)},
            ))
        for fc in scan.conflicts:
            actions.append(Action(
                id=f"overwrite:{fc.source_path.name}",
                category="file", operation="overwrite",
                target=str(fc.dest_path),
                description=f"Overwrite {fc.source_path.name}",
                details={"source": str(fc.source_path), "dest": str(fc.dest_path)},
            ))

        plan = Plan(command="install", actions=actions)

        # 3. Execute
        results = execute_plan(plan, self._preserve_executor)

        # 4. Verify all succeeded
        assert all(r.success for r in results)
        assert len(results) == 2  # copy + overwrite

        # 5. Verify files match source
        for fc in scan.source_only:
            comparison = compare_files(fc.source_path, fc.dest_path)
            assert comparison.category == FileCategory.IDENTICAL

        for fc in scan.conflicts:
            comparison = compare_files(fc.source_path, fc.dest_path)
            assert comparison.category == FileCategory.IDENTICAL

    def test_dry_run_skips_execution(self, install_scenario):
        src, dst = install_scenario

        actions = [Action(
            id="copy:config.yml",
            category="file", operation="copy",
            target=str(dst / "config.yml"),
            description="Copy config.yml",
            details={"source": str(src / "config.yml"), "dest": str(dst / "config.yml")},
        )]
        plan = Plan(command="install", actions=actions)

        results = execute_plan(plan, self._preserve_executor, dry_run=True)
        assert len(results) == 1
        assert results[0].skipped is True
        # File should NOT exist at dest
        assert not (dst / "config.yml").exists()

    def test_dependency_chain_execution(self, install_scenario):
        """Actions with depends_on execute in correct order."""
        src, dst = install_scenario

        actions = [
            Action(
                id="copy:config.yml",
                category="file", operation="copy",
                target=str(dst / "config.yml"),
                description="Copy config first",
                details={"source": str(src / "config.yml"), "dest": str(dst / "config.yml")},
            ),
            Action(
                id="copy:readme.txt",
                category="file", operation="copy",
                target=str(dst / "readme2.txt"),
                description="Copy readme after config",
                details={"source": str(src / "readme.txt"), "dest": str(dst / "readme2.txt")},
                depends_on=["copy:config.yml"],
            ),
        ]
        plan = Plan(command="install", actions=actions)

        results = execute_plan(plan, self._preserve_executor)
        assert len(results) == 2
        assert all(r.success for r in results)
        # Both files should exist
        assert (dst / "config.yml").exists()
        assert (dst / "readme2.txt").exists()

    def test_failed_dep_skips_dependent(self, install_scenario):
        """If copy fails, dependent actions are skipped."""
        src, dst = install_scenario

        def failing_executor(action: Action) -> ActionResult:
            if action.id == "fail:first":
                return ActionResult(action=action, success=False, error="intentional")
            return self._preserve_executor(action)

        actions = [
            Action(
                id="fail:first",
                category="file", operation="copy",
                target="x",
                description="This will fail",
                details={"source": str(src / "nonexistent"), "dest": str(dst / "x")},
            ),
            Action(
                id="copy:config.yml",
                category="file", operation="copy",
                target=str(dst / "config.yml"),
                description="Depends on failed action",
                details={"source": str(src / "config.yml"), "dest": str(dst / "config.yml")},
                depends_on=["fail:first"],
            ),
        ]
        plan = Plan(command="install", actions=actions)

        results = execute_plan(plan, failing_executor, on_error="skip_deps")
        assert results[0].success is False
        assert results[1].skipped is True
        # config.yml should NOT exist at dest
        assert not (dst / "config.yml").exists()


class TestHashVerifyRoundtrip:
    """Hash → copy → verify roundtrip using preserve_lib functions."""

    def test_hash_survives_copy(self, tmp_path):
        src = tmp_path / "original.bin"
        dst = tmp_path / "copy.bin"
        src.write_bytes(b"binary data \x00\x01\x02\x03" * 100)

        pre_hash = calculate_file_hash(src, ["SHA256", "MD5"])
        shutil.copy2(src, dst)
        ok, details = verify_file_hash(dst, pre_hash)

        assert ok is True
        assert details["SHA256"][0] is True
        assert details["MD5"][0] is True

    def test_tampered_file_fails_verify(self, tmp_path):
        src = tmp_path / "original.txt"
        dst = tmp_path / "tampered.txt"
        src.write_text("original content")

        pre_hash = calculate_file_hash(src)
        dst.write_text("tampered content")
        ok, _ = verify_file_hash(dst, pre_hash)

        assert ok is False
