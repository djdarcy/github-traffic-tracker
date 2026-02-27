"""Tests for ghtraf.config — three-layer config resolution."""

import json
import os
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from ghtraf.config import (
    find_project_config,
    load_json,
    load_project_config,
    resolve_config,
    save_global_config,
    save_project_config,
    register_repo_globally,
)


class TestFindProjectConfig:
    """Test .ghtraf.json discovery by walking up directories."""

    def test_finds_config_in_cwd(self, tmp_path):
        """Should find .ghtraf.json in the given directory."""
        cfg_file = tmp_path / ".ghtraf.json"
        cfg_file.write_text('{"owner": "test"}')
        result = find_project_config(str(tmp_path))
        assert result == cfg_file

    def test_finds_config_in_parent(self, tmp_path):
        """Should walk upward to find .ghtraf.json."""
        cfg_file = tmp_path / ".ghtraf.json"
        cfg_file.write_text('{"owner": "test"}')
        child = tmp_path / "subdir" / "deep"
        child.mkdir(parents=True)
        result = find_project_config(str(child))
        assert result == cfg_file

    def test_returns_none_when_missing(self, tmp_path):
        """Should return None when no .ghtraf.json exists."""
        result = find_project_config(str(tmp_path))
        assert result is None


class TestLoadJson:
    """Test JSON file loading with error handling."""

    def test_load_valid_json(self, tmp_path):
        """Should parse valid JSON files."""
        f = tmp_path / "test.json"
        f.write_text('{"key": "value"}')
        assert load_json(f) == {"key": "value"}

    def test_load_missing_file(self, tmp_path):
        """Should return {} for missing files."""
        assert load_json(tmp_path / "nope.json") == {}

    def test_load_malformed_json(self, tmp_path):
        """Should return {} for malformed JSON."""
        f = tmp_path / "bad.json"
        f.write_text("{not valid json")
        assert load_json(f) == {}


class TestSaveConfig:
    """Test config file writing."""

    def test_save_project_config(self, tmp_path):
        """Should write .ghtraf.json to the target directory."""
        data = {"owner": "myorg", "repo": "myrepo"}
        path = save_project_config(data, str(tmp_path))
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["owner"] == "myorg"

    def test_save_global_config(self, tmp_config_home):
        """Should write config.json to ~/.ghtraf/."""
        data = {"version": 1, "repos": {}}
        path = save_global_config(data)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["version"] == 1

    def test_save_global_config_creates_dir(self, tmp_config_home):
        """Should create ~/.ghtraf/ directory if it doesn't exist."""
        ghtraf_dir = tmp_config_home / ".ghtraf"
        assert not ghtraf_dir.exists()
        save_global_config({"version": 1})
        assert ghtraf_dir.exists()


class TestResolveConfig:
    """Test three-layer config resolution (CLI > project > global)."""

    def test_cli_wins_over_project(self, tmp_path, sample_project_config):
        """CLI flags should override project config."""
        args = Namespace(owner="cli-owner", repo="cli-repo", repo_dir=str(tmp_path))

        with patch("ghtraf.config.find_project_config",
                    return_value=sample_project_config[0]):
            resolved = resolve_config(args, keys=["owner", "repo"])

        assert resolved["owner"] == "cli-owner"
        assert resolved["repo"] == "cli-repo"

    def test_project_wins_over_global(self, tmp_path, sample_project_config,
                                      sample_global_config):
        """Project config should override global config."""
        args = Namespace(owner=None, repo=None, repo_dir=str(tmp_path))

        with patch("ghtraf.config.find_project_config",
                    return_value=sample_project_config[0]):
            resolved = resolve_config(args, keys=["owner", "repo"])

        assert resolved["owner"] == "testorg"
        assert resolved["repo"] == "testrepo"

    def test_returns_none_when_no_config(self, tmp_path):
        """Should return None values when no config exists anywhere."""
        args = Namespace(owner=None, repo=None, repo_dir=None)
        resolved = resolve_config(args, keys=["owner", "repo"])
        assert resolved["owner"] is None
        assert resolved["repo"] is None


class TestRegisterRepoGlobally:
    """Test adding repos to global config."""

    def test_adds_new_repo(self, tmp_config_home):
        """Should add a new repo entry to global config."""
        config = register_repo_globally(
            owner="neworg", repo="newrepo",
            badge_gist_id="badge1", archive_gist_id="archive1",
        )
        assert "neworg/newrepo" in config["repos"]
        assert config["repos"]["neworg/newrepo"]["badge_gist_id"] == "badge1"

    def test_updates_existing_repo(self, tmp_config_home):
        """Should update fields on an existing repo entry."""
        register_repo_globally(owner="org", repo="repo", badge_gist_id="old")
        config = register_repo_globally(
            owner="org", repo="repo", badge_gist_id="new",
        )
        assert config["repos"]["org/repo"]["badge_gist_id"] == "new"
