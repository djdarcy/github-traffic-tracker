#!/usr/bin/env python3
"""Verify organic unique clone formulas against experiment data.

Compares proportional+ceiling vs unique_per_day models,
both with and without Pages build detection.

Part of the CI Clone Testbed analysis (Issue #49).
"""
import math

# Raw experiment data with corrected values
# Format: (exp_id, raw_clones, raw_uniques, ci_checkouts, ci_runs, pages_builds, expected_organic_uniques)
#
# ci_checkouts = actions/checkout steps that actually ran
# ci_runs = distinct workflow runs with >= 1 checkout
# pages_builds = "pages build and deployment" runs
# expected_organic_uniques = ground truth (0 if all clones are CI, 1 if human cloned)
experiments = [
    ('exp-00', 0, 0, 0, 0, 0, 0),   # Baseline: no activity
    ('exp-01', 0, 0, 0, 0, 0, 0),   # Workflow but no checkout
    ('exp-02', 1, 1, 1, 1, 0, 0),   # Single checkout
    ('exp-03', 1, 1, 1, 1, 0, 0),   # Fetch-depth=1
    ('exp-04', 2, 1, 2, 1, 0, 0),   # Two checkouts, one job
    ('exp-05', 9, 1, 9, 1, 0, 0),   # 3x3 matrix (1 run = 1 workflow dispatch, but 9 jobs)
    ('exp-06', 3, 1, 3, 3, 0, 0),   # 3 dispatches = 3 runs
    ('exp-07', 1, 1, 0, 0, 0, 1),   # Manual clone = organic
    ('exp-08', 2, 2, 2, 2, 0, 0),   # GITHUB_TOKEN + PAT = 2 runs, 2 checkouts, 0 organic
    ('exp-09', 4, 1, 2, 1, 2, 0),   # 2 exp checkouts + 2 pages builds (1 failed exp run = still 1 ci_run for that workflow)
    ('exp-10', 2, 1, 1, 1, 1, 0),   # 1 checkout + 1 pages build (contaminated)
    ('exp-11', 10, 1, 9, 1, 1, 0),  # 9 checkouts + 1 pages build (contaminated)
    ('exp-12', 1, 1, 1, 1, 0, 0),   # Clean single (Pages OFF)
    ('exp-13', 9, 1, 9, 1, 0, 0),   # Clean matrix (Pages OFF)
]


def proportional_ceiling(raw_clones, raw_uniques, total_ci_clones, ci_runs):
    """Current production formula: min(round(unique * ciRate), ciRuns)."""
    if raw_clones == 0:
        return 0
    ci_rate = total_ci_clones / raw_clones
    ci_unique_by_pct = round(raw_uniques * ci_rate)
    ci_unique_ceiling = ci_runs
    ci_unique_clones = min(ci_unique_by_pct, ci_unique_ceiling)
    return max(0, raw_uniques - ci_unique_clones)


def unique_per_day(raw_uniques, total_ci_clones):
    """Proposed simple formula: 1 unique for GITHUB_TOKEN per day."""
    ci_unique_clones = 1 if total_ci_clones > 0 else 0
    return max(0, raw_uniques - ci_unique_clones)


def organic_clones(raw_clones, total_ci_clones):
    """Organic clone formula (same for both models)."""
    return max(0, raw_clones - total_ci_clones)


def rmse(errors):
    if not errors:
        return float('inf')
    return math.sqrt(sum(e ** 2 for e in errors) / len(errors))


