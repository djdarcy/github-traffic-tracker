# Changelog

All notable changes to GitHub Traffic Tracker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1-alpha] - 2026-02-27

README redesign, workflow bug fix, and project documentation.

### Fixed
- **Badge totals stuck at zero** — The Traffic API returns 14 days of data
  including zero-count entries. The dedup logic marked all API dates as "seen"
  regardless of count, so when real traffic appeared on those dates in later
  runs, it was skipped. Replaced boolean `lastSeenDates` set with delta-based
  `lastSeenCloneCounts` / `lastSeenViewCounts` maps that track the last-seen
  count per date and only accumulate increases. Added totals sanity check to
  repair existing under-counted state data.
- Pre-repo noise in dailyHistory — Traffic API backfills 14 days of zeros
  before the repo existed. Now filtered out using `repoCreatedAt` from the
  GitHub API.

### Added
- `repoCreatedAt` and `trackingSince` date markers in state.json — distinguishes
  "pre-repo" (API noise) from "gap in collection" from "zero traffic"
- `docs/platform-support.md` — platform matrix, known issues, gh CLI install guide
- `ROADMAP.md` — phased roadmap with links to tracking issues

### Changed
- README rewritten with Mermaid diagram, two-tier badge layout (metadata +
  live demo), real Quick Start content, Badge Showcase table, Live Dashboards
- Version badge, Python 3.10+ badge, Platform badge added to README header
- Workflow `lastSeenDates`/`lastSeenViewDates` migrated to delta-based format
  (legacy fields retained for backward compatibility)

## [0.2.0-alpha] - 2026-02-27

`ghtraf` CLI package and test harness.

### Added
- `src/ghtraf/` package with `ghtraf create` subcommand
- Three-layer config: CLI flags > `.ghtraf.json` > `~/.ghtraf/config.json`
- 93-test pytest harness (mock-based, no API calls needed)
- `pyproject.toml` with entry points: `ghtraf`, `github-traffic-tracker`
- `tests/test-data/` immutable template fixtures, `tests/test-runs/` ephemeral output

### Changed
- `pytest.ini` — `norecursedirs` for test-data/test-runs, markers for slow/e2e

## [0.1.2-alpha] - 2026-02-27

Push trigger, script parameterization, setup-gists delegation.

### Added
- Workflow push trigger with concurrency group and 60-minute freshness check
- `setup-gists.py` delegation: imports `ghtraf.cli.main` if installed

### Changed
- `scripts/backfill_stats_fields.py` — parameterized with argparse CLI arguments
- `scripts/fix_expired_uniques.py` — parameterized with `--gist-id` argument
- `scripts/fix_overwritten_stars.py` — parameterized with `--gist-id`/`--repo`
- Moved `verify_stats_migration.py` to `tests/one-offs/`

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
