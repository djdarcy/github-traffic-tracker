"""File configuration for ghtraf.

Handles updating dashboard HTML, README, and workflow YAML files
with project-specific values via regex replacement.
"""

import json
import re
from pathlib import Path

from ghtraf.output import print_dry, print_ok, print_skip, print_warn


def apply_replacements(filepath, replacements, config, dry_run=False):
    """Apply a list of (pattern, template, description) replacements to a file.

    Args:
        filepath: Path to the file to modify.
        replacements: List of (regex_pattern, format_template, description) tuples.
        config: Dict of values to substitute into templates.
        dry_run: If True, only print what would happen.

    Returns:
        Count of successful replacements.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        print_warn(f"File not found: {filepath}")
        return 0

    content = filepath.read_text(encoding="utf-8")
    original = content
    success = 0

    for pattern, template, desc in replacements:
        formatted = template.format(**config)
        new_content, count = re.subn(pattern, formatted, content, count=1)
        if count > 0:
            content = new_content
            success += 1
            if dry_run:
                print_dry(f"{desc}")
            else:
                print_ok(f"{desc}")
        else:
            print_skip(f"{desc} (pattern not found)")

    if not dry_run and content != original:
        filepath.write_text(content, encoding="utf-8")

    return success


def configure_dashboard(config, dashboard_path, dry_run=False):
    """Update the dashboard HTML file with project-specific values.

    Args:
        config: Dict with owner, repo, display_name_html, gh_username,
                badge_gist_id, archive_gist_id, created.
        dashboard_path: Path to docs/stats/index.html.
        dry_run: If True, only print what would happen.

    Returns:
        Count of successful replacements.
    """
    print(f"  Updating {dashboard_path}...")

    replacements = [
        # HTML title
        (r'<title>.*?- Project Statistics</title>',
         '<title>{display_name_html} - Project Statistics</title>',
         "HTML title"),
        # Banner link href
        (r'href="https://github\.com/[^"]+?" class="banner-link"',
         'href="https://github.com/{owner}/{repo}" class="banner-link"',
         "Banner link URL"),
        # Banner title text
        (r'<p class="banner-title">.*?</p>',
         '<p class="banner-title">{display_name_html}</p>',
         "Banner title"),
        # Footer repository link
        (r'<a href="https://github\.com/[^"]+?">Repository</a>',
         '<a href="https://github.com/{owner}/{repo}">Repository</a>',
         "Footer repo link"),
        # Footer releases link
        (r'<a href="https://github\.com/[^"]+?/releases">Releases</a>',
         '<a href="https://github.com/{owner}/{repo}/releases">Releases</a>',
         "Footer releases link"),
        # JS config: GIST_RAW_BASE
        (r"const GIST_RAW_BASE = '[^']+';",
         "const GIST_RAW_BASE = 'https://gist.githubusercontent.com/"
         "{gh_username}/{badge_gist_id}/raw';",
         "Gist raw base URL"),
        # JS config: ARCHIVE_GIST_ID
        (r"const ARCHIVE_GIST_ID = '[^']+';",
         "const ARCHIVE_GIST_ID = '{archive_gist_id}';",
         "Archive gist ID"),
        # JS config: REPO_OWNER
        (r"const REPO_OWNER = '[^']+';",
         "const REPO_OWNER = '{owner}';",
         "Repo owner"),
        # JS config: REPO_NAME
        (r"const REPO_NAME = '[^']+';",
         "const REPO_NAME = '{repo}';",
         "Repo name"),
        # JS config: REPO_CREATED
        (r"const REPO_CREATED = '[^']+';",
         "const REPO_CREATED = '{created}';",
         "Repo creation date"),
    ]

    return apply_replacements(dashboard_path, replacements, config, dry_run)


def configure_readme(config, readme_path, dry_run=False):
    """Update the dashboard README.md with project-specific values.

    Args:
        config: Dict with owner, repo, display_name, gh_username,
                badge_gist_id.
        readme_path: Path to docs/stats/README.md.
        dry_run: If True, only print what would happen.

    Returns:
        Count of successful replacements.
    """
    print(f"  Updating {readme_path}...")

    config = dict(config)  # copy to avoid mutating caller's dict
    config["owner_lower"] = config["owner"].lower()

    replacements = [
        # Project name and link
        (r'\[.*?\]\(https://github\.com/[^)]+\)\.',
         '[{display_name}](https://github.com/{owner}/{repo}).',
         "Project link"),
        # Badge gist link
        (r'\[Badge Gist\]\(https://gist\.github\.com/[^)]+\)',
         '[Badge Gist](https://gist.github.com/{gh_username}/{badge_gist_id})',
         "Badge gist link"),
        # Dashboard URL
        (r'\*\*https://[^*]+/stats/\*\*',
         '**https://{owner_lower}.github.io/{repo}/stats/**',
         "Dashboard URL"),
    ]

    return apply_replacements(readme_path, replacements, config, dry_run)


def configure_workflow(config, workflow_path, dry_run=False):
    """Update the traffic-badges.yml workflow.

    Args:
        config: Dict with optional 'ci_workflows' list.
        workflow_path: Path to .github/workflows/traffic-badges.yml.
        dry_run: If True, only print what would happen.

    Returns:
        Count of changes made.
    """
    print(f"  Updating {workflow_path}...")

    workflow_path = Path(workflow_path)
    if not workflow_path.exists():
        print_warn(f"File not found: {workflow_path}")
        return 0

    content = workflow_path.read_text(encoding="utf-8")
    original = content
    changes = 0

    # Handle workflow_run trigger
    if config.get("ci_workflows"):
        names = json.dumps(config["ci_workflows"])
        new_content = re.sub(
            r'workflows: \[.*?\]',
            f'workflows: {names}',
            content
        )
        if new_content != content:
            content = new_content
            changes += 1
            msg = f"workflow_run trigger: {names}"
            print_dry(msg) if dry_run else print_ok(msg)
    else:
        new_content = re.sub(
            r'  workflow_run:.*?\n    workflows:.*?\n    types:.*?\n',
            '  # workflow_run:            # Uncomment and set your CI workflow'
            ' name to run after CI\n'
            '  #   workflows: ["CI"]\n'
            '  #   types: [completed]\n',
            content
        )
        if new_content != content:
            content = new_content
            changes += 1
            msg = "workflow_run trigger: commented out (no CI workflows specified)"
            print_dry(msg) if dry_run else print_ok(msg)

    # Update archive version string
    new_content = re.sub(
        r'version: "[^"]+",',
        'version: "0.1.0",',
        content
    )
    if new_content != content:
        content = new_content
        changes += 1
        msg = "Archive version: 0.1.0"
        print_dry(msg) if dry_run else print_ok(msg)

    if not dry_run and content != original:
        workflow_path.write_text(content, encoding="utf-8")

    return changes
