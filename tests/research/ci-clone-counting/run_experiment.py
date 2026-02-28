#!/usr/bin/env python3
"""CI Clone Testbed -- Daily Experiment Launcher

Run this once per day to trigger the next experiment in sequence.
Includes safety checks for timing, UTC day boundaries, and experiment order.

Usage:
    python run_experiment.py           # Normal mode -- trigger next experiment
    python run_experiment.py --status  # Show current progress
    python run_experiment.py --force   # Skip timing checks (use with caution)
    python run_experiment.py --observe # Manually trigger the observer

Desktop shortcut target:
    pythonw run_experiment.py
    -- or --
    python run_experiment.py
"""

import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---- CONFIG ----

REPO = "djdarcy/gtt-ci-clone-testbed"
SCRIPT_DIR = Path(__file__).parent
STATE_PATH = SCRIPT_DIR / "experiment_state.json"
MANIFEST_PATH = SCRIPT_DIR / "manifest.json"

# Timing constraints
UTC_HOUR_CUTOFF = 22       # Don't trigger after 10 PM UTC (5 PM EST)
MIN_HOURS_BETWEEN = 20     # At least 20 hours between experiments (ensures new UTC day)

# Experiment schedule with special handling notes
SPECIAL_EXPERIMENTS = {
    "exp-00": {
        "type": "baseline",
        "instructions": "Day 0 is the baseline. Only the observer runs. No experiment workflow.",
    },
    "exp-06": {
        "type": "multi-dispatch",
        "dispatches": 3,
        "spacing_minutes": 60,
        "instructions": (
            "Exp 06 requires 3 separate dispatches ~1 hour apart.\n"
            "This script will trigger the first one now.\n"
            "You must manually trigger the 2nd and 3rd runs later today:\n"
            "  gh workflow run exp-06-multi-run.yml --repo {repo}\n"
            "Run #2 at: {{time2}}\n"
            "Run #3 at: {{time3}}"
        ),
    },
    "exp-07": {
        "type": "manual",
        "instructions": (
            "Exp 07 is a MANUAL clone -- do NOT trigger any workflow.\n"
            "Instead, run this from your local machine:\n"
            "  git clone https://github.com/{repo}.git /tmp/gtt-cal-test\n"
            "Then delete the clone:\n"
            "  rm -rf /tmp/gtt-cal-test\n"
            "The observer will capture the clone event tomorrow at 04:30 UTC."
        ),
    },
    "exp-08": {
        "type": "two-dispatch",
        "instructions": (
            "Exp 08 requires 2 dispatches with different inputs.\n"
            "This script will trigger BOTH:\n"
            "  1. use_pat=false (GITHUB_TOKEN)\n"
            "  2. use_pat=true  (PAT)\n"
            "Both will be triggered now with a 5-minute gap."
        ),
    },
    "exp-09": {
        "type": "pages-setup",
        "instructions": (
            "Exp 09 requires Pages to be ENABLED before triggering.\n"
            "Go to: https://github.com/{repo}/settings/pages\n"
            "  Source: Deploy from a branch\n"
            "  Branch: main, /docs folder\n"
            "  Save\n"
            "Then press Enter here to trigger the workflow.\n"
            "IMPORTANT: Disable Pages again AFTER the observer runs tomorrow."
        ),
    },
}


# ---- STATE MANAGEMENT ----

def load_state() -> dict:
    """Load or initialize the experiment state."""
    if STATE_PATH.exists():
        with open(STATE_PATH) as f:
            return json.load(f)

    # Initialize from manifest
    manifest = load_manifest()
    state = {
        "repo": REPO,
        "created_at": now_utc_str(),
        "experiments": [],
    }

    for exp in manifest["experiments"]:
        entry = {
            "day": exp["day"],
            "id": exp["id"],
            "name": exp["name"],
            "workflow": exp.get("workflow"),
            "status": "pending",
            "triggered_at": None,
            "observed_at": None,
            "notes": "",
        }
        state["experiments"].append(entry)

    # Mark Day 0 as completed (baseline already captured)
    state["experiments"][0]["status"] = "completed"
    state["experiments"][0]["triggered_at"] = "2026-02-28T14:57:26Z"
    state["experiments"][0]["observed_at"] = "2026-02-28T14:57:33Z"
    state["experiments"][0]["notes"] = "Baseline -- zero clones confirmed via API-only setup."

    save_state(state)
    return state


def save_state(state: dict):
    """Save state to disk."""
    state["last_updated"] = now_utc_str()
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def load_manifest() -> dict:
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_utc_str() -> str:
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- SAFETY CHECKS ----

def check_utc_time() -> tuple[bool, str]:
    """Ensure we're not too late in the UTC day."""
    hour = now_utc().hour
    if hour >= UTC_HOUR_CUTOFF:
        est_cutoff = UTC_HOUR_CUTOFF - 5  # rough EST conversion
        return False, (
            f"Current UTC hour is {hour}:00 -- past the {UTC_HOUR_CUTOFF}:00 UTC cutoff "
            f"(~{est_cutoff}:00 PM EST).\n"
            f"Triggering now risks the clone being attributed to tomorrow's UTC day.\n"
            f"Try again tomorrow morning."
        )
    return True, f"UTC time OK ({now_utc().strftime('%H:%M')} UTC, cutoff is {UTC_HOUR_CUTOFF}:00)"


