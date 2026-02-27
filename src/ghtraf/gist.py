"""Gist creation and management for ghtraf.

Handles creating the badge gist (public, 5 files) and archive gist (unlisted)
that back the traffic tracking system.
"""

import json

from ghtraf.gh import run_gh
from ghtraf.output import print_dry, print_ok


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------
def build_initial_state():
    """Build the initial empty state.json structure."""
    return {
        "totalClones": 0,
        "totalUniqueClones": 0,
        "totalDownloads": 0,
        "totalViews": 0,
        "totalUniqueViews": 0,
        "totalCiCheckouts": 0,
        "totalCiUniqueClones": 0,
        "totalOrganicUniqueClones": 0,
        "previousTotalDownloads": 0,
        "_previousCiUniqueToday": 0,
        "stars": 0,
        "forks": 0,
        "openIssues": 0,
        "lastSeenDates": [],
        "lastSeenViewDates": [],
        "dailyHistory": [],
        "ciCheckouts": {},
        "referrers": [],
        "popularPaths": [],
    }


def build_badge(label, message="0", color="blue"):
    """Build a shields.io endpoint badge JSON."""
    return {
        "schemaVersion": 1,
        "label": label,
        "message": message,
        "color": color,
    }


# ---------------------------------------------------------------------------
# Gist creation
# ---------------------------------------------------------------------------
def create_badge_gist(config, dry_run=False):
    """Create the public badge gist with initial state + badge files.

    Args:
        config: Dict with 'gh_repo' key (owner/repo).
        dry_run: If True, only print what would happen.

    Returns:
        Gist ID string (or placeholder in dry-run mode).
    """
    files = {
        "state.json": json.dumps(build_initial_state(), indent=2),
        "installs.json": json.dumps(build_badge("installs"), indent=2),
        "downloads.json": json.dumps(build_badge("downloads"), indent=2),
        "clones.json": json.dumps(build_badge("clones"), indent=2),
        "views.json": json.dumps(build_badge("views"), indent=2),
    }

    description = f"{config['gh_repo']} traffic badges"

    if dry_run:
        print_dry(f"Would create PUBLIC gist: \"{description}\"")
        for name in files:
            print(f"    - {name}")
        return "<DRY_RUN_BADGE_GIST_ID>"

    payload = json.dumps({
        "description": description,
        "public": True,
        "files": {name: {"content": content} for name, content in files.items()},
    })

    print("  Creating gist with 5 files...")
    result = run_gh(["api", "gists", "--method", "POST", "--input", "-"],
                    input_data=payload)
    gist_data = json.loads(result)
    gist_id = gist_data["id"]
    gist_url = gist_data["html_url"]
    print_ok(f"Badge gist created: {gist_id}")
    print(f"       {gist_url}")
    return gist_id


def create_archive_gist(config, dry_run=False):
    """Create the unlisted archive gist with initial archive.json.

    Args:
        config: Dict with 'gh_repo' key (owner/repo).
        dry_run: If True, only print what would happen.

    Returns:
        Gist ID string (or placeholder in dry-run mode).
    """
    archive_content = json.dumps({
        "repo": config["gh_repo"],
        "description": f"Monthly traffic archive for {config['gh_repo']}",
        "archives": [],
    }, indent=2)

    description = f"{config['gh_repo']} traffic archive"

    if dry_run:
        print_dry(f"Would create UNLISTED gist: \"{description}\"")
        print("    - archive.json")
        return "<DRY_RUN_ARCHIVE_GIST_ID>"

    payload = json.dumps({
        "description": description,
        "public": False,
        "files": {"archive.json": {"content": archive_content}},
    })

    print("  Creating unlisted gist...")
    result = run_gh(["api", "gists", "--method", "POST", "--input", "-"],
                    input_data=payload)
    gist_data = json.loads(result)
    gist_id = gist_data["id"]
    print_ok(f"Archive gist created: {gist_id}")
    return gist_id
