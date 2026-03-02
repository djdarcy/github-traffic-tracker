"""GTT-specific channel definitions for the THAC0 verbosity system.

This file configures the generic log_lib channel infrastructure with
channels specific to github-traffic-tracker. It is the project-level
configuration that keeps log_lib itself project-agnostic.

Channel FD defaults:
    general, hint → stdout   (user-facing messages)
    everything else → stderr  (diagnostic/error output)

Usage:
    from ghtraf.channels import GTT_CHANNELS, GTT_CHANNEL_DESCRIPTIONS
    from ghtraf.channels import configure_gtt_channels, format_gtt_channel_list
"""

from ghtraf.lib.log_lib import channels as _ch


# GTT channel set
GTT_CHANNELS = {
    'api',          # GitHub API calls and responses
    'config',       # Configuration loading and resolution
    'gist',         # Gist operations (create, read, update)
    'setup',        # Setup and initialization steps
    'general',      # Default channel
    'hint',         # Contextual tips and suggestions
    'error',        # Error messages
    'trace',        # Function tracing (@trace decorator)
}

GTT_CHANNEL_DESCRIPTIONS = {
    'api':      'GitHub API calls and responses',
    'config':   'Configuration loading and resolution',
    'gist':     'Gist operations (create, read, update)',
    'setup':    'Setup and initialization steps',
    'general':  'General output',
    'hint':     'Contextual tips and suggestions',
    'error':    'Error messages',
    'trace':    'Function call tracing',
}

GTT_OPT_IN_CHANNELS = {
    'trace',    # Function call tracing — opt-in (verbose debug output)
}

# Channel FD defaults: which file handle each channel writes to.
# general and hint are user-facing → stdout.
# Everything else (api, config, gist, setup, error, trace) → stderr (manager default).
#
# String sentinels ('stdout', 'stderr') are resolved dynamically at emit time
# to the current sys.stdout/sys.stderr. This is necessary because test
# frameworks (pytest capsys) replace sys.stdout at runtime.
GTT_CHANNEL_FDS = {
    'general':  'stdout',
    'hint':     'stdout',
}


def configure_gtt_channels():
    """Override log_lib's default channels with GTT-specific set.

    Call once at startup before init_output(). Returns the channel FD
    mapping so the caller can pass it to init_output(channel_fds=...).

    Returns:
        dict mapping channel names to their default file handles
    """
    _ch.KNOWN_CHANNELS = GTT_CHANNELS
    _ch.CHANNEL_DESCRIPTIONS = GTT_CHANNEL_DESCRIPTIONS
    _ch.OPT_IN_CHANNELS = GTT_OPT_IN_CHANNELS
    return GTT_CHANNEL_FDS


def format_gtt_channel_list() -> str:
    """Format GTT channels for --show listing."""
    lines = ["Available channels:"]
    max_name = max(len(name) for name in GTT_CHANNELS)
    for name in sorted(GTT_CHANNELS):
        desc = GTT_CHANNEL_DESCRIPTIONS.get(name, '')
        opt_in = " (opt-in)" if name in GTT_OPT_IN_CHANNELS else ""
        lines.append(f"  {name:<{max_name}}  {desc}{opt_in}")
    return "\n".join(lines)
