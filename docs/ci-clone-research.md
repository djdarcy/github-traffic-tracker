# How GitHub Counts CI Clones

> How GitHub Traffic Tracker separates real user interest from CI/CD noise

## The Problem

GitHub's Traffic API counts every `git clone` -- including automated ones from CI/CD pipelines. A repository with active GitHub Actions can show hundreds of "clones" per day, almost none of which represent actual humans downloading the code.

GitHub Traffic Tracker solves this by computing **organic clones**: the raw count minus CI-attributed clones. But how many clones does each CI operation actually produce? We ran experiments to find out.

## The Experiment

We created a dedicated private testbed repository ([Issue #49](https://github.com/djdarcy/github-traffic-tracker/issues/49)) and ran **14 controlled experiments** over 22 days (Feb 28 -- Mar 21, 2026). Each experiment isolated a single variable on its own UTC day:

| Day | Experiment | What We Tested | Observed Clones | Observed Uniques |
|:---:|-----------|---------------|:---:|:---:|
| 0 | Baseline | No workflow at all | 0 | 0 |
| 1 | No Checkout | Workflow runs but never calls `actions/checkout` | 0 | 0 |
| 2 | Single Checkout | One `actions/checkout@v4` step | 1 | 1 |
| 3 | Fetch Depth | `actions/checkout` with `fetch-depth: 1` | 1 | 1 |
| 4 | Double Checkout | Two checkout steps in one job | 2 | 1 |
| 5 | Matrix 3x3 | 9 parallel jobs, each with one checkout | 9 | 1 |
| 6 | Multi-Run | 3 separate workflow dispatches, 1 hour apart | 3 | 1 |
| 7 | Manual Clone | `git clone` from a local machine (no CI) | 1 | 1 |
| 8 | PAT vs GITHUB_TOKEN | Two dispatches: one with default token, one with PAT | 2 | 2 |
| 9 | Pages Build | GitHub Pages deployment | 4 | 1 |
| 10-11 | *(contaminated)* | Replication attempts with Pages still enabled | -- | -- |
| 12 | Clean Single | Replication of Day 2 (Pages disabled) | 1 | 1 |
| 13 | Clean Matrix | Replication of Day 5 (Pages disabled) | 9 | 1 |

### Key Design Choices

- **Zero-contamination observer**: Data was captured via the GitHub Contents API (not `git push`), which produces zero clone events
- **One experiment per UTC day**: The Traffic API reports by UTC day, so each experiment needed its own day
- **Private repo**: Eliminated external traffic noise
- **Replications**: Days 12-13 confirmed results after removing Pages contamination from Days 10-11

## What We Found

### Finding 1: One checkout = one clone (exact)

Every `actions/checkout` step produces exactly **one** clone in the Traffic API. Not 1.5, not 2 -- exactly 1. This held across all configurations:

- Single checkout: 1 clone
- Two checkouts in one job: 2 clones
- 9-job matrix build: 9 clones
- 3 separate dispatches: 3 clones
- Shallow clone (`fetch-depth: 1`): still 1 clone

**Formula**: `ciClones = count of actions/checkout steps that ran today`

### Finding 2: GITHUB_TOKEN = 1 unique per day

No matter how many jobs or workflow runs execute in a day, they all share the same `GITHUB_TOKEN` identity. The Traffic API sees them as **one unique cloner**.

- 9 matrix jobs: 1 unique
- 3 separate dispatches: 1 unique
- 2 checkouts in one job: 1 unique

### Finding 3: PATs are separate identities

When a workflow uses a Personal Access Token instead of the default `GITHUB_TOKEN`, it registers as a **different unique cloner** (Day 8: 2 clones, 2 uniques).

### Finding 4: GitHub Pages builds produce hidden clones

The `pages build and deployment` workflow performs an internal clone that is **not** visible as an `actions/checkout` step. Each Pages build = 1 additional clone (Day 9). While Pages is enabled, this happens on every push to the configured branch.

### Finding 5: Workflows without checkout = zero clones

Running a GitHub Actions workflow that never calls `actions/checkout` produces **no clone events** (Day 1). The Traffic API only counts actual git operations.

## The Formulas

Based on these findings, here's how GitHub Traffic Tracker computes organic metrics:

### Organic Clones

```
ciCheckouts  = count of actions/checkout steps across all jobs today
pagesBuilds  = count of "pages build and deployment" runs today
totalCiClones = ciCheckouts + pagesBuilds

organicClones = max(0, rawClones - totalCiClones)
```

Each `actions/checkout` step = 1 clone. Each Pages build = 1 clone. Subtract them from the raw total. The `max(0, ...)` floor prevents negative values from API timing differences.

### Organic Unique Clones

Unique clones are harder because the Traffic API reports unique *identities*, not unique *operations*. We can't simply subtract CI checkouts from unique counts.

Instead, we estimate how many of the day's unique cloners were CI:

```
ciRate          = totalCiClones / rawClones
ciUniqueByPct   = round(rawUniques * ciRate)
ciUniqueCeiling = ciRuns   // distinct workflow runs with checkouts
ciUniqueClones  = min(ciUniqueByPct, ciUniqueCeiling)

organicUniqueClones = max(0, rawUniques - ciUniqueClones)
```

**Why this works**:
- The **proportional estimate** (`rawUniques * ciRate`) scales unique CI attribution by how much of the day's traffic was CI
- The **ceiling** (`ciRuns`) prevents over-attribution -- N workflow runs can't produce more than N unique CI identities
- Together, `min(proportional, ceiling)` handles both high-CI days (ceiling kicks in) and mixed days (proportion kicks in)

**Verified**: This formula produces **zero error** across all 14 experiments, including the tricky PAT case (Day 8) where two different CI tokens both needed to be attributed as CI.

### Cumulative Totals

Daily organic values are accumulated using a **delta method** rather than global subtraction:

```
totalOrganicClones += (todayOrganic - previousTodayOrganic)
```

This avoids "phantom CI" drift where global `totalClones - totalCiCheckouts` can diverge from the sum of daily organics.

## Known Limitations

1. **Custom step names**: If a workflow uses `name: "My Custom Step"` on an `actions/checkout` step, the CI detector won't recognize it. The GitHub Jobs API exposes step names but not the underlying action (`step.uses`).

2. **Codespaces**: Creating a GitHub Codespace likely clones the repo, appearing as an "organic" clone. We haven't tested this.

3. **Third-party CI**: External CI services (Jenkins, CircleCI) that clone via PAT will appear as organic traffic since they don't use `actions/checkout`.

4. **Pages build naming**: Detection relies on the workflow name `"pages build and deployment"` being consistent across GitHub configurations.

## Methodology Notes

- **Testbed repo**: `djdarcy/gtt-ci-clone-testbed` (private)
- **Duration**: 22 days (Feb 28 -- Mar 21, 2026)
- **Observer**: Zero-contamination workflow using GitHub Contents API
- **Analysis tool**: `tests/research/ci-clone-counting/analyze.py`
- **Formula verification**: `tests/one-offs/verify_formula_rmse.py`

All experiment definitions, raw observation data, and analysis scripts are available in this repository under `tests/research/ci-clone-counting/`.

## Related

- [GitHub Traffic Tracker](https://github.com/djdarcy/github-traffic-tracker) -- the project that uses these formulas
- [Issue #49](https://github.com/djdarcy/github-traffic-tracker/issues/49) -- the CI clone testbed tracking issue
- [vladkens/ghstats](https://github.com/vladkens/ghstats) -- an alternative approach (self-hosted Docker, no CI detection)