def main():
    print("=" * 90)
    print("Formula Verification: Organic Unique Clones")
    print("=" * 90)

    # Test with Pages detection (proposed improvement)
    print("\n--- WITH Pages Build Detection ---\n")

    header = f"{'Exp':<8} {'Truth':>5} {'Prop':>5} {'PDay':>5} | {'Raw':>4} {'Uniq':>4} {'CI':>3} {'Runs':>4} {'Pgs':>3} {'TotCI':>5}"
    print(header)
    print("-" * len(header))

    prop_errors = []
    pday_errors = []

    for exp_id, raw_c, raw_u, ci_co, ci_r, pages, truth in experiments:
        total_ci = ci_co + pages
        # For proportional formula, ci_runs should include pages builds as distinct runs
        total_ci_runs = ci_r + (1 if pages > 0 else 0)

        pred_prop = proportional_ceiling(raw_c, raw_u, total_ci, total_ci_runs)
        pred_pday = unique_per_day(raw_u, total_ci)

        prop_err = pred_prop - truth
        pday_err = pred_pday - truth

        prop_errors.append(prop_err)
        pday_errors.append(pday_err)

        marker_p = "*" if prop_err != 0 else " "
        marker_d = "*" if pday_err != 0 else " "

        print(f"{exp_id:<8} {truth:>5} {pred_prop:>4}{marker_p} {pred_pday:>4}{marker_d} | {raw_c:>4} {raw_u:>4} {ci_co:>3} {ci_r:>4} {pages:>3} {total_ci:>5}")

    print(f"\nRMSE Proportional+Ceiling: {rmse(prop_errors):.4f}")
    print(f"RMSE Unique Per-Day:       {rmse(pday_errors):.4f}")
    print(f"Proportional errors: {[e for e in prop_errors if e != 0]}")
    print(f"Per-Day errors:      {[e for e in pday_errors if e != 0]}")

    # Test WITHOUT Pages detection (current production)
    print("\n--- WITHOUT Pages Build Detection (current production) ---\n")

    prop_errors_nopg = []
    pday_errors_nopg = []

    for exp_id, raw_c, raw_u, ci_co, ci_r, pages, truth in experiments:
        # No pages detection: only count checkout steps
        total_ci = ci_co  # pages NOT included
        pred_prop = proportional_ceiling(raw_c, raw_u, total_ci, ci_r)
        pred_pday = unique_per_day(raw_u, total_ci)

        prop_errors_nopg.append(pred_prop - truth)
        pday_errors_nopg.append(pred_pday - truth)

    print(f"RMSE Proportional+Ceiling: {rmse(prop_errors_nopg):.4f}")
    print(f"RMSE Unique Per-Day:       {rmse(pday_errors_nopg):.4f}")
    print(f"Proportional errors: {[(experiments[i][0], e) for i, e in enumerate(prop_errors_nopg) if e != 0]}")
    print(f"Per-Day errors:      {[(experiments[i][0], e) for i, e in enumerate(pday_errors_nopg) if e != 0]}")

    # Also verify the clone formula
    print("\n--- Clone Formula Verification (with Pages) ---\n")
    clone_errors = []
    for exp_id, raw_c, raw_u, ci_co, ci_r, pages, truth in experiments:
        total_ci = ci_co + pages
        pred_organic = organic_clones(raw_c, total_ci)
        # For clones, expected organic = raw - total_ci (should be 0 for all CI-only,
        # 1 for exp-07 manual clone)
        expected_organic_clones = 1 if exp_id == 'exp-07' else 0
        err = pred_organic - expected_organic_clones
        clone_errors.append(err)
        if err != 0:
            print(f"  {exp_id}: predicted={pred_organic}, expected={expected_organic_clones}, error={err}")

    if all(e == 0 for e in clone_errors):
        print("  All clone predictions correct (0 error)")
    print(f"  Clone RMSE: {rmse(clone_errors):.4f}")

    # Edge case analysis
    print("\n--- Edge Case Scenarios ---\n")

    # Scenario: 1 human + 99 CI matrix clones
    print("Scenario: 1 human clone + 99 CI matrix clones (1 workflow dispatch)")
    raw_c, raw_u, ci_co, ci_r = 100, 2, 99, 1
    prop = proportional_ceiling(raw_c, raw_u, ci_co, ci_r)
    pday = unique_per_day(raw_u, ci_co)
    print(f"  Proportional: organicUnique={prop}  (ciRate={99/100:.2f}, ciUniqByPct={round(2*99/100)}, ceiling={ci_r})")
    print(f"  Per-Day:      organicUnique={pday}")
    print(f"  Expected: 1 (the human)")

    # Scenario: 2 humans + 2 CI runs with PATs
    print("\nScenario: 2 human clones + 2 CI-PAT clones (4 total, 4 unique)")
    raw_c, raw_u, ci_co, ci_r = 4, 4, 2, 2
    prop = proportional_ceiling(raw_c, raw_u, ci_co, ci_r)
    pday = unique_per_day(raw_u, ci_co)
    print(f"  Proportional: organicUnique={prop}  (ciRate={2/4:.2f}, ciUniqByPct={round(4*2/4)}, ceiling={ci_r})")
    print(f"  Per-Day:      organicUnique={pday}")
    print(f"  Expected: 2 (the humans)")

    # Scenario: 5 human clones + 1 CI checkout
    print("\nScenario: 5 human clones + 1 CI checkout (6 total, 6 unique)")
    raw_c, raw_u, ci_co, ci_r = 6, 6, 1, 1
    prop = proportional_ceiling(raw_c, raw_u, ci_co, ci_r)
    pday = unique_per_day(raw_u, ci_co)
    print(f"  Proportional: organicUnique={prop}  (ciRate={1/6:.2f}, ciUniqByPct={round(6*1/6)}, ceiling={ci_r})")
    print(f"  Per-Day:      organicUnique={pday}")
    print(f"  Expected: 5 (the humans)")


if __name__ == "__main__":
    main()
