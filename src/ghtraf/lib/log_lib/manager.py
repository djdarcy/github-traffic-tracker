"""
OutputManager — the THAC0 verbosity system core.

Central coordinator for verbosity-gated output with per-channel overrides.
The emit rule is: message shows when message.level <= threshold.
The threshold is either a per-channel override or the global verbosity.

THAC0 axis:
    ←── quieter ────────── default ────────── louder ──→
    -4    -3     -2     -1     0     1      2      3
    wall  errors warnings minimal default timing config debug

    -v increments, -Q decrements. They compose: -vv -Q = 1

Per-channel overrides:
    --show timing:2    pins timing channel to threshold 2
    Specific > generic, except at -4 (hard wall, nothing at all)

Issue refs: #31 (multi-level verbosity), #57 (structured hints),
            #65 (named channels, THAC0 model)
"""

import sys
from typing import Any, Dict, Optional, Set, TextIO

from .hints import get_hint
from .channels import parse_channel_spec, OPT_IN_CHANNELS


class OutputManager:
    """Central coordinator for THAC0 verbosity-gated output.

    All output is written to the configured file handle (default: stderr).
    The manager tracks which hints have been shown to avoid repetition
    within a single session.

    Usage::

        out = OutputManager(verbosity=1)
        out.emit(1, "Loaded {count} items", channel='config', count=42)
        out.hint('module.some_hint', 'result', var="value")
        out.progress(100, 3.2)
        out.error("Something went wrong")
    """

    def __init__(
        self,
        verbosity: int = 0,
        channel_overrides: Dict[str, int] = None,
        file: TextIO = None,
        quiet: bool = False,
    ):
        # Backward compat: quiet=True forces verbosity negative
        if quiet and verbosity >= 0:
            verbosity = -1
        self.verbosity = verbosity
        self.channel_overrides: Dict[str, int] = dict(channel_overrides or {})
        self.file = file if file is not None else sys.stderr
        self._shown_hints: Set[str] = set()

    def emit(self, level: int, message: str, *,
             channel: str = 'general', **kwargs: Any) -> None:
        """Emit a message if level <= threshold for that channel.

        The threshold is the per-channel override if set, otherwise
        the global verbosity. At threshold -4 (hard wall), nothing
        is emitted regardless of level.

        Args:
            level: Message level (higher = more verbose)
            message: Format string (uses str.format with kwargs)
            channel: Output channel name
            **kwargs: Values for template placeholders
        """
        threshold = self.channel_overrides.get(channel, self.verbosity)
        if threshold <= -4:
            return
        if level > threshold:
            return
        text = message.format(**kwargs) if kwargs else message
        print(text, file=self.file)

    def hint(self, hint_id: str, context: str = 'result', **kwargs: Any) -> None:
        """Show a hint if appropriate for context, level, and not yet shown.

        Two filters apply:
        1. Context filter: Is this hint relevant now? ('error', 'result', 'verbose')
        2. Level filter: Delegated to emit() via THAC0 threshold check.

        Args:
            hint_id: Registry key for the hint
            context: Current context ('error', 'result', 'verbose')
            **kwargs: Values for template placeholders in hint message
        """
        if hint_id in self._shown_hints:
            return
        h = get_hint(hint_id)
        if h is None:
            return
        if context not in h.context:
            return

        # Build the text before checking threshold (needed for dedup tracking)
        text = h.message.format(**kwargs) if kwargs else h.message

        # Level check via THAC0 threshold
        threshold = self.channel_overrides.get('hint', self.verbosity)
        if threshold <= -4:
            return
        if h.min_level > threshold:
            return

        print(text, file=self.file)
        self._shown_hints.add(hint_id)

    def progress(self, count: int, elapsed: float) -> None:
        """Emit a progress update (level 1, progress channel)."""
        self.emit(1, "  ... {count} results ({elapsed:.1f}s)",
                  channel='progress', count=count, elapsed=elapsed)

    def error(self, message: str) -> None:
        """Emit an error message (level -3, shown unless at hard wall).

        In the THAC0 model, errors are just emit(-3, ...). They show
        at any verbosity >= -3 (i.e., everything except -QQQQ).
        """
        self.emit(-3, message, channel='error')

    def channel_active(self, channel: str) -> bool:
        """Check if a channel would display messages at its default level.

        Returns True if a level-0 message on this channel would be shown.
        Used by callers to gate expensive operations (e.g., vals capture).

        Args:
            channel: Channel name to check

        Returns:
            True if the channel is active
        """
        threshold = self.channel_overrides.get(channel, self.verbosity)
        return threshold > -4 and 0 <= threshold

    @property
    def quiet(self) -> bool:
        """Backward compat: True when verbosity is negative."""
        return self.verbosity < 0

    @property
    def shown_hints(self) -> Set[str]:
        """Set of hint IDs that have been displayed this session."""
        return self._shown_hints.copy()


# =============================================================================
# Module-level singleton
# =============================================================================

_manager: Optional[OutputManager] = None


def init_output(verbosity: int = 0, quiet: bool = False,
                channels: list = None) -> OutputManager:
    """Initialize the module-level OutputManager singleton.

    Call once at program startup after parsing CLI arguments.

    Args:
        verbosity: THAC0 verbosity level (0=default, positive=verbose, negative=quiet)
        quiet: Legacy backward compat — if True, sets verbosity to min(verbosity, -1)
        channels: List of channel spec strings (e.g., ['timing:2', 'vals'])

    Returns:
        The initialized OutputManager instance
    """
    global _manager

    # Backward compat: quiet=True means at least -1
    if quiet and verbosity >= 0:
        verbosity = -1

    # Apply opt-in channel defaults (off unless explicitly enabled)
    channel_overrides = {ch: -1 for ch in OPT_IN_CHANNELS}

    # Parse explicit channel specs (override opt-in defaults)
    if channels:
        for spec in channels:
            cfg = parse_channel_spec(spec)
            channel_overrides[cfg.name] = cfg.level

    _manager = OutputManager(
        verbosity=verbosity,
        channel_overrides=channel_overrides,
    )
    return _manager


def get_output() -> OutputManager:
    """Get the module-level OutputManager, creating a default if needed."""
    global _manager
    if _manager is None:
        _manager = OutputManager()
    return _manager
