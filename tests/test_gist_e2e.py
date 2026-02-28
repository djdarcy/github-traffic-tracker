"""End-to-end tests for real gist creation and cleanup.

These tests hit the live GitHub API. They are skipped by default.
Run explicitly with: pytest -m e2e

Every test creates gists with a unique sentinel description and
deletes them in a finally block, so cleanup happens even on failure.
"""

import json
import subprocess

import pytest


SENTINEL = "[GTT-TEST]"


def gh_api(args, input_data=None):
    """Run gh api command, return stdout."""
    cmd = ["gh"] + args
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        input=input_data,
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def create_test_gist(description, files, public=True):
    """Create a gist and return its ID."""
    payload = json.dumps({
        "description": f"{SENTINEL} {description}",
        "public": public,
        "files": {name: {"content": content} for name, content in files.items()},
    })
    result = gh_api(
        ["api", "gists", "--method", "POST", "--input", "-"],
        input_data=payload,
    )
    return json.loads(result)["id"]


def delete_gist(gist_id):
    """Delete a gist by ID. Ignores errors (gist may already be gone)."""
    try:
        gh_api(["api", "--method", "DELETE", f"gists/{gist_id}"])
    except RuntimeError:
        pass  # already deleted or doesn't exist


def gist_exists(gist_id):
    """Check whether a gist exists (returns True/False)."""
    result = subprocess.run(
        ["gh", "api", f"gists/{gist_id}"],
        capture_output=True, text=True,
    )
    return result.returncode == 0


@pytest.mark.e2e
class TestGistRoundTrip:
    """Create real gists, verify, and clean up."""

    def test_badge_gist_create_and_delete(self):
        """Create a badge-shaped gist, verify files, delete it."""
        gist_id = None
        try:
            gist_id = create_test_gist(
                "e2e badge test",
                {
                    "state.json": json.dumps({"totalClones": 0}),
                    "views.json": json.dumps({"schemaVersion": 1}),
                },
            )
            assert gist_id is not None
            assert len(gist_id) > 10

            # Verify it exists and has the right description
            raw = gh_api(["api", f"gists/{gist_id}"])
            data = json.loads(raw)
            assert SENTINEL in data["description"]
            assert "state.json" in data["files"]
            assert "views.json" in data["files"]
        finally:
            if gist_id:
                delete_gist(gist_id)

        # Verify deletion
        assert not gist_exists(gist_id), f"gist {gist_id} still exists after delete"

    def test_archive_gist_create_and_delete(self):
        """Create an archive-shaped gist (unlisted), verify, delete."""
        gist_id = None
        try:
            gist_id = create_test_gist(
                "e2e archive test",
                {"archive.json": json.dumps({"repo": "test/test", "archives": []})},
                public=False,
            )
            assert gist_id is not None

            raw = gh_api(["api", f"gists/{gist_id}"])
            data = json.loads(raw)
            assert data["public"] is False
            assert "archive.json" in data["files"]
        finally:
            if gist_id:
                delete_gist(gist_id)

        assert not gist_exists(gist_id)

    def test_gist_update_round_trip(self):
        """Create, update content, verify update, delete."""
        gist_id = None
        try:
            gist_id = create_test_gist(
                "e2e update test",
                {"state.json": json.dumps({"totalClones": 0})},
            )

            # Update the gist
            update_payload = json.dumps({
                "files": {
                    "state.json": {
                        "content": json.dumps({"totalClones": 42}),
                    },
                },
            })
            gh_api(
                ["api", f"gists/{gist_id}", "--method", "PATCH", "--input", "-"],
                input_data=update_payload,
            )

            # Verify the update
            raw = gh_api(["api", f"gists/{gist_id}"])
            data = json.loads(raw)
            state = json.loads(data["files"]["state.json"]["content"])
            assert state["totalClones"] == 42
        finally:
            if gist_id:
                delete_gist(gist_id)

        assert not gist_exists(gist_id)
