"""Tests for ghtraf.output — output formatting utilities."""

import io
from unittest.mock import patch

import pytest

from ghtraf.lib.log_lib import init_output
from ghtraf.lib.log_lib import manager as _manager_mod
from ghtraf.output import (
    print_banner, print_dry, print_error, print_info, print_ok,
    print_skip, print_step, print_warn,
    get_output, Hint, register_hint, register_hints, trace,
)


# Helper: channel FDs matching GTT's configuration (general/hint → stdout)
# Uses string sentinels so _resolve_fd resolves at call time (pytest capsys compat)
GTT_FDS = {'general': 'stdout', 'hint': 'stdout'}


# ---------------------------------------------------------------------------
# Format tests (verify output text shape)
# ---------------------------------------------------------------------------

def test_print_ok_format(capsys):
    """print_ok should output '[OK] message' format."""
    init_output(verbosity=0, channel_fds=GTT_FDS)
    print_ok("it works")
    captured = capsys.readouterr()
    assert "[OK] it works" in captured.out


def test_print_dry_format(capsys):
    """print_dry should output '[DRY RUN] message' format."""
    init_output(verbosity=0, channel_fds=GTT_FDS)
    print_dry("would do something")
    captured = capsys.readouterr()
    assert "[DRY RUN] would do something" in captured.out


def test_print_warn_format(capsys):
    """print_warn should output '[WARN] message' format."""
    init_output(verbosity=0, channel_fds=GTT_FDS)
    print_warn("careful")
    captured = capsys.readouterr()
    assert "[WARN] careful" in captured.out


def test_print_skip_format(capsys):
    """print_skip should output '[SKIP] message' format."""
    init_output(verbosity=0, channel_fds=GTT_FDS)
    print_skip("not needed")
    captured = capsys.readouterr()
    assert "[SKIP] not needed" in captured.out


def test_print_step_format(capsys):
    """print_step should output '== Step N/M: msg ==' format."""
    init_output(verbosity=0, channel_fds=GTT_FDS)
    print_step(2, 5, "Do the thing")
    captured = capsys.readouterr()
    assert "== Step 2/5: Do the thing ==" in captured.out


def test_print_info_format(capsys):
    """print_info should output the message directly."""
    init_output(verbosity=0, channel_fds=GTT_FDS)
    print_info("informational message")
    captured = capsys.readouterr()
    assert "informational message" in captured.out


def test_print_banner_format(capsys):
    """print_banner should output the message directly."""
    init_output(verbosity=0, channel_fds=GTT_FDS)
    print_banner("=== Header ===")
    captured = capsys.readouterr()
    assert "=== Header ===" in captured.out


# ---------------------------------------------------------------------------
# Graduated quiet axis tests
# ---------------------------------------------------------------------------
class TestGraduatedQuietAxis:
    """print_*() functions follow the graduated quiet axis.

    Graduated quiet axis:
        -Q  (-1)  hides hints (level 0)
        -QQ (-2)  hides info/ok/skip/dry/step/banner (level -1)
        -QQQ(-3)  hides warnings (level -2)
        -QQQQ(-4) hard wall — nothing at all
    """

    @pytest.fixture(autouse=True)
    def _reset_manager(self):
        """Reset OutputManager singleton between tests."""
        old = _manager_mod._manager
        yield
        _manager_mod._manager = old

    def test_default_verbosity_shows_all(self, capsys):
        """At verbosity 0, all print_*() functions show output."""
        init_output(verbosity=0, channel_fds=GTT_FDS)
        print_ok("visible")
        print_warn("visible")
        print_step(1, 3, "visible")
        print_info("visible")
        print_banner("visible")
        captured = capsys.readouterr()
        assert "[OK] visible" in captured.out
        assert "[WARN] visible" in captured.out
        assert "Step 1/3: visible" in captured.out
        assert captured.out.count("visible") == 5

    def test_Q_still_shows_prints(self, capsys):
        """-Q (verbosity -1) still shows all print_*() functions.

        At -1, level -1 messages (ok/skip/etc) pass because -1 <= -1.
        Level -2 (warn) also passes because -2 <= -1.
        """
        init_output(verbosity=-1, channel_fds=GTT_FDS)
        print_ok("still visible")
        print_warn("still visible")
        print_info("still visible")
        captured = capsys.readouterr()
        assert "[OK] still visible" in captured.out
        assert "[WARN] still visible" in captured.out
        assert captured.out.count("still visible") == 3

    def test_QQ_hides_info_ok_skip(self, capsys):
        """-QQ (verbosity -2) hides level -1 messages (ok, skip, dry, step, info, banner).

        Only warn (level -2) still passes because -2 <= -2.
        """
        init_output(verbosity=-2, channel_fds=GTT_FDS)
        print_ok("hidden")
        print_dry("hidden")
        print_skip("hidden")
        print_step(1, 3, "hidden")
        print_info("hidden")
        print_banner("hidden")
        print_warn("still visible")
        captured = capsys.readouterr()
        assert "[OK]" not in captured.out
        assert "[DRY RUN]" not in captured.out
        assert "[SKIP]" not in captured.out
        assert "Step" not in captured.out
        assert "[WARN] still visible" in captured.out

    def test_QQQ_suppresses_prints(self, capsys):
        """-QQQ (verbosity -3) suppresses all print_*() except errors."""
        init_output(verbosity=-3, channel_fds=GTT_FDS)
        print_ok("hidden")
        print_warn("hidden")
        print_step(1, 3, "hidden")
        print_dry("hidden")
        print_skip("hidden")
        print_info("hidden")
        print_banner("hidden")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_QQQQ_suppresses_everything(self, capsys):
        """-QQQQ (verbosity -4) suppresses even errors (hard wall)."""
        init_output(verbosity=-4, channel_fds=GTT_FDS)
        print_ok("hidden")
        print_error("also hidden")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_QQQ_still_shows_errors(self, capsys):
        """-QQQ shows errors via 'error' channel."""
        init_output(verbosity=-3, channel_fds=GTT_FDS)
        print_error("visible error")
        captured = capsys.readouterr()
        assert "ERROR: visible error" in captured.err


