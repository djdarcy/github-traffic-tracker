#!/usr/bin/env python3
"""CI Clone Testbed -- Formula Comparison Engine

Tests multiple candidate formulas against empirical Traffic API observations.
Joins experiment trigger dates with observer snapshots, computes prediction
errors, and produces RMSE rankings across all experiments.

Usage:
    python analyze.py --pull             # Pull latest observations from GitHub
    python analyze.py                    # Analyze all experiments with data
    python analyze.py --pull --report    # Pull + analyze + write report files
    python analyze.py --experiment exp-02  # Analyze a single experiment
    python analyze.py --summary          # Print RMSE summary table only

Data flow (all inputs are read-only, never modified):
    data/experiments/exp-*.json   (hypotheses + formula predictions)
    data/observations.json        (raw Traffic API snapshots from observer)
    experiment_state.json         (trigger timestamps from run_experiment.py)
        |
        v  [joined in memory by date]
    results/summary.json          (machine-readable output)
    results/report-tables.md      (human-readable output)

Part of the CI Clone Testbed research project (Issue #49).
Not a pytest test -- lives in tests/research/ but excluded from pytest discovery.
"""

import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Dict


# ---- PATHS ----

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
EXPERIMENTS_DIR = DATA_DIR / "experiments"
OBSERVATIONS_PATH = DATA_DIR / "observations.json"
STATE_PATH = SCRIPT_DIR / "experiment_state.json"
MANIFEST_PATH = SCRIPT_DIR / "manifest.json"
RESULTS_DIR = SCRIPT_DIR / "results"

REPO = "djdarcy/gtt-ci-clone-testbed"


# ---- DATA CLASSES ----

@dataclass
class FormulaResult:
    """One formula's prediction vs. observation for a given experiment."""
    name: str
    predicted_clones: int
    predicted_unique: Optional[int]
    actual_clones: Optional[int] = None
    actual_unique: Optional[int] = None

    @property
    def clone_error(self) -> Optional[int]:
        if self.actual_clones is None:
            return None
        return self.actual_clones - self.predicted_clones

    @property
    def unique_error(self) -> Optional[int]:
        if self.actual_unique is None or self.predicted_unique is None:
            return None
        return self.actual_unique - self.predicted_unique


# ---- PULL OBSERVATIONS FROM GITHUB ----

