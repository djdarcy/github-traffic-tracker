"""
Tests for ghtraf.lib.plan_lib — plan execution, rendering, and file operations.

Tests cover:
- execute_plan() with dependency resolution
- All 3 error policies (fail_fast, skip_deps, continue)
- Dry-run mode
- Topological ordering
- Exception handling in executor_fn
- Plan validation integration
- DefaultTextRenderer output
- FileComparison and DestinationScanResult
- compare_files() and scan_destination() with real files
"""

import io
import os
import tempfile
from pathlib import Path

import pytest

from ghtraf.lib.core_lib import (
    Action,
    ActionResult,
    ConflictResolution,
    FileCategory,
    Plan,
    PlanRenderer,
)
from ghtraf.lib.plan_lib import (
    DefaultTextRenderer,
    DestinationScanResult,
    FileComparison,
    compare_files,
    execute_plan,
    scan_destination,
)


# =============================================================================
# Helpers
# =============================================================================

def _action(id, operation="copy", depends_on=None, **kw):
    return Action(
        id=id, category="file", operation=operation,
        target=id.split(":")[-1], description=f"Action {id}",
        depends_on=depends_on or [], **kw,
    )


def _ok_executor(action):
    return ActionResult(action=action, success=True, message="ok")


def _fail_on(fail_id):
    """Return an executor that fails on a specific action ID."""
    def executor(action):
        if action.id == fail_id:
            return ActionResult(action=action, success=False, error="boom")
        return ActionResult(action=action, success=True, message="ok")
    return executor


# =============================================================================
# execute_plan — Basic
# =============================================================================

class TestExecutePlanBasic:
    def test_empty_plan(self):
        p = Plan(command="test")
        results = execute_plan(p, _ok_executor)
        assert results == []

    def test_single_action(self):
        p = Plan(command="test", actions=[_action("a")])
        results = execute_plan(p, _ok_executor)
        assert len(results) == 1
        assert results[0].success

    def test_preserves_action_reference(self):
        a = _action("a")
        p = Plan(command="test", actions=[a])
        results = execute_plan(p, _ok_executor)
        assert results[0].action is a

    def test_multiple_independent_actions(self):
        p = Plan(command="test", actions=[_action("a"), _action("b"), _action("c")])
        results = execute_plan(p, _ok_executor)
        assert len(results) == 3
        assert all(r.success for r in results)

    def test_invalid_plan_raises(self):
        p = Plan(command="test", actions=[
            _action("a", depends_on=["nonexistent"]),
        ])
        with pytest.raises(ValueError, match="Invalid plan"):
            execute_plan(p, _ok_executor)


# =============================================================================
# execute_plan — Dependency Resolution
# =============================================================================

class TestExecutePlanDependencies:
    def test_respects_dependency_order(self):
        """b depends on a — a must execute first."""
        executed = []
        def tracking_executor(action):
            executed.append(action.id)
            return ActionResult(action=action, success=True, message="ok")

        p = Plan(command="test", actions=[
            _action("b", depends_on=["a"]),
            _action("a"),  # listed second but has no deps
        ])
        execute_plan(p, tracking_executor)
        assert executed.index("a") < executed.index("b")

    def test_diamond_dependency(self):
        """d depends on b and c, which both depend on a."""
        executed = []
        def tracking_executor(action):
            executed.append(action.id)
            return ActionResult(action=action, success=True, message="ok")

        p = Plan(command="test", actions=[
            _action("a"),
            _action("b", depends_on=["a"]),
            _action("c", depends_on=["a"]),
            _action("d", depends_on=["b", "c"]),
        ])
        execute_plan(p, tracking_executor)
        assert executed.index("a") < executed.index("b")
        assert executed.index("a") < executed.index("c")
        assert executed.index("b") < executed.index("d")
        assert executed.index("c") < executed.index("d")

    def test_multiple_roots(self):
        """Independent chains execute correctly."""
        p = Plan(command="test", actions=[
            _action("a1"),
            _action("a2", depends_on=["a1"]),
            _action("b1"),
            _action("b2", depends_on=["b1"]),
        ])
        results = execute_plan(p, _ok_executor)
        assert len(results) == 4
        assert all(r.success for r in results)


# =============================================================================
# execute_plan — Error Policies
# =============================================================================

