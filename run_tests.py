#!/usr/bin/env python3
"""
Test runner for GitHub Traffic Tracker (ghtraf).
Provides categorized test execution with slow test and E2E management.

Usage:
    python run_tests.py             # Run fast unit tests only (default)
    python run_tests.py --all       # Run all tests including slow ones
    python run_tests.py --e2e       # Run Playwright E2E browser tests
    python run_tests.py --slow      # Show information about slow tests
    python run_tests.py --list      # List available test modules
    python run_tests.py --coverage  # Run with coverage report
"""

import sys
import subprocess
import argparse
from pathlib import Path


def run_tests(include_slow=False, verbose=True, coverage=False):
    """
    Run pytest with appropriate configuration.

    Args:
        include_slow: Whether to include slow-marked tests.
        verbose: Whether to show verbose output.
        coverage: Whether to run with coverage analysis.

    Returns:
        Exit code from pytest.
    """
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "--ignore=tests/one-offs",      # Always ignore one-offs
        "--ignore=tests/e2e",           # Exclude E2E by default
        "--tb=short",
        "--durations=10",
    ]

    if verbose:
        cmd.append("-v")

    if not include_slow:
        cmd.extend(["-m", "not slow and not e2e"])

    if coverage:
        cmd.extend([
            "--cov=ghtraf",
            "--cov-report=term-missing",
            "--cov-config=pyproject.toml",
        ])

    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd)
    return result.returncode


def run_e2e():
    """
    Run Playwright E2E browser tests.

    Returns:
        Exit code from pytest, or 1 if playwright not installed.
    """
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("=" * 60)
        print("PLAYWRIGHT NOT INSTALLED")
        print("=" * 60)
        print()
        print("E2E browser tests require Playwright. Install with:")
        print()
        print("  pip install pytest-playwright")
        print("  playwright install chromium")
        print()
        print("Or install all dev + E2E dependencies:")
        print()
        print("  pip install -e '.[dev,e2e]'")
        print("  playwright install")
        print()
        return 1

    e2e_dir = Path("tests/e2e")
    if not e2e_dir.exists():
        print("=" * 60)
        print("NO E2E TESTS FOUND")
        print("=" * 60)
        print()
        print(f"  Expected test directory: {e2e_dir}/")
        print("  E2E tests have not been implemented yet.")
        print("  See GitHub issue for Playwright E2E test harness.")
        print()
        return 0

    cmd = [
        sys.executable, "-m", "pytest",
        "tests/e2e/",
        "-m", "e2e",
        "-v",
        "--tb=short",
    ]

    print(f"Running: {' '.join(cmd)}")
    print("=" * 60)

    result = subprocess.run(cmd)
    return result.returncode


def show_slow_tests():
    """Display information about slow tests and test categories."""
    print("=" * 60)
    print("TEST CATEGORIES")
    print("=" * 60)
    print()
    print("  Fast (default):")
    print("    Unit tests for CLI, config, version, gist schemas,")
    print("    file configuration, and output formatting.")
    print("    Run with: python run_tests.py")
    print()
    print("  Slow (@pytest.mark.slow):")
    print("    Integration tests that mock subprocess calls or")
    print("    perform filesystem-heavy operations.")
    print("    Run with: python run_tests.py --all")
    print()
    print("  E2E (@pytest.mark.e2e):")
    print("    Playwright browser tests for the dashboard.")
    print("    Requires: pip install pytest-playwright")
    print("    Run with: python run_tests.py --e2e")
    print()
    print("  One-offs (always excluded):")
    print("    Historical fix/verify/backfill scripts in tests/one-offs/.")
    print("    Not part of the automated test suite.")
    print()
    print("To mark a test as slow:")
    print("  @pytest.mark.slow")
    print()
    print("To run only slow tests directly:")
    print("  python -m pytest -m slow -v")
    print()


def list_tests():
    """List available test modules."""
    test_dir = Path("tests")
    test_files = sorted(test_dir.glob("test_*.py"))

    print()
    print("Available test modules:")
    print("-" * 40)
    for test_file in test_files:
        print(f"  {test_file.stem}")
    print("-" * 40)

    e2e_dir = test_dir / "e2e"
    if e2e_dir.exists():
        e2e_files = sorted(e2e_dir.glob("test_*.py"))
        if e2e_files:
            print()
            print("E2E test modules (requires playwright):")
            print("-" * 40)
            for test_file in e2e_files:
                print(f"  e2e/{test_file.stem}")
            print("-" * 40)

    oneoff_dir = test_dir / "one-offs"
    if oneoff_dir.exists():
        oneoff_count = len(list(oneoff_dir.glob("*.py")))
        print()
        print(f"One-off scripts (excluded): {oneoff_count} files in tests/one-offs/")

    print()
    print("Run a specific module: python -m pytest tests/test_version.py")


def main():
    """Main entry point for test runner."""
    parser = argparse.ArgumentParser(
        description="Test runner for ghtraf (GitHub Traffic Tracker)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tests.py             # Run fast tests only
  python run_tests.py --all       # Run all tests including slow
  python run_tests.py --e2e       # Run browser tests (requires playwright)
  python run_tests.py --coverage  # Run with coverage report
  python run_tests.py --list      # List test modules
  python run_tests.py --slow      # Show test category info
        """
    )

    parser.add_argument(
        "--all", action="store_true",
        help="Run all tests including slow ones"
    )
    parser.add_argument(
        "--e2e", action="store_true",
        help="Run Playwright E2E browser tests"
    )
    parser.add_argument(
        "--slow", action="store_true",
        help="Show information about test categories"
    )
    parser.add_argument(
        "--coverage", action="store_true",
        help="Run tests with coverage analysis"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List available test modules"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Less verbose output"
    )

    args = parser.parse_args()

    if args.slow:
        show_slow_tests()
        return 0

    if args.list:
        list_tests()
        return 0

    print("=" * 60)
    print("GHTRAF TEST SUITE")
    print("=" * 60)

    if args.e2e:
        print("\nRunning E2E browser tests...")
        return run_e2e()

    if args.all:
        print("\nRunning ALL tests (including slow)...")
    else:
        print("\nRunning fast tests only (use --all for slow tests)...")

    print()
    exit_code = run_tests(
        include_slow=args.all,
        verbose=not args.quiet,
        coverage=args.coverage,
    )

    print()
    print("=" * 60)
    if exit_code == 0:
        print("SUCCESS: All tests passed!")
    else:
        print(f"FAILED: Tests failed with exit code {exit_code}")
    print("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