def pull_observations() -> bool:
    """Pull latest observations.json from the testbed repo via gh CLI.

    Saves to data/observations.json (local read-only copy).
    Returns True if successful.
    """
    print(f"Pulling observations from {REPO}...")
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{REPO}/contents/data/observations.json",
             "--jq", ".content"],
            capture_output=True, text=True, check=True
        )
        import base64
        content = base64.b64decode(result.stdout.strip()).decode("utf-8")

        # Validate it's valid JSON
        observations = json.loads(content)

        # Write to local file
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        OBSERVATIONS_PATH.write_text(json.dumps(observations, indent=2), encoding="utf-8")
        print(f"  Saved {len(observations)} observation(s) to {OBSERVATIONS_PATH.name}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"  ERROR: Failed to pull observations: {e.stderr.strip()}")
        return False
    except (json.JSONDecodeError, Exception) as e:
        print(f"  ERROR: Invalid observation data: {e}")
        return False


# ---- DATE MATCHING ----

def load_observations() -> List[dict]:
    """Load local observations file."""
    if not OBSERVATIONS_PATH.exists():
        return []
    with open(OBSERVATIONS_PATH) as f:
        return json.load(f)


def load_state() -> dict:
    """Load experiment state (trigger timestamps)."""
    if not STATE_PATH.exists():
        return {"experiments": []}
    with open(STATE_PATH) as f:
        return json.load(f)


def get_trigger_date(exp_id: str, state: dict) -> Optional[str]:
    """Get the UTC date an experiment was triggered (from state file).

    Returns date string like '2026-03-01' or None if not triggered.
    """
    for exp in state.get("experiments", []):
        if exp["id"] == exp_id and exp.get("triggered_at"):
            ts = exp["triggered_at"]
            return ts[:10]  # Extract YYYY-MM-DD from ISO timestamp
    return None


def find_day_clones(observations: List[dict], target_date: str) -> Optional[dict]:
    """Find clone counts for a specific UTC date from observations.

    Searches through all observation snapshots for the per-day entry
    matching target_date. Returns {"count": N, "uniques": N} or None.

    The Traffic API returns a 14-day rolling window with per-day breakdowns.
    An observation taken on Day N+1 will contain Day N's final counts.
    """
    target_ts = f"{target_date}T00:00:00Z"

    # Search observations in reverse order (most recent first)
    # A later observation is more likely to have the final count for a given day
    for obs in reversed(observations):
        clones_data = obs.get("clones", {})
        for day_entry in clones_data.get("clones", []):
            if day_entry.get("timestamp") == target_ts:
                return {
                    "count": day_entry.get("count", 0),
                    "uniques": day_entry.get("uniques", 0),
                }
    return None


def find_previous_day_clones(observations: List[dict], target_date: str) -> Optional[dict]:
    """Find clone counts for the day BEFORE target_date.

    Used to compute deltas: post - pre = experiment's contribution.
    """
    dt = datetime.strptime(target_date, "%Y-%m-%d")
    from datetime import timedelta
    prev_date = (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    return find_day_clones(observations, prev_date)


def join_experiment_with_observations(exp: dict, state: dict,
                                      observations: List[dict]) -> dict:
    """Join an experiment definition with observed data.

    Returns a copy of the experiment dict with 'observed' fields filled in.
    The original experiment file is NEVER modified.
    """
    exp_copy = json.loads(json.dumps(exp))  # Deep copy
    exp_id = exp_copy["id"]
    trigger_date = get_trigger_date(exp_id, state)

    if not trigger_date:
        return exp_copy  # Not triggered yet, observed stays null

    exp_copy["date"] = trigger_date

    # Find pre (day before experiment) and post (day of experiment)
    pre = find_previous_day_clones(observations, trigger_date)
    post = find_day_clones(observations, trigger_date)

    if pre is not None:
        exp_copy["observed"]["pre"] = {
            "date_count": pre["count"],
            "date_uniques": pre["uniques"],
            "source": f"observation matching {trigger_date} - 1 day",
        }

    if post is not None:
        exp_copy["observed"]["post"] = {
            "date_count": post["count"],
            "date_uniques": post["uniques"],
            "source": f"observation matching {trigger_date}",
        }

    # Compute deltas if we have both pre and post
    if pre is not None and post is not None:
        exp_copy["observed"]["delta_clones"] = post["count"] - pre["count"]
        exp_copy["observed"]["delta_unique"] = post["uniques"] - pre["uniques"]

    return exp_copy


# ---- FORMULA ANALYSIS ----

def load_experiment(path: Path) -> dict:
    """Load an experiment JSON file."""
    with open(path) as f:
        return json.load(f)


def get_formula_predictions(exp: dict) -> List[FormulaResult]:
    """Read pre-computed formula predictions from experiment JSON."""
    formulas_data = exp.get("formulas", {})
    results = []
    for name, preds in formulas_data.items():
        results.append(FormulaResult(
            name=name,
            predicted_clones=preds.get("predicted_ci_clones", 0),
            predicted_unique=preds.get("predicted_ci_unique"),
        ))
    return results


def analyze_experiment(exp: dict) -> Optional[dict]:
    """Compare all formula predictions against observed Traffic API data.

    Returns None if the experiment has no observed data yet.
    """
    observed = exp.get("observed", {})
    delta_clones = observed.get("delta_clones")
    delta_unique = observed.get("delta_unique")

    if delta_clones is None and delta_unique is None:
        return None  # No data yet

    formulas = get_formula_predictions(exp)

    # Apply actuals
    results = []
    for f in formulas:
        f.actual_clones = delta_clones
        f.actual_unique = delta_unique
        results.append({
            "formula": f.name,
            "predicted_clones": f.predicted_clones,
            "actual_clones": f.actual_clones,
            "clone_error": f.clone_error,
            "predicted_unique": f.predicted_unique,
            "actual_unique": f.actual_unique,
            "unique_error": f.unique_error,
        })

    # Find best formulas
    clone_results = [r for r in results if r["clone_error"] is not None]
    unique_results = [r for r in results if r["unique_error"] is not None]

    best_clone = min(clone_results, key=lambda r: abs(r["clone_error"]))["formula"] if clone_results else "N/A"
    best_unique = min(unique_results, key=lambda r: abs(r["unique_error"]))["formula"] if unique_results else "N/A"

    return {
        "experiment_id": exp["id"],
        "experiment_name": exp["name"],
        "date": exp.get("date"),
        "day": exp.get("day"),
        "trigger_date": exp.get("date"),
        "observed_pre": observed.get("pre"),
        "observed_post": observed.get("post"),
        "delta_clones": delta_clones,
        "delta_unique": delta_unique,
        "formula_results": results,
        "best_clone_formula": best_clone,
        "best_unique_formula": best_unique,
    }


def cumulative_accuracy(all_results: List[dict]) -> dict:
    """Aggregate formula accuracy across all experiments using RMSE.

    Lower RMSE = better formula.
    """
    formula_clone_errors: Dict[str, List[int]] = {}
    formula_unique_errors: Dict[str, List[int]] = {}

    for result in all_results:
        for fr in result["formula_results"]:
            name = fr["formula"]
            if fr["clone_error"] is not None:
                formula_clone_errors.setdefault(name, []).append(fr["clone_error"])
            if fr["unique_error"] is not None:
                formula_unique_errors.setdefault(name, []).append(fr["unique_error"])

    def rmse(errors: List[int]) -> float:
        if not errors:
            return float("inf")
        return math.sqrt(sum(e ** 2 for e in errors) / len(errors))

    def mean_error(errors: List[int]) -> float:
        if not errors:
            return float("inf")
        return sum(errors) / len(errors)

    clone_rmse = {name: round(rmse(errs), 4) for name, errs in formula_clone_errors.items()}
    unique_rmse = {name: round(rmse(errs), 4) for name, errs in formula_unique_errors.items()}
    clone_bias = {name: round(mean_error(errs), 4) for name, errs in formula_clone_errors.items()}
    unique_bias = {name: round(mean_error(errs), 4) for name, errs in formula_unique_errors.items()}

    # Sort by RMSE ascending
    clone_ranking = sorted(clone_rmse.items(), key=lambda x: x[1])
    unique_ranking = sorted(unique_rmse.items(), key=lambda x: x[1])

    return {
        "experiments_analyzed": len(all_results),
        "clone_rmse": dict(clone_ranking),
        "unique_rmse": dict(unique_ranking),
        "clone_bias": clone_bias,
        "unique_bias": unique_bias,
        "clone_winner": clone_ranking[0][0] if clone_ranking else "N/A",
        "unique_winner": unique_ranking[0][0] if unique_ranking else "N/A",
    }


# ---- OUTPUT FORMATTERS ----

def format_experiment_table(result: dict) -> str:
    """Format a single experiment's results as a markdown table."""
    lines = []
    lines.append(f"### {result['experiment_id'].upper()}: {result['experiment_name']} (Day {result['day']})")
    if result.get("date"):
        lines.append(f"Date: {result['date']}")
    lines.append(f"Observed: {result['delta_clones']} clones, {result['delta_unique']} unique")
    lines.append("")
    lines.append("| Formula | Pred Clones | Actual | Error | Pred Unique | Actual | Error |")
    lines.append("|---------|------------|--------|-------|-------------|--------|-------|")

    for fr in result["formula_results"]:
        ce = fr["clone_error"] if fr["clone_error"] is not None else "--"
        ue = fr["unique_error"] if fr["unique_error"] is not None else "--"
        pu = fr["predicted_unique"] if fr["predicted_unique"] is not None else "--"
        au = fr["actual_unique"] if fr["actual_unique"] is not None else "--"
        marker_c = " **" if fr["formula"] == result["best_clone_formula"] else ""
        marker_c_end = "**" if marker_c else ""
        lines.append(
            f"| {marker_c}{fr['formula']}{marker_c_end} "
            f"| {fr['predicted_clones']} | {fr['actual_clones']} | {ce} "
            f"| {pu} | {au} | {ue} |"
        )

    lines.append(f"\nBest clone formula: **{result['best_clone_formula']}**")
    lines.append(f"Best unique formula: **{result['best_unique_formula']}**")
    return "\n".join(lines)


def format_rmse_table(accuracy: dict) -> str:
    """Format the RMSE summary as a markdown table."""
    lines = []
    lines.append("## Formula Accuracy Ranking (RMSE)")
    lines.append(f"Experiments analyzed: {accuracy['experiments_analyzed']}")
    lines.append("")
    lines.append("### Clone Count Accuracy")
    lines.append("| Rank | Formula | RMSE | Bias (mean error) |")
    lines.append("|------|---------|------|-------------------|")
    for rank, (name, rmse_val) in enumerate(accuracy["clone_rmse"].items(), 1):
        bias = accuracy["clone_bias"].get(name, "--")
        marker = " **(winner)**" if rank == 1 else ""
        lines.append(f"| {rank} | {name}{marker} | {rmse_val} | {bias} |")

    lines.append("")
    lines.append("### Unique Clone Accuracy")
    lines.append("| Rank | Formula | RMSE | Bias (mean error) |")
    lines.append("|------|---------|------|-------------------|")
    for rank, (name, rmse_val) in enumerate(accuracy["unique_rmse"].items(), 1):
        bias = accuracy["unique_bias"].get(name, "--")
        marker = " **(winner)**" if rank == 1 else ""
        lines.append(f"| {rank} | {name}{marker} | {rmse_val} | {bias} |")

    return "\n".join(lines)


# ---- MAIN ----

def main():
    import argparse

    parser = argparse.ArgumentParser(description="CI Clone Testbed -- Formula Comparison Engine")
    parser.add_argument("--pull", "-p", action="store_true",
                        help="Pull latest observations.json from GitHub before analyzing")
    parser.add_argument("--experiment", "-e",
                        help="Analyze a single experiment by ID (e.g., exp-02)")
    parser.add_argument("--summary", "-s", action="store_true",
                        help="Print RMSE summary only")
    parser.add_argument("--report", "-r", action="store_true",
                        help="Generate results/report-tables.md and results/summary.json")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Output results as JSON")
    args = parser.parse_args()

    # Step 1: Pull if requested
    if args.pull:
        if not pull_observations():
            print("Pull failed. Continuing with local data (if any)...")

    # Step 2: Load all data sources (read-only)
    experiment_files = sorted(EXPERIMENTS_DIR.glob("exp-*.json"))
    if not experiment_files:
        print(f"No experiment files found in {EXPERIMENTS_DIR}")
        sys.exit(1)

    observations = load_observations()
    state = load_state()

    if not observations:
        print("No observations available. Run with --pull to fetch from GitHub.")
        print("Or trigger the observer: python run_experiment.py --observe")

    # Step 3: Join experiments with observations (in memory only)
    joined_experiments = []
    for ef in experiment_files:
        raw_exp = load_experiment(ef)
        joined = join_experiment_with_observations(raw_exp, state, observations)
        joined_experiments.append(joined)

    # Step 4: Analyze
    if args.experiment:
        matches = [e for e in joined_experiments if args.experiment in e["id"]]
        if not matches:
            print(f"Experiment '{args.experiment}' not found")
            sys.exit(1)
        result = analyze_experiment(matches[0])
        if result is None:
            print(f"No observed data for {matches[0]['id']} yet.")
            sys.exit(0)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(format_experiment_table(result))
        return

    # Analyze all experiments with data
    all_results = []
    pending = []
    for exp in joined_experiments:
        result = analyze_experiment(exp)
        if result is not None:
            all_results.append(result)
        else:
            pending.append(exp["id"])

    if not all_results:
        print("No experiments have observed data yet.")
        print(f"Pending: {', '.join(pending)}")
        if not observations:
            print("\nHint: Run 'python analyze.py --pull' after the observer has captured data.")
        sys.exit(0)

    # Compute accuracy
    accuracy = cumulative_accuracy(all_results)

    if args.json:
        output = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "observations_count": len(observations),
            "experiments": all_results,
            "accuracy": accuracy,
            "pending": pending,
        }
        print(json.dumps(output, indent=2))
        return

    if args.summary:
        print(format_rmse_table(accuracy))
        if pending:
            print(f"\nPending experiments: {', '.join(pending)}")
        return

    # Full output
    report_lines = ["# CI Clone Testbed -- Analysis Results\n"]
    report_lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    report_lines.append(f"Observations: {len(observations)} snapshots")
    report_lines.append(f"Experiments with data: {len(all_results)} / {len(joined_experiments)}")
    report_lines.append("")

    for result in all_results:
        report_lines.append(format_experiment_table(result))
        report_lines.append("\n---\n")

    report_lines.append(format_rmse_table(accuracy))

    if pending:
        report_lines.append(f"\n\n## Pending Experiments\n")
        for p in pending:
            report_lines.append(f"- {p}")

    report_text = "\n".join(report_lines)

    if args.report:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        report_path = RESULTS_DIR / "report-tables.md"
        report_path.write_text(report_text, encoding="utf-8")

        # Also write summary.json
        summary_path = RESULTS_DIR / "summary.json"
        summary = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "observations_count": len(observations),
            "experiments": all_results,
            "accuracy": accuracy,
            "pending": pending,
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        print(f"Report written to {report_path}")
        print(f"Summary written to {summary_path}")
    else:
        print(report_text)


if __name__ == "__main__":
    main()
