"""Tests for ghtraf._version — PEP 440 compliance and version parsing."""

import re

from ghtraf._version import (
    BASE_VERSION,
    MAJOR, MINOR, PATCH, PHASE,
    PIP_VERSION,
    VERSION,
    get_base_version,
    get_pip_version,
    get_version,
)


def test_base_version_format():
    """Base version should be MAJOR.MINOR.PATCH-PHASE."""
    base = get_base_version()
    assert re.match(r"^\d+\.\d+\.\d+(-\w+)?$", base), \
        f"Unexpected base version format: {base}"


def test_base_version_matches_components():
    """Base version should match the MAJOR.MINOR.PATCH constants."""
    base = get_base_version()
    expected_prefix = f"{MAJOR}.{MINOR}.{PATCH}"
    assert base.startswith(expected_prefix), \
        f"Base {base} doesn't start with {expected_prefix}"


def test_pip_version_pep440():
    """PIP version must be PEP 440 compliant (no hyphens, proper pre-release)."""
    pip_ver = get_pip_version()
    # PEP 440: N.N.N[{a|b|rc}N][.devN][+local]
    assert "-" not in pip_ver, \
        f"PEP 440 forbids hyphens in version: {pip_ver}"
    assert re.match(r"^\d+\.\d+\.\d+", pip_ver), \
        f"PIP version doesn't start with N.N.N: {pip_ver}"


def test_pip_version_alpha_mapping():
    """Alpha phase should map to 'a0' in PEP 440."""
    if PHASE == "alpha":
        pip_ver = get_pip_version()
        assert "a0" in pip_ver, \
            f"Alpha phase should produce 'a0' suffix: {pip_ver}"


def test_full_version_has_branch():
    """Full version string should contain branch info."""
    full = get_version()
    # Format: 0.2.0-alpha_main_3-20260226-b0c9d31
    assert "_" in full, \
        f"Full version should have underscore separators: {full}"


def test_module_level_constants():
    """Module-level constants should be pre-computed and non-empty."""
    assert VERSION, "VERSION constant is empty"
    assert BASE_VERSION, "BASE_VERSION constant is empty"
    assert PIP_VERSION, "PIP_VERSION constant is empty"


def test_pip_version_no_phase():
    """When PHASE is None, PIP version should be plain N.N.N."""
    # We can't easily test this without monkeypatching the module,
    # but we can verify the current state is consistent
    pip_ver = get_pip_version()
    if PHASE is None:
        assert re.match(r"^\d+\.\d+\.\d+$", pip_ver), \
            f"No phase should give plain version: {pip_ver}"
