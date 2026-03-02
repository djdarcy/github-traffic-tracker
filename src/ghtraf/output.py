"""Output formatting utilities for ghtraf.

Consistent message formatting across all commands.  Each print_*()
function routes through OutputManager.emit() with an appropriate level
and channel, participating fully in THAC0 verbosity gating.

Graduated quiet axis:
    -Q  (-1)  hides hints (level 0)
    -QQ (-2)  hides info/ok/skip/dry/step/banner (level -1)
    -QQQ(-3)  hides warnings (level -2)
    -QQQQ(-4) hard wall — nothing at all

Channel FD routing:
    print_error()  → 'error' channel  (default: stderr)
    all others     → 'general' channel (default: stdout when configured)

Also re-exports the log_lib public API for convenience imports.
"""

import sys

# Re-export log_lib public API — one-stop import for commands
from ghtraf.lib.log_lib import (                     # noqa: F401
    OutputManager, init_output, get_output,
    Hint, register_hint, register_hints, get_hint,
    trace,
)


# ---------------------------------------------------------------------------
# Print functions — route through emit()
# ---------------------------------------------------------------------------

def print_step(n, total, msg, *, file=None):
    """Print a formatted step header.

    Level -1 (MINIMAL): hidden at -QQ and below.
    """
    try:
        out = get_output()
        out.emit(-1, f"\n== Step {n}/{total}: {msg} ==",
                 channel='general', file=file)
    except Exception:
        print(f"\n== Step {n}/{total}: {msg} ==", file=file or sys.stdout)


def print_ok(msg, *, file=None):
    """Print a success message.

    Level -1 (MINIMAL): hidden at -QQ and below.
    """
    try:
        out = get_output()
        out.emit(-1, f"  [OK] {msg}", channel='general', file=file)
    except Exception:
        print(f"  [OK] {msg}", file=file or sys.stdout)


def print_dry(msg, *, file=None):
    """Print a dry-run message.

    Level -1 (MINIMAL): hidden at -QQ and below.
    """
    try:
        out = get_output()
        out.emit(-1, f"  [DRY RUN] {msg}", channel='general', file=file)
    except Exception:
        print(f"  [DRY RUN] {msg}", file=file or sys.stdout)


def print_warn(msg, *, file=None):
    """Print a warning message.

    Level -2 (WARNING): hidden at -QQQ and below.
    """
    try:
        out = get_output()
        out.emit(-2, f"  [WARN] {msg}", channel='general', file=file)
    except Exception:
        print(f"  [WARN] {msg}", file=file or sys.stdout)


def print_skip(msg, *, file=None):
    """Print a skip message.

    Level -1 (MINIMAL): hidden at -QQ and below.
    """
    try:
        out = get_output()
        out.emit(-1, f"  [SKIP] {msg}", channel='general', file=file)
    except Exception:
        print(f"  [SKIP] {msg}", file=file or sys.stdout)


def print_error(msg, *, file=None):
    """Print an error message.

    Level -3 (ERROR): shown at all verbosity levels except hard wall (-QQQQ).
    Routes through the 'error' channel (default: stderr).
    """
    try:
        out = get_output()
        out.emit(-3, f"  ERROR: {msg}", channel='error', file=file)
    except Exception:
        print(f"  ERROR: {msg}", file=file or sys.stderr)


def print_info(msg, *, file=None):
    """Print an informational message.

    Level -1 (MINIMAL): hidden at -QQ and below.
    Use for status lines, summaries, and other user-facing text
    that was previously raw print().
    """
    try:
        out = get_output()
        out.emit(-1, msg, channel='general', file=file)
    except Exception:
        print(msg, file=file or sys.stdout)


def print_banner(msg, *, file=None):
    """Print a banner/header message.

    Level -1 (MINIMAL): hidden at -QQ and below.
    Use for command headers, separators, and section titles
    that were previously raw print().
    """
    try:
        out = get_output()
        out.emit(-1, msg, channel='general', file=file)
    except Exception:
        print(msg, file=file or sys.stdout)


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
