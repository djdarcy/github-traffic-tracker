"""Output formatting utilities for ghtraf.

Consistent message formatting across all commands.  Bridges the
print_*() functions with the THAC0 verbosity system — print functions
respect the quiet axis at extreme levels (-QQQ, -QQQQ).

Also re-exports the log_lib public API for convenience imports.
"""

import sys

# Re-export log_lib public API — one-stop import for commands
from ghtraf.lib.log_lib import (                     # noqa: F401
    OutputManager, init_output, get_output,
    Hint, register_hint, register_hints, get_hint,
    trace,
)


def _should_print():
    """Check if user-facing print_*() calls should display.

    These are effectively level -2 (WARNING) messages — they show at
    verbosity -2 and above, but are suppressed at -3 (errors only)
    and -4 (hard wall / silent).

    Returns True before OutputManager is initialized (pre-init safety).
    """
    try:
        out = get_output()
        if out.verbosity <= -4:
            return False
        return -2 <= out.verbosity
    except Exception:
        return True


def print_step(n, total, msg):
    """Print a formatted step header."""
    if _should_print():
        print(f"\n== Step {n}/{total}: {msg} ==")


def print_ok(msg):
    """Print a success message."""
    if _should_print():
        print(f"  [OK] {msg}")


def print_dry(msg):
    """Print a dry-run message."""
    if _should_print():
        print(f"  [DRY RUN] {msg}")


def print_warn(msg):
    """Print a warning message."""
    if _should_print():
        print(f"  [WARN] {msg}")


def print_skip(msg):
    """Print a skip message."""
    if _should_print():
        print(f"  [SKIP] {msg}")


def print_error(msg):
    """Print an error message to stderr.

    Routes through OutputManager.error() which emits at level -3.
    Shown at all verbosity levels except hard wall (-QQQQ / -4).
    """
    try:
        out = get_output()
        out.error(f"  ERROR: {msg}")
    except Exception:
        print(f"  ERROR: {msg}", file=sys.stderr)


def prompt(label, default=None, required=True):
    """Prompt user for input with optional default.

    Interactive — not filterable by verbosity.

    Args:
        label: Prompt text.
        default: Default value shown in brackets.
        required: If True, exit on empty input.

    Returns:
        User input string.
    """
    if default:
        value = input(f"  {label} [{default}]: ").strip()
        return value or default
    else:
        value = input(f"  {label}: ").strip()
        if not value and required:
            print_error(f"{label} is required.")
            sys.exit(1)
        return value