def check_spacing(state: dict) -> tuple[bool, str]:
    """Ensure enough time has passed since the last experiment."""
    completed = [e for e in state["experiments"] if e["status"] == "completed" and e["triggered_at"]]
    if not completed:
        return True, "No previous experiments -- OK to proceed."

    last = max(completed, key=lambda e: e["triggered_at"])
    last_time = datetime.fromisoformat(last["triggered_at"].replace("Z", "+00:00"))
    elapsed = now_utc() - last_time
    hours = elapsed.total_seconds() / 3600

    if hours < MIN_HOURS_BETWEEN:
        remaining = MIN_HOURS_BETWEEN - hours
        return False, (
            f"Last experiment ({last['id']}) was triggered {hours:.1f} hours ago.\n"
            f"Minimum spacing is {MIN_HOURS_BETWEEN} hours.\n"
            f"Wait ~{remaining:.1f} more hours (ensures a new UTC day)."
        )

    return True, f"Spacing OK ({hours:.1f} hours since {last['id']})"


def check_utc_day_different(state: dict) -> tuple[bool, str]:
    """Ensure we're on a different UTC day than the last experiment."""
    completed = [e for e in state["experiments"] if e["status"] == "completed" and e["triggered_at"]]
    if not completed:
        return True, "No previous experiments."

    last = max(completed, key=lambda e: e["triggered_at"])
    last_time = datetime.fromisoformat(last["triggered_at"].replace("Z", "+00:00"))
    today = now_utc().date()
    last_date = last_time.date()

    if today == last_date:
        return False, (
            f"Last experiment ({last['id']}) was triggered today ({last_date}).\n"
            f"Each experiment must be on a separate UTC day.\n"
            f"Wait until tomorrow (UTC midnight = 7:00 PM EST tonight)."
        )

    return True, f"UTC day OK (today={today}, last={last_date})"


# ---- WORKFLOW TRIGGERS ----

def gh_run(workflow: str, inputs: dict = None) -> bool:
    """Trigger a workflow via gh CLI."""
    cmd = ["gh", "workflow", "run", workflow, "--repo", REPO]
    if inputs:
        for key, val in inputs.items():
            cmd.extend(["-f", f"{key}={val}"])

    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()}")
        return False
    return True


def trigger_experiment(exp: dict, state: dict) -> bool:
    """Trigger an experiment, handling special cases."""
    exp_id = exp["id"]
    special = SPECIAL_EXPERIMENTS.get(exp_id, {})
    exp_type = special.get("type", "standard")

    if exp_type == "baseline":
        print("Day 0 baseline is already completed.")
        return True

    if exp_type == "manual":
        instructions = special["instructions"].format(repo=REPO)
        print(f"\n{'='*60}")
        print(f"MANUAL EXPERIMENT -- {exp['name']}")
        print(f"{'='*60}")
        print(instructions)
        resp = input("\nDid you perform the manual clone? (y/n): ").strip().lower()
        if resp == "y":
            return True
        print("Experiment not marked as triggered. Run this script again after cloning.")
        return False

    if exp_type == "pages-setup":
        instructions = special["instructions"].format(repo=REPO)
        print(f"\n{'='*60}")
        print(f"SETUP REQUIRED -- {exp['name']}")
        print(f"{'='*60}")
        print(instructions)
        input("\nPress Enter when Pages is enabled...")
        print(f"\nTriggering {exp['workflow']}...")
        return gh_run(exp["workflow"])

    if exp_type == "two-dispatch":
        instructions = special["instructions"].format(repo=REPO)
        print(f"\n{instructions}\n")

        print("Dispatch 1: use_pat=false (GITHUB_TOKEN)")
        ok1 = gh_run(exp["workflow"], {"use_pat": "false"})
        if not ok1:
            return False

        print("\nWaiting 10 seconds before second dispatch...")
        import time
        time.sleep(10)

        print("Dispatch 2: use_pat=true (PAT)")
        ok2 = gh_run(exp["workflow"], {"use_pat": "true"})
        return ok2

    if exp_type == "multi-dispatch":
        now = now_utc()
        time2 = (now + timedelta(minutes=60)).strftime("%H:%M UTC")
        time3 = (now + timedelta(minutes=120)).strftime("%H:%M UTC")
        instructions = special["instructions"].format(repo=REPO)
        instructions = instructions.replace("{{time2}}", time2).replace("{{time3}}", time3)
        print(f"\n{instructions}\n")

        print("Dispatch 1 of 3:")
        ok = gh_run(exp["workflow"])
        if not ok:
            return False
        print(f"\nReminder: trigger runs #2 and #3 manually at {time2} and {time3}.")
        return True

    # Standard single-dispatch experiment
    if not exp.get("workflow"):
        print(f"No workflow for {exp_id} -- skipping trigger.")
        return True

    print(f"Triggering {exp['workflow']}...")
    return gh_run(exp["workflow"])


