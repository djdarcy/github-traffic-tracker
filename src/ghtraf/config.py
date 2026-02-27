"""Configuration management for ghtraf.

Three-layer config resolution (highest priority wins):
  1. CLI flags — explicit on the command line
  2. Project config — .ghtraf.json in the repo directory
  3. Global config — ~/.ghtraf/config.json

This means once you run `ghtraf create --owner myorg --repo myproject`,
the project config remembers it. Future commands need zero flags.
"""

import json
import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Config file locations
# ---------------------------------------------------------------------------
def get_global_config_dir():
    """Return the global config directory (~/.ghtraf/)."""
    return Path.home() / ".ghtraf"


def get_global_config_path():
    """Return path to the global config file."""
    return get_global_config_dir() / "config.json"


def find_project_config(start_dir=None):
    """Walk up from start_dir looking for .ghtraf.json.

    Returns the path if found, None otherwise.
    """
    current = Path(start_dir or os.getcwd()).resolve()
    for _ in range(20):  # safety limit
        candidate = current / ".ghtraf.json"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
def load_json(path):
    """Load a JSON file, returning empty dict on error."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_global_config():
    """Load the global config file."""
    return load_json(get_global_config_path())


def load_project_config(start_dir=None):
    """Load the nearest .ghtraf.json walking upward from start_dir."""
    path = find_project_config(start_dir)
    if path:
        return load_json(path), path
    return {}, None


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------
def resolve_config(args, keys=None):
    """Resolve config values using three-layer precedence.

    For each key in `keys`, checks (in order):
      1. CLI args (from argparse namespace)
      2. Project .ghtraf.json
      3. Global ~/.ghtraf/config.json

    Returns a dict with resolved values.
    """
    if keys is None:
        keys = ["owner", "repo", "repo_dir"]

    project_cfg, _ = load_project_config(
        getattr(args, "repo_dir", None)
    )
    global_cfg = load_global_config()

    # If global config tracks repos, find matching repo config
    repo_key = None
    if hasattr(args, "owner") and hasattr(args, "repo"):
        cli_owner = getattr(args, "owner", None)
        cli_repo = getattr(args, "repo", None)
        if cli_owner and cli_repo:
            repo_key = f"{cli_owner}/{cli_repo}"
    global_repo_cfg = {}
    if repo_key:
        global_repo_cfg = global_cfg.get("repos", {}).get(repo_key, {})

    resolved = {}
    for key in keys:
        # Normalize key: argparse uses underscores, JSON may use either
        arg_key = key.replace("-", "_")
        json_key = key.replace("_", "-") if "_" in key else key
        alt_json_key = key.replace("-", "_") if "-" in key else key

        # Layer 1: CLI
        cli_val = getattr(args, arg_key, None)
        if cli_val is not None:
            resolved[arg_key] = cli_val
            continue

        # Layer 2: Project config
        proj_val = project_cfg.get(json_key) or project_cfg.get(alt_json_key)
        if proj_val is not None:
            resolved[arg_key] = proj_val
            continue

        # Layer 3: Global config (repo-specific section)
        global_val = (global_repo_cfg.get(json_key)
                      or global_repo_cfg.get(alt_json_key))
        if global_val is not None:
            resolved[arg_key] = global_val
            continue

        resolved[arg_key] = None

    return resolved


# ---------------------------------------------------------------------------
# Config writing
# ---------------------------------------------------------------------------
def save_project_config(data, repo_dir=None):
    """Write .ghtraf.json to the repo directory."""
    target = Path(repo_dir or os.getcwd()) / ".ghtraf.json"
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return target


def save_global_config(data):
    """Write the global config file."""
    config_dir = get_global_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = get_global_config_path()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return config_path


def register_repo_globally(owner, repo, badge_gist_id=None,
                           archive_gist_id=None, repo_dir=None,
                           display_name=None, created=None):
    """Add or update a repo entry in the global config."""
    config = load_global_config()
    config.setdefault("version", 1)
    config.setdefault("repos", {})

    repo_key = f"{owner}/{repo}"
    entry = config["repos"].get(repo_key, {})

    if badge_gist_id:
        entry["badge_gist_id"] = badge_gist_id
    if archive_gist_id:
        entry["archive_gist_id"] = archive_gist_id
    if repo_dir:
        entry["repo_dir"] = str(repo_dir)
    if display_name:
        entry["display_name"] = display_name
    if created:
        entry["created"] = created

    config["repos"][repo_key] = entry
    save_global_config(config)
    return config
