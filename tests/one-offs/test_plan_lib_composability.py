"""
End-to-end composability test: scan → build plan → render → execute → verify.

Proves the full plan_lib stack works together before investing in
ghtraf init/create retrofit. Exercises the seams between:
- plan_lib/file_ops.py (scan_destination, FileComparison)
- core_lib (Action, Plan, ConflictResolution)
- plan_lib/renderer.py (DefaultTextRenderer)
- plan_lib/executor.py (execute_plan)
- dazzle_filekit (via file_ops hash comparison)
"""

import io
import os
import shutil
from dataclasses import asdict
from pathlib import Path

import pytest

from ghtraf.lib.core_lib import (
    Action,
    ActionResult,
    ConflictResolution,
    FileCategory,
    Plan,
)
from ghtraf.lib.plan_lib import (
    DefaultTextRenderer,
    compare_files,
    execute_plan,
    scan_destination,
)


# =============================================================================
# Full Stack: scan → plan → render → execute
# =============================================================================

class TestFileInstallScenario:
    """Simulates ghtraf init: scan templates → build plan → render → execute."""

    def _build_plan_from_scan(self, scan_result, force=False):
        """Build a Plan from scan results — mirrors what init.py would do."""
        actions = []
        for comp in scan_result.comparisons:
            if comp.category == FileCategory.SOURCE_ONLY:
                actions.append(Action(
                    id=f"file:copy:{comp.rel_path}",
                    category="file",
                    operation="copy",
                    target=comp.rel_path,
                    description=f"Copy {comp.rel_path}",
                    details=comp.to_details(),
                ))
            elif comp.category == FileCategory.CONFLICT:
                if force:
                    actions.append(Action(
                        id=f"file:overwrite:{comp.rel_path}",
                        category="file",
                        operation="overwrite",
                        target=comp.rel_path,
                        description=f"Overwrite {comp.rel_path}",
                        conflict=ConflictResolution.OVERWRITE,
                        details=comp.to_details(),
                    ))
                else:
                    actions.append(Action(
                        id=f"file:skip:{comp.rel_path}",
                        category="file",
                        operation="skip",
                        target=comp.rel_path,
                        description=f"Skip {comp.rel_path} (exists)",
                        conflict=ConflictResolution.SKIP,
                        details=comp.to_details(),
                    ))
            elif comp.category == FileCategory.IDENTICAL:
                actions.append(Action(
                    id=f"file:skip:{comp.rel_path}",
                    category="file",
                    operation="skip",
                    target=comp.rel_path,
                    description=f"Skip {comp.rel_path} (identical)",
                ))
        return Plan(command="init", actions=actions)

    def _make_file_executor(self, src_dir, dst_dir):
        """Create an executor_fn that copies files from src to dst."""
        def file_executor(action):
            if action.operation == "skip":
                return ActionResult(
                    action=action, success=True, skipped=True,
                    message=f"Skipped {action.target}",
                )
            src_path = src_dir / action.target
            dst_path = dst_dir / action.target
            os.makedirs(dst_path.parent, exist_ok=True)
            shutil.copy2(str(src_path), str(dst_path))
            return ActionResult(
                action=action, success=True,
                message=f"Copied {action.target}",
            )
        return file_executor

    def test_fresh_install(self, tmp_path):
        """No existing files — all should be copied."""
        src = tmp_path / "templates"
        dst = tmp_path / "project"
        src.mkdir()
        dst.mkdir()

        (src / "ci.yml").write_text("name: CI\non: push")
        (src / "config.json").write_text('{"version": 1}')

        source_files = {
            "ci.yml": str(src / "ci.yml"),
            "config.json": str(src / "config.json"),
        }
        scan = scan_destination(source_files, dst)
        assert len(scan.source_only) == 2

        plan = self._build_plan_from_scan(scan)
        assert plan.validate() == []
        assert plan.has_changes()
        assert not plan.has_conflicts()

        # Render without crash
        stream = io.StringIO()
        DefaultTextRenderer(use_color=False).render(plan, stream=stream)
        output = stream.getvalue()
        assert "[COPY]" in output
        assert "2 changes" in output

        # Execute
        results = execute_plan(plan, self._make_file_executor(src, dst))
        assert all(r.success for r in results)
        assert (dst / "ci.yml").read_text() == "name: CI\non: push"
        assert (dst / "config.json").read_text() == '{"version": 1}'

    def test_mixed_with_force(self, tmp_path):
        """Some files exist, --force overwrites conflicts."""
        src = tmp_path / "templates"
        dst = tmp_path / "project"
        src.mkdir()
        dst.mkdir()

        (src / "new.txt").write_text("brand new")
        (src / "changed.txt").write_text("version 2")
        (dst / "changed.txt").write_text("version 1")
        (src / "same.txt").write_text("identical")
        (dst / "same.txt").write_text("identical")

        source_files = {
            "new.txt": str(src / "new.txt"),
            "changed.txt": str(src / "changed.txt"),
            "same.txt": str(src / "same.txt"),
        }
        scan = scan_destination(source_files, dst)
        assert len(scan.source_only) == 1
        assert len(scan.conflicts) == 1
        assert len(scan.identical) == 1

        plan = self._build_plan_from_scan(scan, force=True)
        assert plan.validate() == []
        assert plan.has_changes()
        assert plan.has_conflicts()

        # Render shows overwrite
        stream = io.StringIO()
        DefaultTextRenderer(use_color=False).render(plan, stream=stream)
        assert "[OVERWRITE]" in stream.getvalue()
        assert "(overwrite)" in stream.getvalue()

        results = execute_plan(plan, self._make_file_executor(src, dst))
        assert all(r.success for r in results)
        assert (dst / "new.txt").read_text() == "brand new"
        assert (dst / "changed.txt").read_text() == "version 2"
        assert (dst / "same.txt").read_text() == "identical"

    def test_skip_existing(self, tmp_path):
        """--skip-existing: only copy new files."""
        src = tmp_path / "templates"
        dst = tmp_path / "project"
        src.mkdir()
        dst.mkdir()

        (src / "new.txt").write_text("new content")
        (src / "existing.txt").write_text("updated")
        (dst / "existing.txt").write_text("original")

        source_files = {
            "new.txt": str(src / "new.txt"),
            "existing.txt": str(src / "existing.txt"),
        }
        scan = scan_destination(source_files, dst)
        plan = self._build_plan_from_scan(scan, force=False)

        assert plan.has_changes()  # new.txt is a copy
        results = execute_plan(plan, self._make_file_executor(src, dst))

        assert (dst / "new.txt").read_text() == "new content"
        assert (dst / "existing.txt").read_text() == "original"  # NOT overwritten

    def test_dry_run_writes_nothing(self, tmp_path):
        """Dry-run: plan is built and rendered, but no files are written."""
        src = tmp_path / "templates"
        dst = tmp_path / "project"
        src.mkdir()
        dst.mkdir()

        (src / "a.txt").write_text("content")

        source_files = {"a.txt": str(src / "a.txt")}
        scan = scan_destination(source_files, dst)
        plan = self._build_plan_from_scan(scan)

        call_count = 0
        def counting_executor(action):
            nonlocal call_count
            call_count += 1
            return ActionResult(action=action, success=True)

        results = execute_plan(plan, counting_executor, dry_run=True)
        assert call_count == 0
        assert all(r.skipped for r in results)
        assert not (dst / "a.txt").exists()


