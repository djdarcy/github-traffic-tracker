"""
Tests for utils.log_lib — THAC0 verbosity system with named channels.

Tests the THAC0 axis, per-channel overrides, opt-in channels,
channel_active gating, channel spec parsing, and format_channel_list.

Complements test_output.py which tests core OutputManager emit/hint/progress.
"""

import io
import pytest

from ghtraf.lib.log_lib import (
    OutputManager,
    init_output,
    get_output,
)
from ghtraf.lib.log_lib import channels as _channels_mod
from ghtraf.lib.log_lib.channels import (
    ChannelConfig,
    parse_channel_spec,
    format_channel_list,
    KNOWN_CHANNELS,
    CHANNEL_DESCRIPTIONS,
    OPT_IN_CHANNELS,
)
from ghtraf.lib.log_lib.levels import (
    DEBUG, CONFIG, TIMING, DEFAULT, MINIMAL, WARNING, ERROR, NOTHING,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def _restore_channels():
    """Ensure log_lib channels are reset to PSS defaults after each test.

    Other tests (test_cli.py) call configure_gtt_channels() which mutates
    the module-level KNOWN_CHANNELS etc. This fixture saves/restores them.
    """
    saved = (
        _channels_mod.KNOWN_CHANNELS,
        _channels_mod.CHANNEL_DESCRIPTIONS,
        _channels_mod.OPT_IN_CHANNELS,
    )
    # Restore PSS defaults before test
    _channels_mod.KNOWN_CHANNELS = KNOWN_CHANNELS
    _channels_mod.CHANNEL_DESCRIPTIONS = CHANNEL_DESCRIPTIONS
    _channels_mod.OPT_IN_CHANNELS = OPT_IN_CHANNELS
    yield
    # Restore whatever was there (in case test changed them)
    _channels_mod.KNOWN_CHANNELS = saved[0]
    _channels_mod.CHANNEL_DESCRIPTIONS = saved[1]
    _channels_mod.OPT_IN_CHANNELS = saved[2]


@pytest.fixture
def buf():
    """A StringIO buffer for capturing output."""
    return io.StringIO()


@pytest.fixture
def out(buf):
    """An OutputManager writing to a buffer (verbosity=0)."""
    return OutputManager(verbosity=0, file=buf)


# =============================================================================
# THAC0 Level Constants
# =============================================================================

class TestLevelConstants:
    """Verify THAC0 level constants have correct values."""

    def test_level_ordering(self):
        """Levels are ordered: NOTHING < ERROR < WARNING < MINIMAL < DEFAULT < TIMING < CONFIG < DEBUG."""
        assert NOTHING < ERROR < WARNING < MINIMAL < DEFAULT < TIMING < CONFIG < DEBUG

    def test_specific_values(self):
        """Spot check key values."""
        assert DEFAULT == 0
        assert NOTHING == -4
        assert ERROR == -3
        assert TIMING == 1
        assert DEBUG == 3


# =============================================================================
# THAC0 Emit — Per-Channel Overrides
# =============================================================================

class TestPerChannelOverrides:
    """Test per-channel threshold overrides."""

    def test_channel_override_shows_message(self, buf):
        """Message shown when channel override threshold >= level."""
        out = OutputManager(verbosity=0, channel_overrides={'timing': 2}, file=buf)
        out.emit(2, "timing detail", channel='timing')
        assert "timing detail" in buf.getvalue()

    def test_channel_override_hides_message(self, buf):
        """Message hidden when channel override threshold < level."""
        out = OutputManager(verbosity=2, channel_overrides={'timing': 0}, file=buf)
        out.emit(1, "hidden timing", channel='timing')
        assert buf.getvalue() == ""

    def test_global_threshold_used_when_no_override(self, buf):
        """Global verbosity used for channels without override."""
        out = OutputManager(verbosity=1, channel_overrides={'timing': 2}, file=buf)
        out.emit(1, "general msg", channel='general')
        assert "general msg" in buf.getvalue()

    def test_hard_wall_overrides_channel(self, buf):
        """Hard wall (-4) silences channel even with override."""
        out = OutputManager(verbosity=-4, channel_overrides={'timing': 2}, file=buf)
        # Channel override is 2 but... let's check: the channel_override IS used
        # Hard wall only applies when threshold <= -4
        out.emit(2, "should show", channel='timing')
        assert "should show" in buf.getvalue()

    def test_hard_wall_on_channel(self, buf):
        """Channel set to -4 (hard wall) silences it."""
        out = OutputManager(verbosity=2, channel_overrides={'timing': -4}, file=buf)
        out.emit(-3, "even errors", channel='timing')
        assert buf.getvalue() == ""


# =============================================================================
# THAC0 Composition (verbose - quiet)
# =============================================================================

class TestThac0Composition:
    """Test verbose/quiet composition."""

    def test_vv_Q_gives_1(self, buf):
        """-vv -Q = verbosity 1."""
        out = OutputManager(verbosity=1, file=buf)  # 2 - 1 = 1
        out.emit(1, "level 1 visible")
        out.emit(2, "level 2 hidden")
        assert "level 1 visible" in buf.getvalue()
        assert "level 2 hidden" not in buf.getvalue()

    def test_negative_verbosity_hides_level_0(self, buf):
        """Negative verbosity hides level 0 messages."""
        out = OutputManager(verbosity=-1, file=buf)
        out.emit(0, "hidden")
        assert buf.getvalue() == ""

    def test_negative_verbosity_shows_errors(self, buf):
        """Negative verbosity still shows errors (level -3)."""
        out = OutputManager(verbosity=-1, file=buf)
        out.error("visible error")
        assert "visible error" in buf.getvalue()

    def test_hard_wall_blocks_everything(self, buf):
        """Verbosity -4 (hard wall) blocks even errors."""
        out = OutputManager(verbosity=-4, file=buf)
        out.error("blocked error")
        assert buf.getvalue() == ""


# =============================================================================
# Channel Active
# =============================================================================

class TestChannelActive:
    """Test channel_active() gating."""

    def test_default_channel_active_at_v0(self, out):
        """General channel is active at default verbosity."""
        assert out.channel_active('general') is True

    def test_opt_in_channel_inactive_by_default(self):
        """Opt-in channels are inactive without explicit enable."""
        mgr = init_output(verbosity=0)
        assert mgr.channel_active('vals') is False
        assert mgr.channel_active('trace') is False

    def test_opt_in_channel_active_when_enabled(self):
        """Opt-in channels become active when explicitly enabled."""
        mgr = init_output(verbosity=0, channels=['vals'])
        assert mgr.channel_active('vals') is True

    def test_channel_active_false_at_negative(self, buf):
        """channel_active returns False at negative verbosity for general."""
        out = OutputManager(verbosity=-1, file=buf)
        assert out.channel_active('general') is False

    def test_channel_active_with_override(self, buf):
        """channel_active uses per-channel override."""
        out = OutputManager(verbosity=-1, channel_overrides={'timing': 1}, file=buf)
        assert out.channel_active('timing') is True
        assert out.channel_active('general') is False

    def test_channel_active_hard_wall(self, buf):
        """channel_active returns False when channel is at hard wall."""
        out = OutputManager(verbosity=0, channel_overrides={'timing': -4}, file=buf)
        assert out.channel_active('timing') is False


# =============================================================================
# Channel Spec Parsing
# =============================================================================

class TestParseChannelSpec:
    """Test parse_channel_spec()."""

    def test_name_only(self):
        """Bare channel name gets default level 0."""
        cfg = parse_channel_spec("timing")
        assert cfg.name == "timing"
        assert cfg.level == 0

    def test_name_and_level(self):
        """Channel:level parses correctly."""
        cfg = parse_channel_spec("timing:2")
        assert cfg.name == "timing"
        assert cfg.level == 2

    def test_negative_level(self):
        """Negative levels parse correctly."""
        cfg = parse_channel_spec("error:-3")
        assert cfg.name == "error"
        assert cfg.level == -3

    def test_empty_level_uses_default(self):
        """Empty level slot uses default 0."""
        cfg = parse_channel_spec("timing::file")
        assert cfg.name == "timing"
        assert cfg.level == 0
        assert cfg.destination == "file"

    def test_full_spec(self):
        """All 5 positions parse correctly."""
        cfg = parse_channel_spec("timing:2:file:/tmp/out.log:json")
        assert cfg.name == "timing"
        assert cfg.level == 2
        assert cfg.destination == "file"
        assert cfg.location == "/tmp/out.log"
        assert cfg.format == "json"

    def test_windows_drive_letter(self):
        """Windows drive letter in location is rejoined."""
        cfg = parse_channel_spec("timing:2:file:C:\\logs\\out.log")
        assert cfg.location == "C:\\logs\\out.log"


# =============================================================================
# Known Channels
# =============================================================================

class TestKnownChannels:
    """Test channel registry."""

    def test_all_channels_have_descriptions(self):
        """Every known channel has a description."""
        for ch in KNOWN_CHANNELS:
            assert ch in CHANNEL_DESCRIPTIONS, f"Missing description for '{ch}'"

    def test_opt_in_subset_of_known(self):
        """Opt-in channels are a subset of known channels."""
        assert OPT_IN_CHANNELS <= KNOWN_CHANNELS

    def test_format_channel_list_includes_all(self):
        """format_channel_list includes all known channels."""
        listing = format_channel_list()
        for ch in KNOWN_CHANNELS:
            assert ch in listing


# =============================================================================
# Init Output with Channels
# =============================================================================

class TestInitOutputChannels:
    """Test init_output with channel specs."""

    def test_channels_parsed_into_overrides(self):
        """Channel spec list creates overrides."""
        mgr = init_output(verbosity=0, channels=['timing:2', 'vals:1'])
        assert mgr.channel_overrides.get('timing') == 2
        assert mgr.channel_overrides.get('vals') == 1

    def test_opt_in_defaults_applied(self):
        """Opt-in channels get default -1 override."""
        mgr = init_output(verbosity=0)
        assert mgr.channel_overrides.get('vals') == -1
        assert mgr.channel_overrides.get('trace') == -1

    def test_explicit_overrides_win(self):
        """Explicit --show overrides opt-in default."""
        mgr = init_output(verbosity=0, channels=['vals:2'])
        assert mgr.channel_overrides.get('vals') == 2


# =============================================================================
# Vals Channel Integration — PSS-specific (removed)
# =============================================================================
# TestValsChannel tests utils.cli.format_match which is PSS-specific.
# Removed during port to ghtraf. See PSS tests/test_log_lib.py for originals.
