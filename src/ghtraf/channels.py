"""GTT-specific channel definitions for the THAC0 verbosity system.

This file configures the generic log_lib channel infrastructure with
channels specific to github-traffic-tracker. It is the project-level
configuration that keeps log_lib itself project-agnostic.

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


def configure_gtt_channels():
    """Override log_lib's default channels with GTT-specific set.

    Call once at startup before init_output().
    """
    _ch.KNOWN_CHANNELS = GTT_CHANNELS
    _ch.CHANNEL_DESCRIPTIONS = GTT_CHANNEL_DESCRIPTIONS
    _ch.OPT_IN_CHANNELS = GTT_OPT_IN_CHANNELS


def format_gtt_channel_list() -> str:
    """Format GTT channels for --show listing."""
    lines = ["Available channels:"]
    max_name = max(len(name) for name in GTT_CHANNELS)
    for name in sorted(GTT_CHANNELS):
        desc = GTT_CHANNEL_DESCRIPTIONS.get(name, '')
        opt_in = " (opt-in)" if name in GTT_OPT_IN_CHANNELS else ""
        lines.append(f"  {name:<{max_name}}  {desc}{opt_in}")
    return "\n".join(lines)
