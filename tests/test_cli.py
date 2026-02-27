"""Tests for ghtraf.cli — CLI argument parsing and dispatch."""

import subprocess
import sys

import pytest

from ghtraf.cli import _build_common_parser, _extract_global_flags, main


class TestGlobalFlagExtraction:
    """Test the Docker-style two-pass global flag parsing."""

    def test_verbose_before_subcommand(self):
        """--verbose before subcommand should be extracted."""
        global_args, remaining = _extract_global_flags(
            ["--verbose", "create", "--owner", "x"]
        )
        assert global_args.verbose is True
        assert "create" in remaining
        assert "--verbose" not in remaining

    def test_verbose_after_subcommand(self):
        """--verbose after subcommand args should also be extracted."""
        global_args, remaining = _extract_global_flags(
            ["create", "--owner", "x", "--verbose"]
        )
        assert global_args.verbose is True
        assert "--verbose" not in remaining

    def test_no_color_extracted(self):
        """--no-color should be extracted as a global flag."""
        global_args, remaining = _extract_global_flags(
            ["--no-color", "create"]
        )
        assert global_args.no_color is True

    def test_config_with_value(self):
        """--config PATH should be extracted with its value."""
        global_args, remaining = _extract_global_flags(
            ["--config", "/tmp/my.json", "create"]
        )
        assert global_args.config == "/tmp/my.json"
        assert "/tmp/my.json" not in remaining

    def test_no_global_flags(self):
        """When no global flags, all args pass through."""
        global_args, remaining = _extract_global_flags(
            ["create", "--owner", "x"]
        )
        assert global_args.verbose is False
        assert global_args.no_color is False
        assert global_args.config is None
        assert remaining == ["create", "--owner", "x"]

    def test_empty_argv(self):
        """Empty argv should produce default global args."""
        global_args, remaining = _extract_global_flags([])
        assert global_args.verbose is False
        assert remaining == []


class TestCommonParser:
    """Test the shared parent parser for repo-scoped flags."""

    def test_common_parser_has_owner(self):
        """Shared parser should accept --owner."""
        parser = _build_common_parser()
        args = parser.parse_args(["--owner", "myorg"])
        assert args.owner == "myorg"

    def test_common_parser_has_repo(self):
        """Shared parser should accept --repo."""
        parser = _build_common_parser()
        args = parser.parse_args(["--repo", "myproject"])
        assert args.repo == "myproject"

    def test_common_parser_has_dry_run(self):
        """Shared parser should accept --dry-run."""
        parser = _build_common_parser()
        args = parser.parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_common_parser_defaults(self):
        """All common args should default to None/False."""
        parser = _build_common_parser()
        args = parser.parse_args([])
        assert args.owner is None
        assert args.repo is None
        assert args.repo_dir is None
        assert args.dry_run is False
        assert args.non_interactive is False


class TestMainEntryPoint:
    """Test the main() function with various argv inputs."""

    def test_version_flag(self, capsys):
        """--version should print version and exit 0."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "ghtraf" in captured.out

    def test_help_flag(self, capsys):
        """--help should print help and exit 0."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "create" in captured.out

    def test_no_args_shows_help(self, capsys):
        """Bare 'ghtraf' with no args should show help and return 0."""
        result = main([])
        assert result == 0
        captured = capsys.readouterr()
        assert "create" in captured.out

    def test_main_accepts_argv_list(self):
        """main(argv) should accept a list (DazzleCMD compatibility)."""
        # Just verify it doesn't crash with an argv list
        result = main([])
        assert result == 0

    def test_create_help(self, capsys):
        """'ghtraf create --help' should show create-specific args."""
        with pytest.raises(SystemExit) as exc_info:
            main(["create", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "--configure" in captured.out
        assert "--skip-variables" in captured.out

    def test_unknown_subcommand_fails(self):
        """Unknown subcommand should exit non-zero."""
        with pytest.raises(SystemExit) as exc_info:
            main(["nonexistent"])
        assert exc_info.value.code != 0

    def test_global_flags_merge_into_subcommand(self, mock_gh, capsys):
        """Global flags like --verbose should be accessible after dispatch."""
        # --verbose is extracted globally; verify it reaches the subcommand args
        result = main([
            "--verbose",
            "create",
            "--dry-run",
            "--non-interactive",
            "--owner", "testorg",
            "--repo", "testrepo",
            "--created", "2026-01-01",
        ])
        assert result == 0

    def test_subcommand_returning_nonzero(self, mock_gh):
        """When a subcommand returns non-zero, main() should propagate it."""
        # create with missing required args in non-interactive returns 1
        result = main([
            "create",
            "--non-interactive",
            "--repo", "testrepo",
            "--created", "2026-01-01",
            # --owner deliberately omitted
        ])
        assert result == 1


class TestEntryPoints:
    """Test the actual installed CLI entry points via subprocess.

    These verify that pyproject.toml console_scripts, __main__.py,
    and the alias entry point all work as installed binaries.
    """

    def test_ghtraf_version(self):
        """'ghtraf --version' should print version and exit 0."""
        result = subprocess.run(
            ["ghtraf", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "ghtraf" in result.stdout

    def test_ghtraf_help(self):
        """'ghtraf --help' should list subcommands."""
        result = subprocess.run(
            ["ghtraf", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "create" in result.stdout

    def test_ghtraf_no_args(self):
        """'ghtraf' with no args should show help and exit 0."""
        result = subprocess.run(
            ["ghtraf"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "create" in result.stdout

    def test_python_m_ghtraf(self):
        """'python -m ghtraf --version' should work via __main__.py."""
        result = subprocess.run(
            [sys.executable, "-m", "ghtraf", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "ghtraf" in result.stdout

    def test_alias_entry_point(self):
        """'github-traffic-tracker --version' alias should work."""
        result = subprocess.run(
            ["github-traffic-tracker", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "ghtraf" in result.stdout

    def test_ghtraf_create_dry_run(self):
        """'ghtraf create --dry-run' end-to-end as a real process."""
        result = subprocess.run(
            ["ghtraf", "create",
             "--dry-run", "--non-interactive",
             "--owner", "testorg",
             "--repo", "testrepo",
             "--created", "2026-01-01"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "DRY RUN" in result.stdout
        assert "testorg" in result.stdout

    def test_ghtraf_create_help(self):
        """'ghtraf create --help' should show create-specific flags."""
        result = subprocess.run(
            ["ghtraf", "create", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--configure" in result.stdout
        assert "--skip-variables" in result.stdout
