"""Tests for ghtraf.gist — state schema, badge structure, and gist creation."""

import json
from unittest.mock import patch

from ghtraf.gist import (
    build_badge, build_initial_state,
    create_badge_gist, create_archive_gist,
)


class TestInitialState:
    """Test the state.json schema builder."""

    EXPECTED_KEYS = {
        "totalClones", "totalUniqueClones", "totalDownloads",
        "totalViews", "totalUniqueViews", "totalCiCheckouts",
        "totalCiUniqueClones", "totalOrganicUniqueClones",
        "previousTotalDownloads", "_previousCiUniqueToday",
        "stars", "forks", "openIssues",
        "lastSeenDates", "lastSeenViewDates", "dailyHistory",
        "ciCheckouts", "referrers", "popularPaths",
    }

    def test_has_all_expected_keys(self):
        """Initial state should contain all expected top-level keys."""
        state = build_initial_state()
        assert set(state.keys()) == self.EXPECTED_KEYS

    def test_counters_start_at_zero(self):
        """All numeric counters should start at 0."""
        state = build_initial_state()
        counter_keys = [k for k in state if k.startswith("total")
                        or k in ("stars", "forks", "openIssues",
                                 "previousTotalDownloads",
                                 "_previousCiUniqueToday")]
        for key in counter_keys:
            assert state[key] == 0, f"{key} should be 0, got {state[key]}"

    def test_lists_start_empty(self):
        """All list fields should start as empty lists."""
        state = build_initial_state()
        list_keys = ["lastSeenDates", "lastSeenViewDates", "dailyHistory",
                     "referrers", "popularPaths"]
        for key in list_keys:
            assert state[key] == [], f"{key} should be [], got {state[key]}"

    def test_ci_checkouts_starts_empty_dict(self):
        """ciCheckouts should start as an empty dict."""
        state = build_initial_state()
        assert state["ciCheckouts"] == {}

    def test_serializes_to_valid_json(self):
        """State should round-trip through JSON serialization."""
        state = build_initial_state()
        serialized = json.dumps(state)
        deserialized = json.loads(serialized)
        assert deserialized == state


class TestBadge:
    """Test the shields.io badge JSON builder."""

    def test_default_badge(self):
        """Default badge should have schemaVersion=1 and color=blue."""
        badge = build_badge("installs")
        assert badge["schemaVersion"] == 1
        assert badge["label"] == "installs"
        assert badge["message"] == "0"
        assert badge["color"] == "blue"

    def test_custom_values(self):
        """Badge should accept custom message and color."""
        badge = build_badge("stars", message="42", color="brightgreen")
        assert badge["label"] == "stars"
        assert badge["message"] == "42"
        assert badge["color"] == "brightgreen"

    def test_badge_is_shields_compatible(self):
        """Badge JSON must have the 3 required shields.io fields."""
        badge = build_badge("test")
        required = {"schemaVersion", "label", "message"}
        assert required.issubset(set(badge.keys()))


class TestCreateBadgeGist:
    """Test badge gist creation."""

    def test_dry_run_returns_placeholder(self):
        """Dry run should return placeholder ID without API calls."""
        config = {"gh_repo": "testorg/testrepo"}
        gist_id = create_badge_gist(config, dry_run=True)
        assert gist_id == "<DRY_RUN_BADGE_GIST_ID>"

    def test_dry_run_lists_all_files(self, capsys):
        """Dry run should list all 5 badge files."""
        config = {"gh_repo": "testorg/testrepo"}
        create_badge_gist(config, dry_run=True)
        captured = capsys.readouterr()
        for name in ["state.json", "installs.json", "downloads.json",
                      "clones.json", "views.json"]:
            assert name in captured.out

    def test_creates_gist_via_api(self):
        """Should call run_gh with correct payload and return gist ID."""
        config = {"gh_repo": "testorg/testrepo"}
        fake_response = json.dumps({
            "id": "abc123",
            "html_url": "https://gist.github.com/testuser/abc123",
        })
        with patch("ghtraf.gist.run_gh", return_value=fake_response) as mock:
            gist_id = create_badge_gist(config)

        assert gist_id == "abc123"
        mock.assert_called_once()
        call_args = mock.call_args
        assert "gists" in call_args[0][0]
        # Verify payload contains all 5 files
        payload = json.loads(call_args[1]["input_data"])
        assert payload["public"] is True
        assert len(payload["files"]) == 5
        assert "state.json" in payload["files"]

    def test_badge_gist_description_includes_repo(self):
        """Gist description should contain the repo name with [GTT] prefix."""
        config = {"gh_repo": "myorg/myproject"}
        fake_response = json.dumps({"id": "x", "html_url": "https://..."})
        with patch("ghtraf.gist.run_gh", return_value=fake_response) as mock:
            create_badge_gist(config)
        payload = json.loads(mock.call_args[1]["input_data"])
        assert payload["description"].startswith("[GTT]")
        assert "myorg/myproject" in payload["description"]
        assert "\u00b7 badges" in payload["description"]


class TestCreateArchiveGist:
    """Test archive gist creation."""

    def test_dry_run_returns_placeholder(self):
        """Dry run should return placeholder ID without API calls."""
        config = {"gh_repo": "testorg/testrepo"}
        gist_id = create_archive_gist(config, dry_run=True)
        assert gist_id == "<DRY_RUN_ARCHIVE_GIST_ID>"

    def test_creates_unlisted_gist(self):
        """Archive gist should be unlisted (public=False)."""
        config = {"gh_repo": "testorg/testrepo"}
        fake_response = json.dumps({"id": "def456", "html_url": "https://..."})
        with patch("ghtraf.gist.run_gh", return_value=fake_response) as mock:
            gist_id = create_archive_gist(config)

        assert gist_id == "def456"
        payload = json.loads(mock.call_args[1]["input_data"])
        assert payload["public"] is False
        assert "archive.json" in payload["files"]

    def test_archive_gist_description_format(self):
        """Archive gist description should use [GTT] prefix."""
        config = {"gh_repo": "testorg/testrepo"}
        fake_response = json.dumps({"id": "x", "html_url": "https://..."})
        with patch("ghtraf.gist.run_gh", return_value=fake_response) as mock:
            create_archive_gist(config)
        payload = json.loads(mock.call_args[1]["input_data"])
        assert payload["description"].startswith("[GTT]")
        assert "testorg/testrepo" in payload["description"]
        assert "\u00b7 archive" in payload["description"]

    def test_archive_content_has_repo_and_empty_archives(self):
        """archive.json content should reference repo and start with empty archives list."""
        config = {"gh_repo": "testorg/testrepo"}
        fake_response = json.dumps({"id": "x", "html_url": "https://..."})
        with patch("ghtraf.gist.run_gh", return_value=fake_response) as mock:
            create_archive_gist(config)
        payload = json.loads(mock.call_args[1]["input_data"])
        archive_content = json.loads(payload["files"]["archive.json"]["content"])
        assert archive_content["repo"] == "testorg/testrepo"
        assert archive_content["archives"] == []

    def test_archive_json_internal_description_unchanged(self):
        """Internal archive.json description should NOT have [GTT] prefix."""
        config = {"gh_repo": "testorg/testrepo"}
        fake_response = json.dumps({"id": "x", "html_url": "https://..."})
        with patch("ghtraf.gist.run_gh", return_value=fake_response) as mock:
            create_archive_gist(config)
        payload = json.loads(mock.call_args[1]["input_data"])
        archive_content = json.loads(payload["files"]["archive.json"]["content"])
        assert "Monthly traffic archive for" in archive_content["description"]
        assert not archive_content["description"].startswith("[GTT]")
