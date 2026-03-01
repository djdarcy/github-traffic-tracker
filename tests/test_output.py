"""Tests for ghtraf.output — output formatting utilities."""

import io
from unittest.mock import patch

import pytest

from ghtraf.lib.log_lib import init_output
from ghtraf.lib.log_lib import manager as _manager_mod
from ghtraf.output import (
    print_dry, print_error, print_ok, print_skip, print_step, print_warn,
    get_output, Hint, register_hint, register_hints, trace,
)


def test_print_ok_format(capsys):
    """print_ok should output '[OK] message' format."""
    print_ok("it works")
    captured = capsys.readouterr()
    assert "[OK] it works" in captured.out


def test_print_dry_format(capsys):
    """print_dry should output '[DRY RUN] message' format."""
    print_dry("would do something")
    captured = capsys.readouterr()
    assert "[DRY RUN] would do something" in captured.out


def test_print_warn_format(capsys):
    """print_warn should output '[WARN] message' format."""
    print_warn("careful")
    captured = capsys.readouterr()
    assert "[WARN] careful" in captured.out


def test_print_skip_format(capsys):
    """print_skip should output '[SKIP] message' format."""
    print_skip("not needed")
    captured = capsys.readouterr()
    assert "[SKIP] not needed" in captured.out


def test_print_step_format(capsys):
    """print_step should output '== Step N/M: msg ==' format."""
    print_step(2, 5, "Do the thing")
    captured = capsys.readouterr()
    assert "== Step 2/5: Do the thing ==" in captured.out


# ---------------------------------------------------------------------------
# Quiet axis suppression tests
# ---------------------------------------------------------------------------
class TestQuietAxisSuppression:
    """print_*() functions respect the THAC0 quiet axis."""

    @pytest.fixture(autouse=True)
    def _reset_manager(self):
        """Reset OutputManager singleton between tests."""
        old = _manager_mod._manager
        yield
        _manager_mod._manager = old

    def test_default_verbosity_shows_all(self, capsys):
        """At verbosity 0, all print_*() functions show output."""
        init_output(verbosity=0)
        print_ok("visible")
        print_warn("visible")
        print_step(1, 3, "visible")
        captured = capsys.readouterr()
        assert "[OK] visible" in captured.out
        assert "[WARN] visible" in captured.out
        assert "Step 1/3: visible" in captured.out

    def test_quiet_Q_still_shows_prints(self, capsys):
        """-Q (verbosity -1) still shows print_*() functions."""
        init_output(verbosity=-1)
        print_ok("still visible")
        print_warn("still visible")
        captured = capsys.readouterr()
        assert "[OK] still visible" in captured.out
        assert "[WARN] still visible" in captured.out

    def test_quiet_QQ_still_shows_prints(self, capsys):
        """-QQ (verbosity -2) still shows print_*() functions."""
        init_output(verbosity=-2)
        print_ok("still visible")
        print_dry("still visible")
        print_skip("still visible")
        captured = capsys.readouterr()
        assert "[OK] still visible" in captured.out
        assert "[DRY RUN] still visible" in captured.out
        assert "[SKIP] still visible" in captured.out

    def test_quiet_QQQ_suppresses_prints(self, capsys):
        """-QQQ (verbosity -3) suppresses all print_*() except errors."""
        init_output(verbosity=-3)
        print_ok("hidden")
        print_warn("hidden")
        print_step(1, 3, "hidden")
        print_dry("hidden")
        print_skip("hidden")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_quiet_QQQQ_suppresses_everything(self, capsys):
        """-QQQQ (verbosity -4) suppresses even errors (hard wall)."""
        init_output(verbosity=-4)
        print_ok("hidden")
        print_error("also hidden")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_QQQ_still_shows_errors(self, capsys):
        """-QQQ shows errors via OutputManager.error()."""
        init_output(verbosity=-3)
        print_error("visible error")
        captured = capsys.readouterr()
        assert "ERROR: visible error" in captured.err


# ---------------------------------------------------------------------------
# Error routing tests
# ---------------------------------------------------------------------------
class TestPrintErrorRoutesToManager:
    """print_error() routes through OutputManager.error()."""

    @pytest.fixture(autouse=True)
    def _reset_manager(self):
        old = _manager_mod._manager
        yield
        _manager_mod._manager = old

    def test_error_goes_to_stderr(self, capsys):
        """print_error() output appears on stderr, not stdout."""
        init_output(verbosity=0)
        print_error("something broke")
        captured = capsys.readouterr()
        assert "ERROR: something broke" in captured.err
        assert captured.out == ""


# ---------------------------------------------------------------------------
# Re-export tests
# ---------------------------------------------------------------------------
class TestReExports:
    """output.py re-exports the log_lib public API."""

    def test_get_output_exported(self):
        assert callable(get_output)

    def test_hint_exported(self):
        assert Hint is not None

    def test_register_hint_exported(self):
        assert callable(register_hint)
        assert callable(register_hints)

    def test_trace_exported(self):
        assert callable(trace)
