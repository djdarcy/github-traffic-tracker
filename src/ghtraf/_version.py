"""
Version information for ghtraf (GitHub Traffic Tracker CLI).

This file is the canonical source for version numbers.
The __version__ string is automatically updated by git hooks
with build metadata (branch, build number, date, commit hash).

Format: MAJOR.MINOR.PATCH[-PHASE]_BRANCH_BUILD-YYYYMMDD-COMMITHASH
Example: 0.2.0-alpha_main_4-20260226-a1b2c3d4
"""

# Version components - edit these for version bumps
MAJOR = 0
MINOR = 2
PATCH = 0
PHASE = "alpha"  # Per-MINOR feature set: None, "alpha", "beta", "rc1", etc.

# Auto-updated by git hooks - do not edit manually
__version__ = "0.2.0-alpha_main_3-20260226-b0c9d31"
__app_name__ = "ghtraf"


def get_version():
    """Return the full version string including branch and build info."""
    return __version__


def get_base_version():
    """Return the semantic version string (MAJOR.MINOR.PATCH[-PHASE])."""
    if "_" in __version__:
        return __version__.split("_")[0]
    base = f"{MAJOR}.{MINOR}.{PATCH}"
    if PHASE:
        base = f"{base}-{PHASE}"
    return base


def get_pip_version():
    """
    Return PEP 440 compliant version for pip/setuptools.

    Converts our version format to PEP 440:
    - Main branch: 0.2.0-alpha_main_3-20260226-hash -> 0.2.0a0
    - Dev branch: 0.2.0-alpha_dev_3-20260226-hash -> 0.2.0a0.dev3
    """
    base = f"{MAJOR}.{MINOR}.{PATCH}"

    # Map phase to PEP 440 pre-release segment
    phase_map = {"alpha": "a0", "beta": "b0"}
    if PHASE:
        base += phase_map.get(PHASE, PHASE)

    if "_" not in __version__:
        return base

    parts = __version__.split("_")
    branch = parts[1] if len(parts) > 1 else "unknown"

    if branch == "main":
        return base
    else:
        build_info = "_".join(parts[2:]) if len(parts) > 2 else ""
        build_num = build_info.split("-")[0] if "-" in build_info else "0"
        return f"{base}.dev{build_num}"


# For convenience in imports
VERSION = get_version()
BASE_VERSION = get_base_version()
PIP_VERSION = get_pip_version()
