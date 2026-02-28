# Changelog

All notable changes to GitHub Traffic Tracker will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.7-alpha] - 2026-02-28

Gist naming convention for discoverability.

### Changed
- **Gist naming convention** (#48) — Gist descriptions now use
  `[GTT] owner/repo · badges` and `[GTT] owner/repo · archive` format.
  The `[GTT]` prefix enables visual scanning and programmatic filtering
  (`gh api gists --jq '.[] | select(.description | startswith("[GTT]"))'`).
  Applied to both `gist.py` and `setup-gists.py`.
- Version bump 0.2.6 → 0.2.7

### Added
- One-off gist rename script (`tests/one-offs/rename_gists.py`) —
  discovers GTT gists by file signature, renames to `[GTT]` convention.
  Supports `--dry-run` and reports placeholder gists separately.
- One-off gist backup script (`tests/one-offs/backup_placeholder_gists.py`) —
  backs up all placeholder gists before cleanup.
- One-off gist cleanup script (`tests/one-offs/cleanup_placeholder_gists.py`) —
  two-phase verify-then-delete with abort-on-suspicious default.
- 3 e2e gist round-trip tests (`test_gist_e2e.py`) — create, verify,
  update, and delete real gists via API. Run with `pytest -m e2e`.
- 2 new gist unit tests — archive description format + internal
  archive.json description unchanged (138 total: 135 unit + 3 e2e)

### Fixed
- **Test mock leak creating ghost gists** — `conftest.py` patched
  `ghtraf.gh.run_gh` but `gist.py` had already imported `run_gh` into
  its own namespace via `from ... import`. Two non-dry-run tests hit the
  real API on every `pytest` run, creating 4 orphan gists each time.
  Fixed by also patching `gist_mod.run_gh` directly.
- `pytest.ini` excludes e2e tests from default run (`-m "not e2e"`)

## [0.2.6-alpha] - 2026-02-28

Package-embed templates and dashboard bug fixes.

### Added
- **Package-embedded templates** (#27) — Dashboard, README, and workflow
  templates shipped in `src/ghtraf/templates/` with placeholder tokens for
  `configure.py` round-trip. Enables `ghtraf init` to copy clean templates
  without GTT-specific values.
- Favicon (`docs/stats/favicon.svg`) — SVG chart icon for dashboard tab
- 40 new template tests (`test_templates.py`) — structure verification,
  placeholder presence, GTT-value absence, bug-fix regression, pyproject
  glob, and configure round-trip (133 total tests)

### Fixed
- **Community Trends negative y-axis** (#25) — `beginAtZero: false` on the
  community chart's left y-axis caused -1 display when all star values were 0.
  Changed to `beginAtZero: true`.
- **Organic clone formula divergence** — Live dashboard still used inline
  `totalClones - totalCiCheckouts` (old formula) instead of accumulated
  `state.totalOrganicClones` (new field from v0.2.2). Updated two locations
  in `docs/stats/index.html`.

### Changed
- `pyproject.toml` template glob: `templates/*` → `templates/**/*` (recursive)
- `src/ghtraf/_version.py` synced to PATCH=6 (was stuck at PATCH=0 since v0.2.0)
- Version bump 0.2.5 → 0.2.6

## [0.2.5-alpha] - 2026-02-28

Fix zero-traffic days missing uniqueClones/uniqueViews in dailyHistory.

### Fixed
- **Zero-traffic days missing unique fields** — The Traffic API only returns dates
  with non-zero clone/view counts. For zero-traffic days, the API simply omits the
  date from its response, so `clonesByDate[date]` is `undefined` and the v0.2.4 fix
  (`!== undefined` check) correctly skipped writing. Added a backfill pass after the
  merge loop: any dailyHistory entry within the API's 14-day window that still has
  `uniqueClones === undefined` gets set to 0, because "not in API response" means
  "zero traffic" — not "no data collected."

- **Dashboard projection gap for US-timezone users** — `projectTrailingZeros()`
  only projected when the last entry was "today" (UTC). For US users viewing after
  midnight UTC (7pm EST / 4pm PST) but before the 3am UTC workflow run, the last
  entry is "yesterday" and no projection fired — chart lines dropped to zero at the
  right edge. Now projects when the last entry is today OR yesterday.

### Changed
- License badge color `blue` → `darkgreen` (matches Python badge)
- Version bump 0.2.4 → 0.2.5

## [0.2.4-alpha] - 2026-02-27

Fix false-zero suppression and badge color refresh.

### Fixed
- **Unique clones/views false-zero suppression** — The `> 0` gate rejected
  valid zero values from the Traffic API within its 14-day window, omitting
  `uniqueClones`/`uniqueViews` fields entirely for zero-traffic days. Changed
  to `!== undefined` so zero means "no visitors" (stored) vs undefined means
  "no data collected" (gap). Math.max still prevents overwriting real values.

### Changed
- README badge colors: Python badge `darkgreen` (was blue), license badge
  consistent casing, platform badge drops `.svg` suffix

## [0.2.3-alpha] - 2026-02-27

Patch: organic double-count guard, mermaid rendering fix, missing changelog.

### Fixed
- **Organic double-count guard** — First run after v2→v3 schema migration
  could double-count today's organic clones (migration seeds `totalOrganicClones`
  from `dailyHistory` which may include today, then accumulation adds today again
  because `_previousOrganicToday` was `undefined` → `0`). Now skips accumulation
  on first run when `_previousOrganicToday` is undefined.
- README Mermaid diagram — `\n` replaced with `<br/>` for correct rendering
  on GitHub (literal `\n` displayed as text instead of line breaks)

### Added
- Missing CHANGELOG entry for v0.2.2-alpha
- Early-dev note in CLAUDE.md — skip deprecation formalities during alpha

## [0.2.2-alpha] - 2026-02-27

Schema v3 organic clones, downstream port, and community health files.

### Fixed
- **Organic clone badge math** — Per-day organic accumulation (`totalOrganicClones`)
  replaces global subtraction (`totalClones - totalCiCheckouts`) which allowed
  phantom CI on zero-clone days to reduce organic below individual day values
- Backlink path resolution — `[[notes/bugs/filename|alias]]` wikilinks now
  resolve correctly alongside bare `[[filename]]` links in `generate-backlinks.py`
- `--validate` in `generate-backlinks.py` is non-fatal (graceful when
  obsidiantools not installed) and runs after normal output

### Added
- Schema v3 migration (section 2.5): computes `totalOrganicClones` from
  `dailyHistory` (takes max of per-day sum vs legacy global subtraction)
- Consolidated schema migration section 2.5 (v1→v2 and v2→v3 in one place)
- Sanity check for `totalOrganicClones` in totals repair section
- Per-day organic delta tracking (`_previousOrganicToday` state field)
- RepoKit community files: CODEOWNERS, FUNDING.yml, dependabot.yml,
  stale.yml, bug-report and feature-request templates, PR template
- GitHub Discussions badge in README header row

### Changed
- Badge output uses `state.totalOrganicClones` instead of inline subtraction
- Monthly archive uses `state.totalOrganicClones` for organic clone count

### Removed
- `setup.py` (replaced by `pyproject.toml` in v0.2.0)
- Inline v1→v2 migration blocks from clone/view sections (moved to 2.5)

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