# =============================================================================
# API-centric scenario (simulates ghtraf create)
# =============================================================================

class TestApiCentricScenario:
    """Simulates ghtraf create: build plan with dependencies → execute."""

    def test_gist_creation_with_dependencies(self):
        """Create badge gist → create archive gist → set secrets."""
        created_gists = {}

        def api_executor(action):
            if action.category == "gist" and action.operation == "create":
                gist_id = f"fake_gist_{action.target.replace(' ', '_')}"
                created_gists[action.target] = gist_id
                return ActionResult(
                    action=action, success=True,
                    message=f"Created gist: {gist_id}",
                )
            elif action.category == "variable" and action.operation == "set":
                return ActionResult(
                    action=action, success=True,
                    message=f"Set {action.target}",
                )
            return ActionResult(action=action, success=False, error="Unknown")

        plan = Plan(command="create", actions=[
            Action(
                id="gist:create:badge",
                category="gist", operation="create",
                target="badge gist",
                description="Create public badge gist",
            ),
            Action(
                id="gist:create:archive",
                category="gist", operation="create",
                target="archive gist",
                description="Create unlisted archive gist",
            ),
            Action(
                id="var:set:BADGE_GIST_ID",
                category="variable", operation="set",
                target="BADGE_GIST_ID",
                description="Set badge gist ID as repo variable",
                depends_on=["gist:create:badge"],
            ),
            Action(
                id="var:set:ARCHIVE_GIST_ID",
                category="variable", operation="set",
                target="ARCHIVE_GIST_ID",
                description="Set archive gist ID as repo variable",
                depends_on=["gist:create:archive"],
            ),
        ])

        assert plan.validate() == []
        results = execute_plan(plan, api_executor)
        assert all(r.success for r in results)
        assert "badge gist" in created_gists
        assert "archive gist" in created_gists

    def test_api_failure_skips_dependent_secrets(self):
        """If gist creation fails, dependent variable-set is skipped."""
        def failing_api(action):
            if action.id == "gist:create:badge":
                return ActionResult(
                    action=action, success=False,
                    error="gh: API rate limit exceeded",
                )
            return ActionResult(action=action, success=True, message="ok")

        plan = Plan(command="create", actions=[
            Action(
                id="gist:create:badge",
                category="gist", operation="create",
                target="badge gist", description="Create badge gist",
            ),
            Action(
                id="var:set:BADGE_GIST_ID",
                category="variable", operation="set",
                target="BADGE_GIST_ID", description="Set badge gist ID",
                depends_on=["gist:create:badge"],
            ),
            Action(
                id="gist:create:archive",
                category="gist", operation="create",
                target="archive gist", description="Create archive gist",
            ),
        ])

        results = execute_plan(plan, failing_api, on_error="skip_deps")
        result_map = {r.action.id: r for r in results}

        assert not result_map["gist:create:badge"].success
        assert result_map["var:set:BADGE_GIST_ID"].skipped
        assert result_map["gist:create:archive"].success  # independent


