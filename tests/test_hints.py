"""Tests for ghtraf.hints — GTT domain-specific hints."""

import io

import pytest

from ghtraf.lib.log_lib import get_hint, OutputManager, init_output
from ghtraf.lib.log_lib import manager as _manager_mod


@pytest.fixture(autouse=True)
def _reset_manager():
    """Reset OutputManager singleton between tests."""
    old = _manager_mod._manager
    yield
    _manager_mod._manager = old


@pytest.fixture(autouse=True)
def _import_hints():
    """Ensure GTT hints are registered."""
    import ghtraf.hints  # noqa: F401


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------
class TestHintsRegistered:
    """All GTT hints are registered in the global registry."""

    @pytest.mark.parametrize("hint_id", [
        'setup.dry_run',
        'setup.configure',
        'api.rate_limit',
        'config.remember',
        'setup.pat',
    ])
    def test_hint_exists(self, hint_id):
        h = get_hint(hint_id)
        assert h is not None, f"Hint '{hint_id}' not registered"
        assert h.id == hint_id

    def test_setup_hints_have_correct_category(self):
        for hint_id in ['setup.dry_run', 'setup.configure', 'setup.pat']:
            assert get_hint(hint_id).category == 'setup'

    def test_api_hint_has_correct_category(self):
        assert get_hint('api.rate_limit').category == 'api'

    def test_config_hint_has_correct_category(self):
        assert get_hint('config.remember').category == 'config'


# ---------------------------------------------------------------------------
# Context and level tests
# ---------------------------------------------------------------------------
class TestHintFiringInContext:
    """Hints fire in appropriate contexts and respect THAC0."""

    def test_result_hint_shows_at_default(self):
        """Result-context hints (min_level=0) fire at verbosity 0."""
        buf = io.StringIO()
        out = OutputManager(verbosity=0, file=buf)
        out.hint('config.remember', 'result')
        assert 'ghtraf remembers' in buf.getvalue()

    def test_verbose_hint_hidden_at_default(self):
        """Verbose-context hints (min_level=1) hidden at verbosity 0."""
        buf = io.StringIO()
        out = OutputManager(verbosity=0, file=buf)
        out.hint('api.rate_limit', 'verbose')
        assert buf.getvalue() == ""

    def test_verbose_hint_shows_at_v1(self):
        """Verbose-context hints show at verbosity 1."""
        buf = io.StringIO()
        out = OutputManager(verbosity=1, file=buf)
        out.hint('api.rate_limit', 'verbose')
        assert 'rate limit' in buf.getvalue()

    def test_hint_dedup(self):
        """Same hint only fires once per session."""
        buf = io.StringIO()
        out = OutputManager(verbosity=0, file=buf)
        out.hint('config.remember', 'result')
        first_len = len(buf.getvalue())
        out.hint('config.remember', 'result')
        assert len(buf.getvalue()) == first_len

    def test_hint_suppressed_at_hard_wall(self):
        """Hints are suppressed at hard wall (-4)."""
        buf = io.StringIO()
        out = OutputManager(verbosity=-4, file=buf)
        out.hint('config.remember', 'result')
        assert buf.getvalue() == ""