# ---------------------------------------------------------------------------
# Channel FD routing tests
# ---------------------------------------------------------------------------
class TestChannelFDRouting:
    """print_*() functions respect channel FD configuration."""

    @pytest.fixture(autouse=True)
    def _reset_manager(self):
        old = _manager_mod._manager
        yield
        _manager_mod._manager = old

    def test_general_channel_goes_to_stdout(self, capsys):
        """With GTT channel FDs, print_ok goes to stdout (general channel)."""
        init_output(verbosity=0, channel_fds=GTT_FDS)
        print_ok("on stdout")
        captured = capsys.readouterr()
        assert "[OK] on stdout" in captured.out
        assert captured.err == ""

    def test_error_channel_goes_to_stderr(self, capsys):
        """print_error always goes to stderr (error channel has no FD override)."""
        init_output(verbosity=0, channel_fds=GTT_FDS)
        print_error("on stderr")
        captured = capsys.readouterr()
        assert "ERROR: on stderr" in captured.err
        assert captured.out == ""

    def test_file_parameter_overrides_channel_fd(self):
        """Per-message file= parameter overrides channel FD."""
        init_output(verbosity=0, channel_fds=GTT_FDS)
        # Force print_ok to a buffer despite general channel being stdout
        buf = io.StringIO()
        print_ok("forced buffer", file=buf)
        assert "[OK] forced buffer" in buf.getvalue()

    def test_set_channel_fd_overrides_default(self):
        """set_channel_fd() overrides the channel's default FD."""
        init_output(verbosity=0, channel_fds=GTT_FDS)
        out = get_output()
        # Redirect general from stdout to a buffer
        buf = io.StringIO()
        out.set_channel_fd('general', buf)
        print_ok("redirected to buffer")
        assert "[OK] redirected to buffer" in buf.getvalue()

    def test_without_channel_fds_falls_to_manager_default(self):
        """Without channel FDs, print_*() falls through to manager default (stderr)."""
        buf = io.StringIO()
        init_output(verbosity=0, channel_fds={'error': buf})  # No general FD
        # OutputManager default file is stderr; without 'general' in channel_fds,
        # _resolve_fd falls through to self.file (stderr). We use a StringIO
        # as the manager's file to capture instead of relying on capsys.
        mgr = get_output()
        mgr.file = buf
        print_ok("on manager default")
        assert "[OK] on manager default" in buf.getvalue()

    def test_fd_resolution_order(self):
        """file= > set_channel_fd > channel_fds > manager default."""
        init_output(verbosity=0, channel_fds=GTT_FDS)
        out = get_output()
        # Layer 2: set_channel_fd overrides channel_fds
        buf = io.StringIO()
        out.set_channel_fd('general', buf)
        print_info("to buffer")
        assert "to buffer" in buf.getvalue()
        # Layer 1: file= overrides set_channel_fd
        buf2 = io.StringIO()
        print_info("to file override", file=buf2)
        assert "to file override" in buf2.getvalue()
        assert "to file override" not in buf.getvalue()


