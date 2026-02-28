# CI Clone Testbed

**Parent project**: [github-traffic-tracker](https://github.com/djdarcy/github-traffic-tracker) ([Issue #49](https://github.com/djdarcy/github-traffic-tracker/issues/49))

Controlled experiments to empirically determine how GitHub's Traffic API counts clones from CI/CD activity.

## Why This Exists

GitHub's Traffic API reports clone counts, but the exact relationship between `actions/checkout` operations and reported clones is undocumented. Different assumptions lead to different "organic clone" formulas. This testbed measures the actual behavior through controlled, isolated experiments.

## Experiment Schedule

One experiment per UTC day. Observer reads Traffic API at 04:30 UTC (no `actions/checkout`, no `git push` — zero contamination).

| Day | Experiment | Question |
|-----|-----------|----------|
| 0 | Baseline | Does API-only repo setup register zero clones? |
| 1 | No Checkout | Does a bare workflow (no checkout) produce clones? |
| 2 | Single Checkout | Is 1 `actions/checkout` = exactly 1 clone event? |
| 3 | Fetch Depth | Does `fetch-depth=0` differ from default shallow? |
| 4 | Double Checkout | 2 checkout steps in 1 job = 1 or 2 clones? |
| 5 | Matrix 3x3 | 9 jobs x 1 checkout = ? clones, ? unique |
| 6 | Multi-Run (x3) | 3 dispatches same day = 3 clones, 1 unique? |
| 7 | Manual Clone | Human `git clone` calibration (+1, +1) |
| 8 | PAT vs Token | Different auth = different unique identity? |
| 9 | Pages Build | Does Pages deployment add hidden clones? |
| 10 | Replicate Single | Repeatability check — same as Day 2? |
| 11 | Replicate Matrix | Repeatability check — same as Day 5? |

## Design Constraint: Zero-Contamination Observer

The observer workflow (`observe-traffic.yml`) must NOT produce clone events:
- Reads Traffic API via `curl` + PAT (not `actions/checkout`)
- Writes results via GitHub Contents API (not `git push`)
- This is the #1 design constraint of the entire project

## Data

- `data/observations.json` — Raw API snapshots (written by observer)
- `data/experiments/exp-*.json` — Per-experiment hypotheses and results
- `data/manifest.json` — Experiment schedule mapping

## Analysis

Analysis code lives in the parent GTT repo at `tests/research/ci-clone-counting/analyze.py`.

## Candidate Formulas Being Tested

1. **current_1to1**: 1 checkout = 1 clone (current GTT assumption)
2. **multiplier_1.5x**: Each checkout produces 1.5 clone events
3. **multiplier_2.0x**: Each checkout produces 2 clone events (init + fetch)
4. **unique_per_day**: CI unique = 1 per UTC day regardless of runs
5. **unique_per_wf**: CI unique = number of distinct workflows that ran
