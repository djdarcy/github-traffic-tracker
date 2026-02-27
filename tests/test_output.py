"""Tests for ghtraf.output — output formatting utilities."""

import io
from unittest.mock import patch

from ghtraf.output import print_dry, print_ok, print_skip, print_step, print_warn


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
