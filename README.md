# GitHub Traffic Tracker

Track GitHub repo traffic beyond the 14-day API limit. Zero servers, zero cost.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

## What It Does

GitHub's Traffic API only retains **14 days** of clone and view data. This project captures that data daily via GitHub Actions and accumulates it indefinitely in a Gist — giving you permanent traffic history with zero infrastructure.

### Features

- **Daily data collection** — Clones, views, downloads, stars, forks, referrers, popular paths
- **Unique visitor tracking** — Unique cloners and viewers alongside raw counts
- **CI clone detection** — Separates organic clones from CI/CD checkout noise
- **Cascading recency badge** — `installs X (+Y 24h)` → `(+Y wk)` → `(+Y mo)`
- **Tabbed dashboard** — Overview, Installs, Views, Community, Dev tabs
- **Monthly archives** — Long-term snapshots in a separate Gist
- **Zero server** — Pure GitHub Actions + Gist storage + client-side rendering

## Quick Start

> Detailed setup guide coming soon. For now, see the workflow and dashboard in the production deployments below.

### Production Deployments

This system is actively running on:

- **[NCSI Resolver](https://dazzletools.github.io/Windows-No-Internet-Secured-BUGFIX/stats/)** — Origin project (v0.7.12)
- **[ComfyUI Triton & SageAttention](https://dazzleml.github.io/comfyui-triton-and-sageattention-installer/stats/#installs)** — First port (v0.8.3)

## How It Works

```
┌──────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  GitHub Actions  │────▶│  Public Gist │────▶│   Dashboard    │
│  (daily 3am UTC) │     │  state.json  │     │  (GitHub Pages) │
│                  │     │ badges/*.json│     │                 │
│  Collects:       │     └──────────────┘     │  Reads from     │
│  - Clones/Views  │                          │  Gist CDN       │
│  - Downloads     │     ┌──────────────┐     │  client-side    │
│  - Stars/Forks   │────▶│ Archive Gist │     └────────────────┘
│  - CI checkouts  │     │ (unlisted)   │
│  - Referrers     │     │ monthly.json │
└──────────────────┘     └──────────────┘
```

## Roadmap

See [Issue #1 — Roadmap](https://github.com/djdarcy/github-traffic-tracker/issues/1) for the full plan.

## License

[GPL-3.0](LICENSE)
