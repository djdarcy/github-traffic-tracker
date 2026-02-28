# CI Clone Counting Research

Controlled experiments to empirically determine how GitHub's Traffic API counts
clones from CI/CD activity. Parent issue: [github-traffic-tracker#49](https://github.com/djdarcy/github-traffic-tracker/issues/49).

## Overview

Nobody has published controlled measurements of how GitHub counts clones from
Actions workflows. We built a private testbed repo with 12 isolated experiments
(one per UTC day) and a zero-contamination observer to capture the results.

Five candidate formulas are tested against the empirical data, scored by RMSE,
and the winner becomes the basis for GTT's organic clone calculations.

## The Three Tools

| Tool | Purpose | When to use |
|------|---------|-------------|
| `run_experiment.py` | Trigger daily experiments | Once per day during the 12-day series |
| `analyze.py` | Pull data + compute results | Any time after observations exist |
| `experiment_state.json` | Progress tracker | Auto-managed by run_experiment.py |

## Phase 1: Daily Experiments (12 days)

### Setup (already done)
- Private testbed repo: `djdarcy/gtt-ci-clone-testbed`
- Created entirely via GitHub API (zero clone contamination)
- `TRAFFIC_PAT` secret configured for observer
- Day 0 baseline captured: zero clones confirmed

### Daily Routine

1. Click the `run_experiment.bat` desktop shortcut (or run `python run_experiment.py`)
2. The script shows which experiment is next and runs safety checks:
   - Not too late in UTC day (cutoff: 5 PM EST / 10 PM UTC)
   - At least 20 hours since last experiment
   - Different UTC day than last experiment
3. Confirm with `y`, the workflow is triggered and the timestamp is recorded
4. The observer auto-runs at 04:30 UTC (11:30 PM EST) and captures Traffic API data

### Commands
```bash
python run_experiment.py           # Trigger next experiment
python run_experiment.py --status  # Show progress table
python run_experiment.py --observe # Manually trigger the observer
python run_experiment.py --force   # Skip timing checks (not recommended)
```

### Experiment Schedule

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
| 10 | Replicate Single | Repeatability check -- same as Day 2? |
| 11 | Replicate Matrix | Repeatability check -- same as Day 5? |

### Special Experiments

- **Day 6 (Multi-Run)**: Requires 3 separate triggers ~1 hour apart. The script triggers the first and reminds you to trigger runs #2 and #3 manually.
- **Day 7 (Manual Clone)**: No workflow -- you run `git clone` from your local machine.
- **Day 8 (PAT vs Token)**: The script triggers both dispatches automatically (one with GITHUB_TOKEN, one with PAT).
- **Day 9 (Pages)**: Requires enabling GitHub Pages before triggering. The script walks you through the setup steps. Disable Pages after the observer runs.

### What if I miss a day?

No problem. The experiments don't need to be on consecutive days -- they just need to be on *different* UTC days. If you skip a week, run the script when you're back and it picks up where you left off. The state file tracks everything.

## Phase 2: Analysis (after experiments)

### Pulling Data

After experiments are running (or complete), pull the observer's data:

```bash
python analyze.py --pull
```

This downloads `observations.json` from the testbed repo to a local read-only copy. The observer writes a full Traffic API snapshot each day (14-day rolling window), so later snapshots contain earlier days' final counts.

### How the Join Works

The analysis joins three data sources **in memory** (no input files are ever modified):

```
experiment_state.json     "exp-02 was triggered at 2026-03-02T12:34Z"
        +
data/observations.json    "on 2026-03-02, clones=1, uniques=1"
        +
data/experiments/*.json   "exp-02 predicted: current_1to1=1, multiplier_2x=2"
        =
results/summary.json      "exp-02: current_1to1 error=0, multiplier_2x error=1"
```

For each experiment:
1. Look up trigger date from `experiment_state.json`
2. Find that date's clone counts in `observations.json`
3. Find the previous day's counts (for computing deltas)
4. Delta = experiment day - previous day = that experiment's contribution
5. Compare delta to each formula's prediction
6. Record the error (actual - predicted) for each formula

### Running Analysis

```bash
python analyze.py --pull             # Pull latest data from GitHub
python analyze.py                    # Show all results (reads local data)
python analyze.py --pull --report    # Pull + generate report files
python analyze.py --summary          # RMSE rankings only
python analyze.py -e exp-05          # Single experiment detail
python analyze.py --json             # Machine-readable output
```

### Output Files (in results/)

- `summary.json` -- Full results: per-experiment comparisons, RMSE rankings, pending list
- `report-tables.md` -- Pre-formatted markdown tables ready for the findings document

### Data Integrity Safeguards

- **Input files are never modified.** analyze.py reads experiment definitions, observations, and state -- it never writes back to them.
- **Join happens in memory only.** The `observed` fields in experiment JSONs stay null forever. All derived values exist only in `results/`.
- **Observations are append-only.** The observer on GitHub only appends to observations.json. Local copy is overwritten on each `--pull` but that's just a fresh download of the full file.
- **State file is append-only.** run_experiment.py only sets `triggered_at` and `status` once per experiment, never overwrites previous entries.
- **Idempotent analysis.** Running analyze.py 100 times produces the same output. Safe to re-run at any point.

## Phase 3: Publication (after analysis)

### Step 1: Generate Final Report
```bash
python analyze.py --pull --report
```

### Step 2: Write Findings Document
Create `docs/research/ci-clone-counting.md` in the GTT repo with:
1. Abstract -- what we tested, what we found
2. Methodology -- experiment design, observer design, timing protocol
3. Per-Experiment Results -- tables from report-tables.md
4. Formula Comparison -- RMSE ranking table, winner analysis
5. Conclusions -- which formula is most accurate, what the actual mapping is
6. Implications for GTT -- what changes to traffic-badges.yml
7. Raw Data appendix -- link to curated data

### Step 3: Curate Public Data
Create `docs/research/ci-clone-counting-data.json` -- sanitized subset:
- Experiment definitions (hypotheses, actions, results)
- Observed deltas (not raw API snapshots)
- Formula comparison results
- No PAT references, no secrets, no internal URLs

### Step 4: Update GTT Formulas (if needed)
If findings differ from current assumptions, update:
- `traffic-badges.yml` -- organic clone formula
- `docs/stats/index.html` -- dashboard fallback formula

## File Structure

```
ci-clone-counting/
  run_experiment.py          # Daily launcher (desktop shortcut target)
  run_experiment.bat         # Windows batch wrapper for desktop shortcut
  experiment_state.json      # Auto-generated progress tracker (trigger timestamps)
  analyze.py                 # Formula comparison engine (pull + join + score)
  manifest.json              # Experiment schedule definition
  README.md                  # This file
  data/
    observations.json        # Local copy of observer data (pulled from GitHub)
    experiments/             # Per-experiment hypothesis + formula predictions
      exp-00-baseline.json
      ...
      exp-11-replicate-matrix.json
  results/                   # Generated by analyze.py (never committed to git)
    summary.json             # Machine-readable RMSE rankings
    report-tables.md         # Human-readable markdown tables
  testbed-workflows/         # Local copies of workflows deployed to testbed repo
  testbed-repo-files/        # Local copies of other testbed repo files
```

## Candidate Formulas

| Formula | Clone Prediction | Unique Prediction |
|---------|-----------------|-------------------|
| current_1to1 | 1 checkout = 1 clone | MIN(pct, runs) |
| multiplier_1.5x | 1 checkout = 1.5 clones | -- |
| multiplier_2.0x | 1 checkout = 2 clones (init+fetch) | -- |
| unique_per_day | 1 checkout = 1 clone | 1 per UTC day |
| unique_per_wf | 1 checkout = 1 clone | 1 per distinct workflow |

## Design Constraints

1. **Zero-contamination observer**: Reads Traffic API via curl + PAT, writes via Contents API. No `actions/checkout`, no `git push`.
2. **API-only repo setup**: Testbed created and populated entirely via GitHub REST API. Zero git protocol operations.
3. **One experiment per UTC day**: Each experiment is the sole clone-producing activity for its day.
4. **Immutable inputs**: Experiment definitions and observations are never modified by analysis tools.

## Links

- Parent issue: [github-traffic-tracker#49](https://github.com/djdarcy/github-traffic-tracker/issues/49)
- Testbed repo: `djdarcy/gtt-ci-clone-testbed` (private)
- Analysis doc: `2026-02-28__07-36-32__dev-workflow-process_ci-clone-testbed-implementation-plan.md`
