"""
Generate synthetic state.json and archive files for dashboard testing.

Creates realistic traffic data without touching live gists. Output goes
to tests/one-offs/test_dashboard_data/ by default.

Usage:
    python scripts/generate-test-data.py                    # 90-day default
    python scripts/generate-test-data.py --days 180         # 6 months
    python scripts/generate-test-data.py --output /tmp/test # custom output dir
    python scripts/generate-test-data.py --profile popular  # high-traffic project
"""

import argparse
import json
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone


# Traffic profiles: realistic growth curves for different project types
PROFILES = {
    "new": {
        "description": "New project, low traffic, gradual growth",
        "base_clones": 2, "clone_growth": 0.02, "clone_variance": 0.5,
        "base_views": 5, "view_growth": 0.03, "view_variance": 0.4,
        "base_downloads": 0, "dl_growth": 0.01, "dl_variance": 0.8,
        "ci_workflows": 1, "ci_runs_per_day": 1,
        "stars_start": 0, "stars_growth": 0.05,
        "forks_start": 0, "forks_growth": 0.01,
    },
    "moderate": {
        "description": "Established project, steady traffic",
        "base_clones": 15, "clone_growth": 0.005, "clone_variance": 0.3,
        "base_views": 50, "view_growth": 0.008, "view_variance": 0.3,
        "base_downloads": 10, "dl_growth": 0.005, "dl_variance": 0.4,
        "ci_workflows": 2, "ci_runs_per_day": 3,
        "stars_start": 25, "stars_growth": 0.1,
        "forks_start": 5, "forks_growth": 0.03,
    },
    "popular": {
        "description": "Popular project, high traffic with spikes",
        "base_clones": 80, "clone_growth": 0.01, "clone_variance": 0.4,
        "base_views": 300, "view_growth": 0.015, "view_variance": 0.35,
        "base_downloads": 50, "dl_growth": 0.01, "dl_variance": 0.5,
        "ci_workflows": 3, "ci_runs_per_day": 8,
        "stars_start": 200, "stars_growth": 0.5,
        "forks_start": 30, "forks_growth": 0.1,
    },
}

# Referrer sources (weighted by likelihood)
REFERRERS = [
    ("Google", 0.35), ("github.com", 0.25), ("reddit.com", 0.1),
    ("stackoverflow.com", 0.08), ("twitter.com", 0.05), ("bing.com", 0.04),
    ("dev.to", 0.03), ("news.ycombinator.com", 0.03), ("medium.com", 0.02),
    ("duckduckgo.com", 0.02), ("youtube.com", 0.02), ("linkedin.com", 0.01),
]

# Popular paths templates
POPULAR_PATHS = [
    ("/ExampleOrg/example-project", "ExampleOrg/example-project"),
    ("/ExampleOrg/example-project/blob/main/README.md", "example-project/README.md"),
    ("/ExampleOrg/example-project/releases", "Releases - ExampleOrg/example-project"),
    ("/ExampleOrg/example-project/issues", "Issues - ExampleOrg/example-project"),
    ("/ExampleOrg/example-project/blob/main/docs/setup.md", "example-project/docs/setup.md"),
    ("/ExampleOrg/example-project/wiki", "Wiki - ExampleOrg/example-project"),
    ("/ExampleOrg/example-project/actions", "Actions - ExampleOrg/example-project"),
    ("/ExampleOrg/example-project/tree/main/src", "example-project/src"),
]


def generate_daily_value(base, growth_rate, day_num, variance, allow_zero=True):
    """Generate a realistic daily traffic value with growth and noise."""
    # Exponential growth curve
    trend = base * math.exp(growth_rate * day_num)

    # Day-of-week effect (weekdays slightly higher)
    dow_factor = 1.1 if day_num % 7 < 5 else 0.8

    # Random variance
    noise = random.gauss(1.0, variance)
    noise = max(0.1, noise)  # Don't go negative

    value = trend * dow_factor * noise

    # Occasional spike (release day, HN post, etc.)
    if random.random() < 0.03:
        value *= random.uniform(2.0, 5.0)

    # Occasional zero day
    if allow_zero and random.random() < 0.05:
        value = 0

    return max(0, int(round(value)))


