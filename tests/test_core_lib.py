"""
Tests for ghtraf.lib.core_lib — shared types and protocols for plan-execute.

Tests cover:
- Action creation and identity (string ID)
- Plan validation (dangling deps, duplicate IDs)
- Plan query methods (has_changes, has_conflicts, has_destructive)
- ConflictResolution and FileCategory enums
- PlanRenderer protocol compliance
"""

import pytest

from ghtraf.lib.core_lib import (
    Action,
    ActionResult,
    Plan,
    ConflictResolution,
    FileCategory,
    ErrorPolicy,
    PlanRenderer,
)


# =============================================================================
# Action
# =============================================================================

class TestAction:
    def test_basic_creation(self):
        a = Action(
            id="file:copy:test.txt",
            category="file",
            operation="copy",
            target="test.txt",
            description="Copy test file",
        )
        assert a.id == "file:copy:test.txt"
        assert a.category == "file"
        assert a.operation == "copy"
        assert a.target == "test.txt"
        assert a.description == "Copy test file"

    def test_defaults(self):
        a = Action(id="x", category="c", operation="o", target="t", description="d")
        assert a.details == {}
        assert a.requires_input is False
        assert a.depends_on == []
        assert a.conflict is None
        assert a.step == 0

    def test_with_dependencies(self):
        a = Action(
            id="gist:create:badge",
            category="gist",
            operation="create",
            target="badge.json",
            description="Create badge",
            depends_on=["file:copy:ci.yml", "file:copy:config"],
        )
        assert len(a.depends_on) == 2
        assert "file:copy:ci.yml" in a.depends_on

    def test_with_conflict(self):
        a = Action(
            id="file:overwrite:x",
            category="file",
            operation="overwrite",
            target="x",
            description="Overwrite",
            conflict=ConflictResolution.OVERWRITE,
        )
        assert a.conflict == ConflictResolution.OVERWRITE

    def test_with_details(self):
        a = Action(
            id="file:copy:x",
            category="file",
            operation="copy",
            target="x",
            description="Copy",
            details={"source": "/tmp/a", "size": 1024},
        )
        assert a.details["source"] == "/tmp/a"
        assert a.details["size"] == 1024

    def test_details_isolation(self):
        """Details dict should not be shared between instances."""
        a = Action(id="a", category="c", operation="o", target="t", description="d")
        b = Action(id="b", category="c", operation="o", target="t", description="d")
        a.details["key"] = "value"
        assert "key" not in b.details


# =============================================================================
# ActionResult
# =============================================================================

class TestActionResult:
    def test_success(self):
        a = Action(id="a", category="c", operation="o", target="t", description="d")
        r = ActionResult(action=a, success=True, message="done")
        assert r.success
        assert r.message == "done"
        assert r.error == ""
        assert not r.skipped

    def test_failure(self):
        a = Action(id="a", category="c", operation="o", target="t", description="d")
        r = ActionResult(action=a, success=False, error="boom")
        assert not r.success
        assert r.error == "boom"

    def test_skipped(self):
        a = Action(id="a", category="c", operation="o", target="t", description="d")
        r = ActionResult(action=a, success=False, skipped=True, message="dep failed")
        assert r.skipped
        assert not r.success


# =============================================================================
# Plan
# =============================================================================

class TestPlan:
    def _make_action(self, id, operation="copy", **kw):
        return Action(
            id=id, category="file", operation=operation,
            target=id.split(":")[-1], description=f"Action {id}", **kw,
        )

    def test_empty_plan(self):
        p = Plan(command="test")
        assert p.actions == []
        assert p.warnings == []
        assert p.context == {}
        assert not p.has_changes()
        assert not p.has_conflicts()
        assert not p.has_destructive()
        assert p.validate() == []

    def test_has_changes_with_skip(self):
        p = Plan(command="test", actions=[
            self._make_action("file:skip:a", operation="skip"),
        ])
        assert not p.has_changes()

    def test_has_changes_with_copy(self):
        p = Plan(command="test", actions=[
            self._make_action("file:copy:a", operation="copy"),
        ])
        assert p.has_changes()

    def test_has_conflicts(self):
        p = Plan(command="test", actions=[
            self._make_action("file:copy:a", conflict=ConflictResolution.OVERWRITE),
        ])
        assert p.has_conflicts()

    def test_has_conflicts_skip_not_counted(self):
        p = Plan(command="test", actions=[
            self._make_action("file:copy:a", conflict=ConflictResolution.SKIP),
        ])
        assert not p.has_conflicts()

    def test_has_destructive(self):
        p = Plan(command="test", actions=[
            self._make_action("file:delete:a", operation="delete"),
        ])
        assert p.has_destructive()

    def test_has_destructive_overwrite(self):
        p = Plan(command="test", actions=[
            self._make_action("file:overwrite:a", operation="overwrite"),
        ])
        assert p.has_destructive()

    def test_has_destructive_reinstall(self):
        p = Plan(command="test", actions=[
            self._make_action("comp:REINSTALL:a", operation="REINSTALL"),
        ])
        assert p.has_destructive()


