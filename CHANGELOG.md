# Changelog

All notable changes to GitHub Traffic Tracker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1-alpha] - 2026-02-26

Setup tooling, project configuration, and dog-fooding — the project now tracks its own traffic.

### Added
- `setup-gists.py` — general-purpose onboarding script for any GitHub repo
  - Creates badge gist (public, 5 files) and archive gist (unlisted)
  - Sets repo variables (`TRAFFIC_GIST_ID`, `TRAFFIC_ARCHIVE_GIST_ID`)
  - Guides through PAT secret setup
  - `--configure` updates dashboard, README, and workflow with project values
  - `--dry-run` and `--non-interactive` modes for safe testing
- JSONL session log toolkit in `tests/one-offs/thinking/`
  - `inspect_jsonl_schema.py` — schema exploration for CC transcripts
  - `search_session_log.py` — content search across JSONL logs
  - `extract_plan_from_jsonl.py` — recover overwritten plan files
- GitHub Issues: ghtraf CLI epic (#6), Star History views (#7), Token distribution (#8)
- One-off scripts from production debugging (tests/one-offs/): backfill,
  fix, verify, and merge-logic test scripts with pre-operation state snapshots

### Changed
- README badges: version, installs, views, clones, license (dog-fooded from own gists)
- Dashboard (`docs/stats/index.html`) configured for `djdarcy/github-traffic-tracker`
- Dashboard README (`docs/stats/README.md`) configured with project links
- Workflow (`traffic-badges.yml`) updated: `workflow_run` commented out, version 0.1.0
- Test fixtures cleaned: all triton/DazzleML references replaced with generic ExampleOrg values
- Fixed stale project name in `scripts/update-version.sh` comment

## [0.1.0-alpha] - 2026-02-26

Initial project scaffold — extracted from production use in [NCSI Resolver](https://github.com/DazzleTools/Windows-No-Internet-Secured-BUGFIX) (v0.7.12) and [comfyui-triton-sageattention-installer](https://github.com/DazzleML/comfyui-triton-and-sageattention-installer) (v0.8.3).

### Added
- Project structure with RepoKit hooks and versioning
- GitHub Issues: Roadmap (#1), Quick Notes (#2), Embeddable Charts (#3), Badge Collection (#4), Time-Segmented History (#5)