# ---------------------------------------------------------------------------
# Level and channel override tests
# ---------------------------------------------------------------------------
class TestLevelChannelOverrides:
    """print_*() functions accept level= and channel= keyword params."""

    @pytest.fixture(autouse=True)
    def _reset_manager(self):
        old = _manager_mod._manager
        yield
        _manager_mod._manager = old

    def test_print_ok_level_override_suppresses_at_Q(self, capsys):
        """print_ok(level=0) is suppressed at -Q, unlike default level=-1."""
        init_output(verbosity=-1, channel_fds=GTT_FDS)
        print_ok("per-file noise", level=0)
        print_ok("summary stays")  # default level=-1, passes at -1
        captured = capsys.readouterr()
        assert "per-file noise" not in captured.out
        assert "summary stays" in captured.out

    def test_print_warn_level_override(self, capsys):
        """print_warn(level=-1) becomes suppressible at -QQ instead of -QQQ."""
        init_output(verbosity=-2, channel_fds=GTT_FDS)
        print_warn("default warn")  # level=-2, passes at -2
        print_warn("soft warn", level=-1)  # level=-1, hidden at -2
        captured = capsys.readouterr()
        assert "default warn" in captured.out
        assert "soft warn" not in captured.out

    def test_print_info_channel_override(self, capsys):
        """print_info(channel='setup') routes to stderr (setup default)."""
        init_output(verbosity=0, channel_fds=GTT_FDS)
        print_info("user-facing")  # default channel='general' → stdout
        print_info("diagnostic", channel='setup')  # setup → stderr
        captured = capsys.readouterr()
        assert "user-facing" in captured.out
        assert "diagnostic" in captured.err

    def test_print_ok_channel_override(self, capsys):
        """print_ok(channel='setup') routes to stderr."""
        init_output(verbosity=0, channel_fds=GTT_FDS)
        print_ok("via setup", channel='setup')
        captured = capsys.readouterr()
        assert "[OK] via setup" in captured.err
        assert captured.out == ""

    def test_print_error_level_override(self, capsys):
        """print_error(level=-1) becomes hidden at -QQ."""
        init_output(verbosity=-2, channel_fds=GTT_FDS)
        print_error("default error")  # level=-3, passes at -2
        print_error("soft error", level=-1)  # level=-1, hidden at -2
        captured = capsys.readouterr()
        assert "default error" in captured.err
        assert "soft error" not in captured.err

    def test_level_and_channel_together(self, capsys):
        """Both level= and channel= can be overridden simultaneously."""
        init_output(verbosity=0, channel_fds=GTT_FDS)
        buf = io.StringIO()
        out = get_output()
        out.set_channel_fd('setup', buf)
        print_ok("setup ok", level=0, channel='setup')
        assert "[OK] setup ok" in buf.getvalue()

    def test_all_functions_accept_level_channel(self):
        """Every print_*() function accepts level= and channel= kwargs."""
        init_output(verbosity=0, channel_fds=GTT_FDS)
        buf = io.StringIO()
        # These should not raise TypeError
        print_ok("x", level=-1, channel='general', file=buf)
        print_warn("x", level=-2, channel='general', file=buf)
        print_skip("x", level=-1, channel='general', file=buf)
        print_dry("x", level=-1, channel='general', file=buf)
        print_info("x", level=-1, channel='general', file=buf)
        print_banner("x", level=-1, channel='general', file=buf)
        print_error("x", level=-3, channel='error', file=buf)
        print_step(1, 3, "x", level=-1, channel='general', file=buf)
        assert buf.getvalue()  # something was written


# ---------------------------------------------------------------------------
# set_channel_fd usage tests
# ---------------------------------------------------------------------------
class TestSetChannelFdUsage:
    """Commands can use set_channel_fd() to make channels user-facing."""

    @pytest.fixture(autouse=True)
    def _reset_manager(self):
        old = _manager_mod._manager
        yield
        _manager_mod._manager = old

    def test_setup_channel_redirected_to_stdout(self, capsys):
        """set_channel_fd('setup', sys.stdout) makes setup messages user-facing."""
        import sys
        init_output(verbosity=1, channel_fds=GTT_FDS)
        out = get_output()
        # Before: setup goes to stderr (no FD override for 'setup')
        out.emit(1, "before redirect", channel='setup')
        captured_before = capsys.readouterr()
        assert "before redirect" in captured_before.err

        # After: redirect setup to stdout (like create.py does)
        out.set_channel_fd('setup', sys.stdout)
        out.emit(1, "after redirect", channel='setup')
        captured_after = capsys.readouterr()
        assert "after redirect" in captured_after.out


# ---------------------------------------------------------------------------
# Error routing tests
# ---------------------------------------------------------------------------
class TestPrintErrorRoutesToManager:
    """print_error() routes through OutputManager."""

    @pytest.fixture(autouse=True)
    def _reset_manager(self):
        old = _manager_mod._manager
        yield
        _manager_mod._manager = old

    def test_error_goes_to_stderr(self, capsys):
        """print_error() output appears on stderr, not stdout."""
        init_output(verbosity=0, channel_fds=GTT_FDS)
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
