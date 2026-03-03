"""
plan_lib.renderer — Default plan rendering implementations.

Provides DefaultTextRenderer which satisfies the PlanRenderer protocol.
Uses OutputManager for THAC0 integration when available, falls back to
print() for standalone usage.

Color support uses ANSI escape sequences (works in modern terminals).
"""

from __future__ import annotations

import sys
from typing import Optional, TextIO

from ghtraf.lib.core_lib import Action, ConflictResolution, Plan


# ── ANSI color helpers ─────────────────────────────────────────────────

def _supports_color(stream: TextIO) -> bool:
    """Check if a stream likely supports ANSI color."""
    if not hasattr(stream, "isatty"):
        return False
    if not stream.isatty():
        return False
    # Windows terminal supports ANSI since Windows 10 1511
    return True


def _color(text: str, code: str, use_color: bool) -> str:
    """Wrap text in ANSI color if enabled."""
    if not use_color:
        return text
    return f"\033[{code}m{text}\033[0m"


# ── Operation symbol mapping ──────────────────────────────────────────

# Color codes: 32=green, 33=yellow, 31=red, 90=grey, 36=cyan, 35=magenta
OP_STYLES: dict[str, tuple[str, str]] = {
    # operation -> (symbol, ansi_color_code)
    "copy":      ("[COPY]",      "32"),   # green — new resource
    "create":    ("[CREATE]",    "32"),   # green
    "INSTALL":   ("[INSTALL]",   "32"),   # green
    "set":       ("[SET]",       "36"),   # cyan — configuration
    "configure": ("[CONFIGURE]", "36"),   # cyan
    "overwrite": ("[OVERWRITE]", "33"),   # yellow — conflict change
    "UPGRADE":   ("[UPGRADE]",   "33"),   # yellow
    "REINSTALL": ("[REINSTALL]", "33"),   # yellow
    "delete":    ("[DELETE]",    "31"),   # red — destructive
    "skip":      ("[SKIP]",      "90"),   # grey — no change
    "KEEP":      ("[KEEP]",      "90"),   # grey
}

DEFAULT_STYLE: tuple[str, str] = ("[ACTION]", "0")  # no color


class DefaultTextRenderer:
    """Render a plan as color-coded text output.

    Integrates with log_lib's OutputManager for THAC0 verbosity control:
    - Level 0 (default): action lines + warnings + conflict summary
    - Level 1 (verbose): adds details dict for each action
    - Level -1 and below: suppressed per THAC0 quiet axis

    Falls back to print() when no OutputManager is provided.

    Usage:
        renderer = DefaultTextRenderer()
        renderer.render(plan)                          # print to stderr
        renderer.render(plan, output_manager=out)      # THAC0 integration
        renderer.render(plan, stream=sys.stdout)       # explicit stream
    """

    def __init__(self, *, use_color: Optional[bool] = None):
        """Initialize renderer.

        Args:
            use_color: Force color on/off. None = auto-detect from stream.
        """
        self._force_color = use_color

    def _resolve_color(self, stream: TextIO) -> bool:
        if self._force_color is not None:
            return self._force_color
        return _supports_color(stream)

    def _format_action_line(self, action: Action, use_color: bool) -> str:
        """Format a single action as one line."""
        symbol, color_code = OP_STYLES.get(
            action.operation, DEFAULT_STYLE
        )
        styled_symbol = _color(f"{symbol:>13}", color_code, use_color)

        line = f"  {styled_symbol}  {action.target}"
        if action.description:
            line += f" — {action.description}"

        # Show conflict resolution if present
        if action.conflict and action.conflict != ConflictResolution.SKIP:
            conflict_str = f"({action.conflict.value})"
            line += f" {_color(conflict_str, '33', use_color)}"

        # Flag actions that will prompt for user input
        if action.requires_input:
            line += f" {_color('[requires input]', '35', use_color)}"

        return line

    def _format_details(self, action: Action, use_color: bool) -> list[str]:
        """Format action details for verbose display."""
        lines = []
        for key, value in action.details.items():
            detail_line = f"{'':>17}{_color(key, '90', use_color)}: {value}"
            lines.append(detail_line)
        return lines

    def render(
        self,
        plan: Plan,
        output_manager=None,
        *,
        stream: Optional[TextIO] = None,
    ) -> None:
        """Render a plan for user review.

        Args:
            plan: The plan to display.
            output_manager: Optional OutputManager for THAC0 integration.
            stream: Output stream override (default: stderr, or manager's
                configured stream).
        """
        # Resolve output destination
        if stream is None:
            if output_manager is not None:
                stream = output_manager.file
            else:
                stream = sys.stderr

        use_color = self._resolve_color(stream)

        # Header
        header = f"Plan: {plan.command}"
        action_count = len(plan.actions)
        change_count = sum(1 for a in plan.actions if a.operation != "skip")
        header += f" ({change_count} change{'s' if change_count != 1 else ''}"
        header += f" / {action_count} total)"

        self._output(header, output_manager, stream, level=0, channel='setup')
        self._output("", output_manager, stream, level=0, channel='setup')

        # Action lines
        for action in plan.actions:
            line = self._format_action_line(action, use_color)
            self._output(line, output_manager, stream, level=0, channel='setup')

            # Details at verbose level
            if action.details:
                for detail_line in self._format_details(action, use_color):
                    self._output(
                        detail_line, output_manager, stream,
                        level=1, channel='setup',
                    )

        # Warnings
        if plan.warnings:
            self._output("", output_manager, stream, level=0, channel='setup')
            for warning in plan.warnings:
                warn_line = _color(f"  Warning: {warning}", "33", use_color)
                self._output(
                    warn_line, output_manager, stream,
                    level=0, channel='setup',
                )

        # Conflict summary
        if plan.has_conflicts():
            self._output("", output_manager, stream, level=0, channel='setup')
            conflicts = [
                a for a in plan.actions
                if a.conflict and a.conflict != ConflictResolution.SKIP
            ]
            summary = _color(
                f"  {len(conflicts)} conflict(s) to resolve",
                "33", use_color,
            )
            self._output(
                summary, output_manager, stream,
                level=0, channel='setup',
            )

    def _output(
        self,
        message: str,
        output_manager,
        stream: TextIO,
        *,
        level: int = 0,
        channel: str = 'general',
    ) -> None:
        """Write a line using OutputManager or print fallback."""
        if output_manager is not None:
            output_manager.emit(level, message, channel=channel)
        else:
            print(message, file=stream)