class TestExecutePlanSkipDeps:
    """Default error policy: skip_deps."""

    def test_dependent_skipped_on_failure(self):
        p = Plan(command="test", actions=[
            _action("a"),
            _action("b", depends_on=["a"]),
            _action("c"),  # independent
        ])
        results = execute_plan(p, _fail_on("a"), on_error="skip_deps")

        result_map = {r.action.id: r for r in results}
        assert not result_map["a"].success
        assert result_map["b"].skipped
        assert "dependency failed" in result_map["b"].message
        assert result_map["c"].success  # independent, still runs

    def test_transitive_skip(self):
        """a fails → b skipped → c (depends on b) also skipped."""
        p = Plan(command="test", actions=[
            _action("a"),
            _action("b", depends_on=["a"]),
            _action("c", depends_on=["b"]),
        ])
        results = execute_plan(p, _fail_on("a"), on_error="skip_deps")

        result_map = {r.action.id: r for r in results}
        assert not result_map["a"].success
        assert result_map["b"].skipped
        assert result_map["c"].skipped


class TestExecutePlanFailFast:
    def test_stops_on_first_failure(self):
        p = Plan(command="test", actions=[
            _action("a"),
            _action("b"),
            _action("c"),
        ])
        results = execute_plan(p, _fail_on("a"), on_error="fail_fast")
        # Only "a" executed — stopped immediately
        assert len(results) == 1
        assert not results[0].success

    def test_stops_after_second_action(self):
        p = Plan(command="test", actions=[
            _action("a"),
            _action("b"),
            _action("c"),
        ])
        results = execute_plan(p, _fail_on("b"), on_error="fail_fast")
        assert len(results) == 2
        assert results[0].success  # a succeeded
        assert not results[1].success  # b failed, stopped


class TestExecutePlanContinue:
    def test_continues_after_failure(self):
        p = Plan(command="test", actions=[
            _action("a"),
            _action("b"),
            _action("c"),
        ])
        results = execute_plan(p, _fail_on("a"), on_error="continue")
        assert len(results) == 3
        assert not results[0].success  # a failed
        assert results[1].success  # b still runs
        assert results[2].success  # c still runs

    def test_dependents_still_run(self):
        """In continue mode, even dependents of failed actions execute."""
        p = Plan(command="test", actions=[
            _action("a"),
            _action("b", depends_on=["a"]),
        ])
        results = execute_plan(p, _fail_on("a"), on_error="continue")
        result_map = {r.action.id: r for r in results}
        assert not result_map["a"].success
        assert result_map["b"].success  # not skipped in continue mode


# =============================================================================
# execute_plan — Dry-run
# =============================================================================

class TestExecutePlanDryRun:
    def test_no_executor_called(self):
        call_count = 0
        def counting_executor(action):
            nonlocal call_count
            call_count += 1
            return ActionResult(action=action, success=True, message="ok")

        p = Plan(command="test", actions=[_action("a"), _action("b")])
        results = execute_plan(p, counting_executor, dry_run=True)
        assert call_count == 0
        assert len(results) == 2

    def test_all_results_marked_skipped(self):
        p = Plan(command="test", actions=[_action("a"), _action("b")])
        results = execute_plan(p, _ok_executor, dry_run=True)
        for r in results:
            assert r.skipped
            assert r.success
            assert r.message == "dry-run"


# =============================================================================
# execute_plan — Exception Handling
# =============================================================================

class TestExecutePlanExceptions:
    def test_executor_exception_caught(self):
        def exploding_executor(action):
            raise RuntimeError("kaboom")

        p = Plan(command="test", actions=[_action("a")])
        results = execute_plan(p, exploding_executor)
        assert len(results) == 1
        assert not results[0].success
        assert "kaboom" in results[0].error

    def test_exception_treated_as_failure(self):
        """Exception in action a should skip dependent b (skip_deps)."""
        def exploding_executor(action):
            if action.id == "a":
                raise ValueError("broken")
            return ActionResult(action=action, success=True, message="ok")

        p = Plan(command="test", actions=[
            _action("a"),
            _action("b", depends_on=["a"]),
            _action("c"),
        ])
        results = execute_plan(p, exploding_executor, on_error="skip_deps")
        result_map = {r.action.id: r for r in results}
        assert not result_map["a"].success
        assert result_map["b"].skipped
        assert result_map["c"].success


# =============================================================================
# DefaultTextRenderer
# =============================================================================

