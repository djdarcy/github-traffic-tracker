"""Output formatting utilities for ghtraf.

Consistent message formatting across all commands.
"""

import sys


def print_step(n, total, msg):
    """Print a formatted step header."""
    print(f"\n== Step {n}/{total}: {msg} ==")


def print_ok(msg):
    """Print a success message."""
    print(f"  [OK] {msg}")


def print_dry(msg):
    """Print a dry-run message."""
    print(f"  [DRY RUN] {msg}")


def print_warn(msg):
    """Print a warning message."""
    print(f"  [WARN] {msg}")


def print_skip(msg):
    """Print a skip message."""
    print(f"  [SKIP] {msg}")


def print_error(msg):
    """Print an error message to stderr."""
    print(f"  ERROR: {msg}", file=sys.stderr)


def prompt(label, default=None, required=True):
    """Prompt user for input with optional default.

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
            print(f"  ERROR: {label} is required.")
            sys.exit(1)
        return value