# =============================================================================
# Serialization round-trip
# =============================================================================

class TestPlanSerialization:
    """Verify Plan/Action can be serialized for debugging and persistence."""

    def test_asdict_round_trip(self):
        plan = Plan(command="init", actions=[
            Action(
                id="file:copy:ci.yml",
                category="file", operation="copy",
                target="ci.yml", description="Copy CI workflow",
                details={"source": "/tmp/ci.yml", "size": 1024},
                conflict=ConflictResolution.OVERWRITE,
                depends_on=["file:create:dir"],
            ),
        ])
        d = asdict(plan)
        assert d["command"] == "init"
        assert len(d["actions"]) == 1
        action_d = d["actions"][0]
        assert action_d["id"] == "file:copy:ci.yml"
        assert action_d["conflict"] == ConflictResolution.OVERWRITE
        assert action_d["depends_on"] == ["file:create:dir"]
        assert action_d["details"]["size"] == 1024

    def test_asdict_to_json(self):
        """Verify JSON serialization works (enum needs .value)."""
        import json

        plan = Plan(command="test", actions=[
            Action(
                id="a", category="c", operation="o",
                target="t", description="d",
                conflict=ConflictResolution.ASK,
            ),
        ])
        d = asdict(plan)

        # ConflictResolution enum needs conversion for JSON
        def enum_serializer(obj):
            if hasattr(obj, 'value'):
                return obj.value
            raise TypeError(f"Not serializable: {type(obj)}")

        json_str = json.dumps(d, default=enum_serializer)
        loaded = json.loads(json_str)
        assert loaded["actions"][0]["conflict"] == "ask"
        assert loaded["actions"][0]["id"] == "a"