# ---- DISPLAY ----

def print_status(state: dict):
    """Print current experiment progress."""
    print(f"\n{'='*60}")
    print(f"CI Clone Testbed -- Experiment Progress")
    print(f"Repo: {state['repo']}")
    print(f"{'='*60}\n")

    print(f"{'Day':<5} {'ID':<8} {'Name':<30} {'Status':<12} {'Triggered':<22}")
    print(f"{'-'*5} {'-'*8} {'-'*30} {'-'*12} {'-'*22}")

    for exp in state["experiments"]:
        triggered = exp.get("triggered_at") or ""
        if triggered:
            # Show in UTC format
            t = datetime.fromisoformat(triggered.replace("Z", "+00:00"))
            triggered = t.strftime("%Y-%m-%d %H:%M UTC")
        status_marker = {
            "completed": "[done]",
            "pending": "[ -- ]",
            "in_progress": "[...]",
            "skipped": "[skip]",
        }.get(exp["status"], exp["status"])

        print(f"{exp['day']:<5} {exp['id']:<8} {exp['name']:<30} {status_marker:<12} {triggered:<22}")

    completed = sum(1 for e in state["experiments"] if e["status"] == "completed")
    total = len(state["experiments"])
    print(f"\nProgress: {completed}/{total} experiments completed")

    # Show what's next
    next_exp = next((e for e in state["experiments"] if e["status"] == "pending"), None)
    if next_exp:
        print(f"Next up: Day {next_exp['day']} -- {next_exp['name']}")
    else:
        print("All experiments completed!")


def print_header():
    print(f"""
====================================================
   CI Clone Testbed -- Daily Experiment Launcher
   github-traffic-tracker Issue #49
====================================================
    Time: {now_utc().strftime('%Y-%m-%d %H:%M:%S')} UTC
    """)


# ---- MAIN ----

def main():
    import argparse
    parser = argparse.ArgumentParser(description="CI Clone Testbed -- Daily Experiment Launcher")
    parser.add_argument("--status", "-s", action="store_true", help="Show progress")
    parser.add_argument("--force", "-f", action="store_true", help="Skip timing checks")
    parser.add_argument("--observe", "-o", action="store_true", help="Trigger observer manually")
    args = parser.parse_args()

    print_header()
    state = load_state()

    if args.status:
        print_status(state)
        return

    if args.observe:
        print("Triggering observer workflow...")
        ok = gh_run("observe-traffic.yml")
        if ok:
            print("Observer triggered. Check results in ~30 seconds:")
            print(f"  gh api repos/{REPO}/contents/data/observations.json --jq '.content' | base64 -d | jq '.[-1]'")
        return

    # Find next pending experiment
    next_exp = next((e for e in state["experiments"] if e["status"] == "pending"), None)
    if not next_exp:
        print("All experiments completed!")
        print_status(state)
        return

    print(f"Next experiment: Day {next_exp['day']} -- {next_exp['name']} ({next_exp['id']})")
    print()

    # Safety checks
    checks = [
        ("UTC time window", check_utc_time()),
        ("Experiment spacing", check_spacing(state)),
        ("UTC day boundary", check_utc_day_different(state)),
    ]

    all_ok = True
    for name, (ok, msg) in checks:
        symbol = "PASS" if ok else "FAIL"
        print(f"  [{symbol}] {name}: {msg}")
        if not ok:
            all_ok = False

    if not all_ok and not args.force:
        print("\nSafety checks failed. Use --force to override (not recommended).")
        return

    if not all_ok and args.force:
        print("\n  WARNING: Overriding safety checks with --force!")

    # Confirmation
    print(f"\nReady to trigger: Day {next_exp['day']} -- {next_exp['name']}")

    # Show special instructions if any
    special = SPECIAL_EXPERIMENTS.get(next_exp["id"], {})
    if special.get("instructions"):
        preview = special["instructions"].format(repo=REPO)
        # Clean up template placeholders for preview
        preview = preview.replace("{{time2}}", "~1hr from now").replace("{{time3}}", "~2hrs from now")
        print(f"\n  Note: {preview.split(chr(10))[0]}")

    resp = input("\nProceed? (y/n): ").strip().lower()
    if resp != "y":
        print("Aborted.")
        return

    # Trigger
    ok = trigger_experiment(next_exp, state)
    if ok:
        next_exp["status"] = "completed"
        next_exp["triggered_at"] = now_utc_str()
        save_state(state)
        print(f"\nDay {next_exp['day']} ({next_exp['id']}) triggered and recorded.")

        # Show what's next
        upcoming = next((e for e in state["experiments"] if e["status"] == "pending"), None)
        if upcoming:
            print(f"Next experiment: Day {upcoming['day']} -- {upcoming['name']} (trigger tomorrow)")
        else:
            print("That was the last experiment! Run analyze.py to compute results.")

        print(f"\nObserver will auto-run at 04:30 UTC tonight (11:30 PM EST).")
        print(f"Or trigger manually: python {Path(__file__).name} --observe")
    else:
        print(f"\nTrigger failed. Experiment NOT marked as completed. Try again.")


if __name__ == "__main__":
    main()
