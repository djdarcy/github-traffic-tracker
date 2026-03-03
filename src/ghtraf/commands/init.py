"""Deprecated: use 'ghtraf create --files-only' instead.

The init functionality has been merged into the create command.
This module exists only as a re-export shim for backward compatibility.
"""

# Re-exports so any stale imports from ghtraf.commands.init still resolve
from ghtraf.commands.create import (  # noqa: F401
    TEMPLATE_FILES,
    _discover_repo_dir,
    _get_template_root,
    _prompt_overwrite,
)