def generate_state(days, profile_name, repo_owner, repo_name, created_date):
    """Generate a complete state.json with synthetic data."""
    profile = PROFILES[profile_name]
    end_date = datetime.now(timezone.utc).replace(hour=3, minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)

    random.seed(42)  # Reproducible output

    daily_history = []
    total_clones = 0
    total_unique_clones = 0
    total_views = 0
    total_unique_views = 0
    total_downloads = 0
    total_ci_checkouts = 0
    stars = profile["stars_start"]
    forks = profile["forks_start"]
    ci_checkouts_map = {}

    for i in range(days):
        date = start_date + timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")

        clones = generate_daily_value(
            profile["base_clones"], profile["clone_growth"], i, profile["clone_variance"]
        )
        views = generate_daily_value(
            profile["base_views"], profile["view_growth"], i, profile["view_variance"]
        )
        downloads = generate_daily_value(
            profile["base_downloads"], profile["dl_growth"], i, profile["dl_variance"]
        )

        # Unique counts: typically 40-80% of raw counts
        unique_ratio_clones = random.uniform(0.4, 0.8)
        unique_ratio_views = random.uniform(0.5, 0.85)

        # CI checkouts
        ci_runs = max(0, int(random.gauss(
            profile["ci_runs_per_day"], profile["ci_runs_per_day"] * 0.3
        )))
        ci_checkouts = ci_runs  # 1 checkout per run typically

        organic_clones = max(0, clones - ci_checkouts)
        unique_clones = max(1, int(clones * unique_ratio_clones)) if clones > 0 else 0
        unique_views = max(1, int(views * unique_ratio_views)) if views > 0 else 0

        # Organic unique estimate
        if clones > 0:
            ci_rate = ci_checkouts / clones
            ci_unique_est = min(int(round(unique_clones * ci_rate)), ci_runs)
            organic_unique_clones = max(0, unique_clones - ci_unique_est)
        else:
            organic_unique_clones = 0

        # Stars/forks grow slowly
        if random.random() < profile["stars_growth"] / days:
            stars += 1
        if random.random() < profile["forks_growth"] / days:
            forks += 1

        # Only include unique data for recent entries (simulating API 14-day window)
        days_ago = days - i
        has_uniques = days_ago <= 14

        entry = {
            "date": f"{date_str}T00:00:00Z",
            "capturedAt": f"{date_str}T03:00:00Z",
            "clones": clones,
            "downloads": downloads,
            "views": views,
            "total": clones + downloads,
            "ciCheckouts": ci_checkouts,
            "ciRuns": ci_runs,
            "organicClones": organic_clones,
            "stars": stars,
            "forks": forks,
            "openIssues": max(0, int(random.gauss(5, 2))),
        }

        if has_uniques:
            entry["uniqueClones"] = unique_clones
            entry["uniqueViews"] = unique_views
            entry["organicUniqueClones"] = organic_unique_clones

        daily_history.append(entry)

        total_clones += clones
        total_unique_clones += unique_clones if has_uniques else 0
        total_views += views
        total_unique_views += unique_views if has_uniques else 0
        total_downloads += downloads
        total_ci_checkouts += ci_checkouts

        ci_checkouts_map[date_str] = {
            "total": ci_checkouts,
            "runs": ci_runs,
            "byWorkflow": {f"CI-{j+1}": {"runs": max(1, ci_runs // profile["ci_workflows"]),
                                           "checkoutsPerRun": [1]}
                           for j in range(profile["ci_workflows"])}
        }

    # Generate referrers
    referrers = []
    for source, weight in REFERRERS[:8]:
        count = int(total_views * weight * random.uniform(0.8, 1.2) / days)
        uniques = int(count * random.uniform(0.5, 0.9))
        if count > 0:
            referrers.append({"source": source, "count": count, "uniques": uniques})
    referrers.sort(key=lambda r: r["count"], reverse=True)

    # Generate popular paths
    popular_paths = []
    for path, title in POPULAR_PATHS[:6]:
        path = path.replace("ExampleOrg", repo_owner).replace("example-project", repo_name)
        title = title.replace("ExampleOrg", repo_owner).replace("example-project", repo_name)
        count = int(random.uniform(10, 200))
        uniques = int(count * random.uniform(0.4, 0.8))
        popular_paths.append({"path": path, "title": title, "count": count, "uniques": uniques})
    popular_paths.sort(key=lambda p: p["count"], reverse=True)

    total_organic = max(0, total_clones - total_ci_checkouts)

    state = {
        "totalClones": total_clones,
        "totalUniqueClones": total_unique_clones,
        "totalDownloads": total_downloads,
        "totalViews": total_views,
        "totalUniqueViews": total_unique_views,
        "totalCiCheckouts": total_ci_checkouts,
        "totalOrganicUniqueClones": max(0, total_unique_clones - int(total_ci_checkouts * 0.6)),
        "totalCiUniqueClones": int(total_ci_checkouts * 0.6),
        "stars": stars,
        "forks": forks,
        "openIssues": daily_history[-1]["openIssues"] if daily_history else 0,
        "previousTotalDownloads": total_downloads,
        "lastSeenDates": [e["date"] for e in daily_history[-14:]],
        "lastSeenViewDates": [e["date"] for e in daily_history[-14:]],
        "referrers": referrers,
        "popularPaths": popular_paths,
        "ciCheckouts": {k: v for k, v in list(ci_checkouts_map.items())[-31:]},
        "dailyHistory": daily_history[-31:],  # Keep last 31 days like the real workflow
    }

    return state, daily_history


def generate_archive(daily_history, month_str, repo_owner, repo_name):
    """Generate a monthly archive from daily history entries."""
    month_entries = [e for e in daily_history if e["date"][:7] == month_str]
    if not month_entries:
        return None

    return {
        "repo": f"{repo_owner}/{repo_name}",
        "period": month_str,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
        "cumulativeTotals": {
            "downloads": sum(e.get("downloads", 0) for e in month_entries),
            "clones": sum(e.get("clones", 0) for e in month_entries),
            "uniqueClones": sum(e.get("uniqueClones", 0) for e in month_entries),
            "organicClones": sum(e.get("organicClones", 0) for e in month_entries),
            "views": sum(e.get("views", 0) for e in month_entries),
            "uniqueViews": sum(e.get("uniqueViews", 0) for e in month_entries),
        },
        "monthSummary": {
            "days": len(month_entries),
            "downloads": sum(e.get("downloads", 0) for e in month_entries),
            "clones": sum(e.get("clones", 0) for e in month_entries),
            "views": sum(e.get("views", 0) for e in month_entries),
        },
        "dailyHistory": month_entries,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic traffic data for dashboard testing"
    )
    parser.add_argument("--days", type=int, default=90,
                        help="Number of days of history to generate (default: 90)")
    parser.add_argument("--profile", choices=PROFILES.keys(), default="moderate",
                        help="Traffic profile (default: moderate)")
    parser.add_argument("--owner", default="ExampleOrg",
                        help="Repo owner for generated data (default: ExampleOrg)")
    parser.add_argument("--repo", default="example-project",
                        help="Repo name for generated data (default: example-project)")
    parser.add_argument("--output", default=None,
                        help="Output directory (default: tests/one-offs/test_dashboard_data/)")
    parser.add_argument("--archives", action="store_true",
                        help="Also generate monthly archive files")
    args = parser.parse_args()

    output_dir = args.output or os.path.join("tests", "one-offs", "test_dashboard_data")
    os.makedirs(output_dir, exist_ok=True)

    created_date = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")
    profile = PROFILES[args.profile]

    print(f"Generating {args.days} days of '{args.profile}' traffic data")
    print(f"  Profile: {profile['description']}")
    print(f"  Owner/Repo: {args.owner}/{args.repo}")
    print(f"  Output: {output_dir}/")

    state, full_history = generate_state(
        args.days, args.profile, args.owner, args.repo, created_date
    )

    # Write state.json
    state_path = os.path.join(output_dir, "state.json")
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    print(f"\n  state.json: {len(state['dailyHistory'])} daily entries")
    print(f"    Total clones: {state['totalClones']}")
    print(f"    Total views: {state['totalViews']}")
    print(f"    Total downloads: {state['totalDownloads']}")
    print(f"    Stars: {state['stars']}, Forks: {state['forks']}")

    # Generate archives
    if args.archives:
        months = sorted(set(e["date"][:7] for e in full_history))
        archive_count = 0
        for month in months:
            archive = generate_archive(full_history, month, args.owner, args.repo)
            if archive:
                archive_path = os.path.join(output_dir, f"archive-{month}.json")
                with open(archive_path, "w") as f:
                    json.dump(archive, f, indent=2)
                archive_count += 1
                print(f"  archive-{month}.json: {archive['monthSummary']['days']} days")
        print(f"\n  Generated {archive_count} monthly archives")

    print(f"\nDone. Files written to {output_dir}/")
    print(f"\nTo test the dashboard locally, open test_dashboard.html and point")
    print(f"its GIST_RAW_BASE to a local server serving these JSON files.")


if __name__ == "__main__":
    main()
