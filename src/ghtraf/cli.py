"""Main CLI entry point for ghtraf.

Implements a Docker-style two-pass argument parser:
  1. First pass: extract global flags (--verbose, --no-color, --config)
  2. Second pass: dispatch to subcommand with shared parent args

Global flags can appear before OR after the subcommand:
  ghtraf --verbose create --owner X      # works
  ghtraf create --owner X --verbose      # also works

Subcommands self-register via register(subparsers, parents) convention.
"""

import argparse
import sys

from ghtraf._version import BASE_VERSION, VERSION


# ---------------------------------------------------------------------------
# Global flags (Docker-style: can precede the subcommand)
# ---------------------------------------------------------------------------
GLOBAL_FLAGS = {
    "--verbose": {"aliases": ["-v"], "action": "count", "default": 0,
                  "help": "Increase verbosity (-v, -vv, -vvv)"},
    "--quiet": {"aliases": ["-Q"], "action": "count", "default": 0,
                "help": "Decrease verbosity (-Q, -QQ, -QQQ, -QQQQ=silent)"},
    "--show": {"nargs": "?", "action": "append", "metavar": "CHANNEL[:LEVEL]",
               "help": "Show output channel (bare --show lists channels)"},
    "--no-color": {"action": "store_true", "default": False,
                   "help": "Disable colored output"},
    "--config": {"metavar": "PATH", "default": None,
                 "help": "Path to config file (default: ~/.ghtraf/config.json)"},
}


def _extract_global_flags(argv):
    """Two-pass parse: pull global flags from anywhere in argv.

    Returns (global_namespace, remaining_argv).
    """
    global_parser = argparse.ArgumentParser(add_help=False)
    for flag, kwargs in GLOBAL_FLAGS.items():
        aliases = kwargs.pop("aliases", [])
        global_parser.add_argument(flag, *aliases, **kwargs)
        if aliases:
            kwargs["aliases"] = aliases  # restore for reuse

    global_args, remaining = global_parser.parse_known_args(argv)
    return global_args, remaining


# ---------------------------------------------------------------------------
# Shared parent parser (inherited by all subcommands via parents=[])
# ---------------------------------------------------------------------------
def _build_common_parser():
    """Build the shared argument parser for repo-scoped flags.

    These are inherited by every subcommand — defined once, zero duplication.
    """
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--owner", metavar="NAME",
                        help="GitHub username or organization")
    common.add_argument("--repo", metavar="NAME",
                        help="Repository name")
    common.add_argument("--repo-dir", metavar="PATH",
                        help="Local repository directory")
    common.add_argument("--dry-run", action="store_true", default=False,
                        help="Preview changes without applying them")
    common.add_argument("--non-interactive", action="store_true", default=False,
                        help="Never prompt — fail on missing required values")
    return common


# ---------------------------------------------------------------------------
# Subcommand discovery and registration
# ---------------------------------------------------------------------------
def _discover_commands():
    """Import and return all command modules.

    Each module in ghtraf.commands must export:
      register(subparsers, parents) — add itself to the subparser
      run(args, global_args) — execute the command
    """
    from ghtraf.commands import create, init
    # Future commands added here:
    # from ghtraf.commands import status, list_cmd, upgrade, verify
    return [create, init]


def _build_parser(commands, common_parser):
    """Build the main argparse parser with subcommand dispatch."""
    parser = argparse.ArgumentParser(
        prog="ghtraf",
        description="ghtraf — GitHub Traffic Tracker CLI",
        epilog=(
            "Run 'ghtraf <command> --help' for details on a specific command.\n"
            "\n"
            "Global flags (--verbose, --no-color, --config) can appear\n"
            "before or after the subcommand."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"ghtraf {BASE_VERSION} ({VERSION})",
    )

    # Add global flags to main parser too (for --help display)
    for flag, kwargs in GLOBAL_FLAGS.items():
        kw = {k: v for k, v in kwargs.items() if k != "aliases"}
        aliases = kwargs.get("aliases", [])
        parser.add_argument(flag, *aliases, **kw)

    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        metavar="<command>",
    )

    # Let each command register itself
    for cmd_module in commands:
        cmd_module.register(subparsers, parents=[common_parser])

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv=None):
    """Main entry point for ghtraf CLI.

    Args:
        argv: Command-line arguments. None means sys.argv[1:].
              Accepts a list for DazzleCMD integration.

    Returns:
        Exit code (0 = success).
    """
    if argv is None:
        argv = sys.argv[1:]

    # Pass 1: extract global flags from anywhere in the arg list
    global_args, remaining = _extract_global_flags(argv)

    # Handle bare --show (list channels and exit)
    if global_args.show and None in global_args.show:
        from ghtraf.channels import format_gtt_channel_list
        print(format_gtt_channel_list())
        return 0

    # Initialize THAC0 output system
    verbosity = (global_args.verbose or 0) - (global_args.quiet or 0)
    channels = [s for s in (global_args.show or []) if s is not None]
    from ghtraf.channels import configure_gtt_channels
    from ghtraf.lib.log_lib import init_output
    configure_gtt_channels()
    init_output(verbosity=verbosity, channels=channels)
    import ghtraf.hints  # noqa: F401 — register GTT hints

    # Pass 2: parse subcommand + shared/specific args
    common_parser = _build_common_parser()
    commands = _discover_commands()
    parser = _build_parser(commands, common_parser)

    # If no args at all, print help
    if not remaining:
        parser.print_help()
        return 0

    args = parser.parse_args(remaining)

    # If subcommand selected but no handler, print help
    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    # Merge global args into the namespace for convenience
    for key, value in vars(global_args).items():
        if key not in vars(args) or getattr(args, key) is None:
            setattr(args, key, value)

    # Dispatch
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1


if __name__ == "__main__":
    sys.exit(main())