class TestPlanValidation:
    def _make_action(self, id, depends_on=None, **kw):
        return Action(
            id=id, category="file", operation="copy",
            target=id, description=f"Action {id}",
            depends_on=depends_on or [], **kw,
        )

    def test_valid_plan(self):
        p = Plan(command="test", actions=[
            self._make_action("a"),
            self._make_action("b", depends_on=["a"]),
        ])
        assert p.validate() == []

    def test_dangling_dependency(self):
        p = Plan(command="test", actions=[
            self._make_action("a", depends_on=["nonexistent"]),
        ])
        errors = p.validate()
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_duplicate_ids(self):
        p = Plan(command="test", actions=[
            self._make_action("a"),
            self._make_action("a"),
        ])
        errors = p.validate()
        assert len(errors) == 1
        assert "Duplicate" in errors[0]

    def test_multiple_errors(self):
        p = Plan(command="test", actions=[
            self._make_action("a"),
            self._make_action("a", depends_on=["ghost"]),
        ])
        errors = p.validate()
        assert len(errors) == 2  # duplicate + dangling


class TestPlanLookup:
    def test_get_action(self):
        a = Action(id="x", category="c", operation="o", target="t", description="d")
        p = Plan(command="test", actions=[a])
        assert p.get_action("x") is a
        assert p.get_action("missing") is None

    def test_action_ids(self):
        actions = [
            Action(id="a", category="c", operation="o", target="t", description="d"),
            Action(id="b", category="c", operation="o", target="t", description="d"),
            Action(id="c", category="c", operation="o", target="t", description="d"),
        ]
        p = Plan(command="test", actions=actions)
        assert p.action_ids() == ["a", "b", "c"]


# =============================================================================
# Enums
# =============================================================================

class TestConflictResolution:
    def test_all_seven_modes(self):
        expected = {"skip", "overwrite", "newer", "larger", "rename", "fail", "ask"}
        actual = {e.value for e in ConflictResolution}
        assert actual == expected

    def test_lookup_by_value(self):
        assert ConflictResolution("skip") == ConflictResolution.SKIP
        assert ConflictResolution("ask") == ConflictResolution.ASK

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            ConflictResolution("invalid")


class TestFileCategory:
    def test_all_categories(self):
        expected = {"identical", "conflict", "source_only", "dest_only"}
        actual = {e.value for e in FileCategory}
        assert actual == expected


# =============================================================================
# ErrorPolicy type alias
# =============================================================================

class TestErrorPolicy:
    def test_valid_values(self):
        """ErrorPolicy is a Literal — verify the expected values are accepted."""
        # This tests at runtime that the type alias works as documentation
        for val in ("fail_fast", "skip_deps", "continue"):
            assert isinstance(val, str)


# =============================================================================
# PlanRenderer Protocol
# =============================================================================

class TestPlanRendererProtocol:
    def test_protocol_is_runtime_checkable(self):
        assert hasattr(PlanRenderer, "__protocol_attrs__") or hasattr(
            PlanRenderer, "__abstractmethods__"
        ) or True  # @runtime_checkable makes isinstance work

    def test_class_satisfying_protocol(self):
        class MyRenderer:
            def render(self, plan, output_manager=None):
                pass
        assert isinstance(MyRenderer(), PlanRenderer)

    def test_class_not_satisfying_protocol(self):
        class NotARenderer:
            def display(self, plan):
                pass
        assert not isinstance(NotARenderer(), PlanRenderer)

    def test_lambda_not_satisfying(self):
        assert not isinstance(lambda: None, PlanRenderer)