class TestDefaultTextRenderer:
    def test_satisfies_protocol(self):
        r = DefaultTextRenderer()
        assert isinstance(r, PlanRenderer)

    def test_renders_to_stream(self):
        stream = io.StringIO()
        p = Plan(command="test", actions=[
            _action("file:copy:a.txt"),
        ])
        renderer = DefaultTextRenderer(use_color=False)
        renderer.render(p, stream=stream)
        output = stream.getvalue()
        assert "test" in output
        assert "[COPY]" in output
        assert "a.txt" in output

    def test_renders_conflict_indicator(self):
        stream = io.StringIO()
        p = Plan(command="test", actions=[
            _action("file:overwrite:x", operation="overwrite",
                    conflict=ConflictResolution.OVERWRITE),
        ])
        renderer = DefaultTextRenderer(use_color=False)
        renderer.render(p, stream=stream)
        output = stream.getvalue()
        assert "(overwrite)" in output

    def test_renders_warnings(self):
        stream = io.StringIO()
        p = Plan(command="test", actions=[], warnings=["Watch out!"])
        renderer = DefaultTextRenderer(use_color=False)
        renderer.render(p, stream=stream)
        assert "Watch out!" in stream.getvalue()

    def test_renders_skip_as_grey_label(self):
        stream = io.StringIO()
        p = Plan(command="test", actions=[
            _action("file:skip:x", operation="skip"),
        ])
        renderer = DefaultTextRenderer(use_color=False)
        renderer.render(p, stream=stream)
        assert "[SKIP]" in stream.getvalue()

    def test_renders_details_at_verbose(self):
        stream = io.StringIO()
        p = Plan(command="test", actions=[
            _action("file:copy:a", details={"source": "/tmp/a", "size": 1024}),
        ])
        renderer = DefaultTextRenderer(use_color=False)
        renderer.render(p, stream=stream)
        output = stream.getvalue()
        # Details are always rendered when no output_manager (no level filtering)
        assert "source" in output
        assert "1024" in output

    def test_change_count_in_header(self):
        stream = io.StringIO()
        p = Plan(command="init", actions=[
            _action("a", operation="copy"),
            _action("b", operation="skip"),
            _action("c", operation="copy"),
        ])
        renderer = DefaultTextRenderer(use_color=False)
        renderer.render(p, stream=stream)
        assert "2 changes" in stream.getvalue()

    def test_color_disabled(self):
        stream = io.StringIO()
        p = Plan(command="test", actions=[_action("a")])
        renderer = DefaultTextRenderer(use_color=False)
        renderer.render(p, stream=stream)
        assert "\033[" not in stream.getvalue()

    def test_conflict_summary(self):
        stream = io.StringIO()
        p = Plan(command="test", actions=[
            _action("a", conflict=ConflictResolution.OVERWRITE),
            _action("b", conflict=ConflictResolution.RENAME),
        ])
        renderer = DefaultTextRenderer(use_color=False)
        renderer.render(p, stream=stream)
        assert "2 conflict(s)" in stream.getvalue()

    def test_requires_input_flagged(self):
        stream = io.StringIO()
        p = Plan(command="test", actions=[
            _action("file:ask:x", operation="overwrite",
                    conflict=ConflictResolution.ASK, requires_input=True),
            _action("file:copy:y"),
        ])
        renderer = DefaultTextRenderer(use_color=False)
        renderer.render(p, stream=stream)
        output = stream.getvalue()
        assert "[requires input]" in output
        # Only the ASK action has it, not the copy
        lines = output.strip().split("\n")
        ask_lines = [l for l in lines if "x" in l and "[requires input]" in l]
        copy_lines = [l for l in lines if "y" in l and "[requires input]" in l]
        assert len(ask_lines) == 1
        assert len(copy_lines) == 0


# =============================================================================
# FileComparison
# =============================================================================

class TestFileComparison:
    def test_source_only(self):
        fc = FileComparison(rel_path="a.txt", category=FileCategory.SOURCE_ONLY)
        assert not fc.is_conflict
        assert not fc.is_identical

    def test_conflict(self):
        fc = FileComparison(
            rel_path="a.txt", category=FileCategory.CONFLICT,
            source_hash="abc", dest_hash="def",
        )
        assert fc.is_conflict
        assert not fc.is_identical

    def test_identical(self):
        fc = FileComparison(
            rel_path="a.txt", category=FileCategory.IDENTICAL,
            source_hash="abc", dest_hash="abc",
        )
        assert fc.is_identical

    def test_to_details(self):
        fc = FileComparison(
            rel_path="a.txt", category=FileCategory.CONFLICT,
            source_hash="aaa", dest_hash="bbb",
            source_size=100, dest_size=200,
        )
        d = fc.to_details()
        assert d["rel_path"] == "a.txt"
        assert d["category"] == "conflict"
        assert d["source_hash"] == "aaa"
        assert d["dest_hash"] == "bbb"
        assert d["source_size"] == 100
        assert d["dest_size"] == 200


# =============================================================================
# DestinationScanResult
# =============================================================================

class TestDestinationScanResult:
    def test_empty(self):
        r = DestinationScanResult()
        assert r.summary() == {
            "identical": 0, "conflict": 0,
            "source_only": 0, "dest_only": 0, "total": 0,
        }
        assert not r.has_conflicts

    def test_categorized_access(self):
        r = DestinationScanResult(comparisons=[
            FileComparison(rel_path="a", category=FileCategory.IDENTICAL),
            FileComparison(rel_path="b", category=FileCategory.CONFLICT),
            FileComparison(rel_path="c", category=FileCategory.SOURCE_ONLY),
            FileComparison(rel_path="d", category=FileCategory.DEST_ONLY),
        ])
        assert len(r.identical) == 1
        assert len(r.conflicts) == 1
        assert len(r.source_only) == 1
        assert len(r.dest_only) == 1
        assert r.has_conflicts
        assert r.summary()["total"] == 4


