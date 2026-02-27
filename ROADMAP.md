# Roadmap

> Tracks the project roadmap. See [Issue #1](https://github.com/djdarcy/github-traffic-tracker/issues/1) for discussion.

## Vision

Zero-server GitHub traffic analytics that anyone can add to their repo in minutes. Daily collection via GitHub Actions, gist-backed storage, client-side dashboard with interactive charts.

---

## Phase 1: Port & Validate _(complete)_

Core system proven across two production repos (NCSI Resolver, ComfyUI Triton Installer).

- [x] GitHub Actions workflow — daily traffic collection, CI detection, archive rotation
- [x] Client-side dashboard — Installs, Views, Overview, Dev, Community tabs
- [x] Organic clone separation (CI checkout detection via workflow run analysis)
- [x] Organic unique clone estimation (`MIN(percentage, ciRuns)` formula)
- [x] Monthly archive system (gist-based, unlimited history)
- [x] Shields.io badge endpoints (installs, views, clones, downloads)
- [x] Cascading recency suffix (`+N 24h` / `+N wk` / `+N mo`)
- [x] Bidirectional projection segments for missing/incomplete data

## Phase 2: Standalone Project _(current)_

Extract into reusable project with CLI tooling.

- [x] Template workflow and dashboard (copy-paste ready)
- [x] `setup-gists.py` — automated gist creation and variable setup
- [x] Dog-fooding: this project tracks its own traffic
- [x] `ghtraf` CLI package with `ghtraf create` subcommand ([#6](https://github.com/djdarcy/github-traffic-tracker/issues/6))
- [x] 93-test pytest harness ([#19](https://github.com/djdarcy/github-traffic-tracker/issues/19))
- [x] Delta-based accumulation (fixes first-run seeding bug)
- [ ] `ghtraf init`, `status`, `list` subcommands
- [ ] `ghtraf upgrade` — migration runner ([#6](https://github.com/djdarcy/github-traffic-tracker/issues/6))
- [ ] THAC0 verbosity system ([#13](https://github.com/djdarcy/github-traffic-tracker/issues/13))
- [ ] CI pipeline for automated test runs ([#22](https://github.com/djdarcy/github-traffic-tracker/issues/22))
- [ ] PyPI publish

## Phase 3: Dashboard & Analytics

- [ ] Playwright E2E tests for dashboard ([#20](https://github.com/djdarcy/github-traffic-tracker/issues/20))
- [ ] Conversion ratio analytics — funnel insights ([#11](https://github.com/djdarcy/github-traffic-tracker/issues/11))
- [ ] Smart star history views ([#7](https://github.com/djdarcy/github-traffic-tracker/issues/7))
- [ ] Time-segmented All History view ([#5](https://github.com/djdarcy/github-traffic-tracker/issues/5))
- [ ] Dashboard dark/light theme toggle
- [ ] Data export (CSV/JSON download)

## Phase 4: Growth & Integration

- [ ] Embeddable charts for READMEs ([#3](https://github.com/djdarcy/github-traffic-tracker/issues/3))
- [ ] Badge collection page ([#4](https://github.com/djdarcy/github-traffic-tracker/issues/4))
- [ ] Pluggable integration system — PyPI, npm, ComfyUI registries ([#10](https://github.com/djdarcy/github-traffic-tracker/issues/10))
- [ ] Multi-repo dashboard (single page for multiple repos)
- [ ] Free-tier limits audit ([#9](https://github.com/djdarcy/github-traffic-tracker/issues/9))
- [ ] Org transfer to DazzleTools ([#24](https://github.com/djdarcy/github-traffic-tracker/issues/24))

## Future Ideas

- GitHub App version (no PAT needed, org-wide deployment)
- Historical data import from other tools
- Webhook notifications for traffic milestones
- Contributor analytics integration