# =============================================================================
# compare_files (real filesystem)
# =============================================================================

class TestCompareFiles:
    def test_identical_files(self, tmp_path):
        src = tmp_path / "src" / "a.txt"
        dst = tmp_path / "dst" / "a.txt"
        src.parent.mkdir()
        dst.parent.mkdir()
        src.write_text("hello")
        dst.write_text("hello")

        result = compare_files(src, dst, "a.txt")
        assert result.category == FileCategory.IDENTICAL
        assert result.source_hash == result.dest_hash

    def test_different_files(self, tmp_path):
        src = tmp_path / "src" / "a.txt"
        dst = tmp_path / "dst" / "a.txt"
        src.parent.mkdir()
        dst.parent.mkdir()
        src.write_text("version 2")
        dst.write_text("version 1")

        result = compare_files(src, dst, "a.txt")
        assert result.category == FileCategory.CONFLICT
        assert result.source_hash != result.dest_hash

    def test_source_only(self, tmp_path):
        src = tmp_path / "src" / "new.txt"
        dst = tmp_path / "dst" / "new.txt"
        src.parent.mkdir()
        dst.parent.mkdir(exist_ok=True)
        src.write_text("new file")

        result = compare_files(src, dst, "new.txt")
        assert result.category == FileCategory.SOURCE_ONLY
        assert result.source_path is not None
        assert result.dest_path is None

    def test_dest_only(self, tmp_path):
        src = tmp_path / "src" / "old.txt"
        dst = tmp_path / "dst" / "old.txt"
        src.parent.mkdir()
        dst.parent.mkdir()
        dst.write_text("leftover")

        result = compare_files(src, dst, "old.txt")
        assert result.category == FileCategory.DEST_ONLY

    def test_quick_mode_identical(self, tmp_path):
        """Quick mode compares size + mtime only."""
        src = tmp_path / "a.txt"
        dst = tmp_path / "b.txt"
        src.write_text("hello")
        dst.write_text("hello")
        # Sync mtime
        src_stat = src.stat()
        os.utime(dst, (src_stat.st_atime, src_stat.st_mtime))

        result = compare_files(src, dst, "a.txt", quick=True)
        assert result.category == FileCategory.IDENTICAL
        assert result.source_hash is None  # no hash in quick mode

    def test_quick_mode_different_size(self, tmp_path):
        src = tmp_path / "a.txt"
        dst = tmp_path / "b.txt"
        src.write_text("short")
        dst.write_text("much longer content")

        result = compare_files(src, dst, "a.txt", quick=True)
        assert result.category == FileCategory.CONFLICT


# =============================================================================
# scan_destination (real filesystem)
# =============================================================================

class TestScanDestination:
    def test_full_scan(self, tmp_path):
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()

        # Identical
        (src_dir / "same.txt").write_text("same")
        (dst_dir / "same.txt").write_text("same")

        # Conflict
        (src_dir / "diff.txt").write_text("new")
        (dst_dir / "diff.txt").write_text("old")

        # Source only
        (src_dir / "new.txt").write_text("fresh")

        source_files = {
            "same.txt": str(src_dir / "same.txt"),
            "diff.txt": str(src_dir / "diff.txt"),
            "new.txt": str(src_dir / "new.txt"),
        }

        result = scan_destination(source_files, dst_dir)
        assert len(result.identical) == 1
        assert len(result.conflicts) == 1
        assert len(result.source_only) == 1
        assert len(result.dest_only) == 0  # not requested

    def test_include_dest_only(self, tmp_path):
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()

        (src_dir / "a.txt").write_text("a")
        (dst_dir / "orphan.txt").write_text("orphan")

        source_files = {"a.txt": str(src_dir / "a.txt")}
        result = scan_destination(source_files, dst_dir, include_dest_only=True)
        assert len(result.source_only) == 1
        assert len(result.dest_only) == 1
        assert result.dest_only[0].rel_path == "orphan.txt"

    def test_empty_source(self, tmp_path):
        dst_dir = tmp_path / "dst"
        dst_dir.mkdir()
        result = scan_destination({}, dst_dir)
        assert result.summary()["total"] == 0

    def test_nested_dest_only(self, tmp_path):
        """Dest-only files in subdirectories use forward-slash relative paths."""
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()
        dst_dir.mkdir()
        sub = dst_dir / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("deep")

        result = scan_destination({}, dst_dir, include_dest_only=True)
        assert len(result.dest_only) == 1
        assert result.dest_only[0].rel_path == "sub/deep.txt"
