#!/usr/bin/env python3
"""Star Radar POC -- cross-repo star delta tracker.

Proof-of-concept for github-traffic-tracker #69 (cross-repo engagement radar).
Collects stargazer data across all user + org repos via GitHub GraphQL API,
shows who starred what and when, with daily/weekly aggregation.

Usage:
    python tests/one-offs/star_radar_poc.py                  # Last 7 days (default)
    python tests/one-offs/star_radar_poc.py --days 30        # Last 30 days
    python tests/one-offs/star_radar_poc.py --date 2026-03-18  # Specific day
    python tests/one-offs/star_radar_poc.py --all             # All time, grouped by day
    python tests/one-offs/star_radar_poc.py --snapshot        # Save snapshot to JSON
    python tests/one-offs/star_radar_poc.py --compare         # Compare with last snapshot

Requires: gh CLI authenticated (gh auth login)
"""

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# GraphQL via gh CLI
# ---------------------------------------------------------------------------

def gh_graphql(query, variables=None):
    """Run a GraphQL query via gh CLI. Returns parsed JSON."""
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    if variables:
        for k, v in variables.items():
            cmd.extend(["-f", f"{k}={v}"])
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"ERROR: gh api graphql failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

REPO_FIELDS = """
    nameWithOwner
    stargazerCount
    forkCount
    isArchived
    isFork
    url
    issues(states: OPEN) { totalCount }
    pullRequests(states: OPEN) { totalCount }
"""

# Stargazer query with timestamps -- paginated per repo
STARGAZER_QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    stargazers(first: 100, orderBy: {field: STARRED_AT, direction: DESC}, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      edges {
        starredAt
        node { login }
      }
    }
  }
}
"""


def fetch_all_repos():
    """Fetch all repos (personal + org) with summary stats."""
    # Personal repos
    repos = []
    cursor = None
    while True:
        after = f', after: "{cursor}"' if cursor else ""
        query = f"""{{
          viewer {{
            repositories(first: 100, ownerAffiliations: [OWNER]{after},
                         orderBy: {{field: STARGAZERS, direction: DESC}}) {{
              pageInfo {{ hasNextPage endCursor }}
              nodes {{ {REPO_FIELDS} }}
            }}
          }}
        }}"""
        data = gh_graphql(query)
        page = data["data"]["viewer"]["repositories"]
        repos.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    # Org repos
    org_data = gh_graphql("""{
      viewer {
        organizations(first: 50) {
          nodes { login }
        }
      }
    }""")
    orgs = [o["login"] for o in org_data["data"]["viewer"]["organizations"]["nodes"]]

    for org in orgs:
        cursor = None
        while True:
            after = f', after: "{cursor}"' if cursor else ""
            query = f"""{{
              organization(login: "{org}") {{
                repositories(first: 100{after},
                             orderBy: {{field: STARGAZERS, direction: DESC}}) {{
                  pageInfo {{ hasNextPage endCursor }}
                  nodes {{ {REPO_FIELDS} }}
                }}
              }}
            }}"""
            data = gh_graphql(query)
            page = data["data"]["organization"]["repositories"]
            repos.extend(page["nodes"])
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]

    return repos


def fetch_recent_stargazers(owner, name, since_date=None, max_pages=10):
    """Fetch stargazer history for a repo. Stops when hitting stars older than since_date."""
    stars = []
    cursor = None
    for _ in range(max_pages):
        variables = {"owner": owner, "name": name}
        if cursor:
            variables["cursor"] = cursor
        data = gh_graphql(STARGAZER_QUERY, variables)
        repo_data = data["data"]["repository"]
        if not repo_data:
            break
        page = repo_data["stargazers"]
        for edge in page["edges"]:
            starred_at = edge["starredAt"]
            star_date = datetime.fromisoformat(starred_at.replace("Z", "+00:00"))
            if since_date and star_date < since_date:
                return stars  # We've gone past our window
            stars.append({
                "user": edge["node"]["login"],
                "starredAt": starred_at,
                "date": starred_at[:10],
            })
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return stars


# ---------------------------------------------------------------------------
# Snapshot storage
# ---------------------------------------------------------------------------

SNAPSHOT_DIR = Path.home() / ".ghtraf" / "portfolio" / "snapshots"


def save_snapshot(repos):
    """Save current repo stats as a dated snapshot."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    snapshot = {
        "collectedAt": datetime.now(timezone.utc).isoformat(),
        "version": 1,
        "repos": {}
    }
    for repo in repos:
        snapshot["repos"][repo["nameWithOwner"]] = {
            "stars": repo["stargazerCount"],
            "forks": repo["forkCount"],
            "openIssues": repo["issues"]["totalCount"],
            "openPRs": repo["pullRequests"]["totalCount"],
            "isArchived": repo["isArchived"],
            "isFork": repo["isFork"],
        }
    path = SNAPSHOT_DIR / f"{today}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    return path


def load_snapshot(date_str=None):
    """Load a snapshot by date. If date_str is None, load the most recent."""
    if not SNAPSHOT_DIR.exists():
        return None
    files = sorted(SNAPSHOT_DIR.glob("*.json"))
    if not files:
        return None
    if date_str:
        target = SNAPSHOT_DIR / f"{date_str}.json"
        if target.exists():
            with open(target, encoding="utf-8") as f:
                return json.load(f)
        return None
    # Most recent
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def compare_snapshots(current_repos, previous_snapshot):
    """Compare current data against a previous snapshot. Returns deltas."""
    prev = previous_snapshot.get("repos", {})
    deltas = []
    for repo in current_repos:
        name = repo["nameWithOwner"]
        if name not in prev:
            continue
        star_delta = repo["stargazerCount"] - prev[name].get("stars", 0)
        fork_delta = repo["forkCount"] - prev[name].get("forks", 0)
        issue_delta = repo["issues"]["totalCount"] - prev[name].get("openIssues", 0)
        if star_delta != 0 or fork_delta != 0 or issue_delta != 0:
            deltas.append({
                "repo": name,
                "url": repo["url"],
                "starDelta": star_delta,
                "starsCurrent": repo["stargazerCount"],
                "forkDelta": fork_delta,
                "forksCurrent": repo["forkCount"],
                "issueDelta": issue_delta,
                "issuesCurrent": repo["issues"]["totalCount"],
            })
    # Sort by star delta descending
    deltas.sort(key=lambda d: d["starDelta"], reverse=True)
    return deltas


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def star_page_url(repo_name):
    """Generate URL to a repo's stargazers page."""
    return f"https://github.com/{repo_name}/stargazers"


def format_delta(n):
    """Format a number with +/- sign."""
    if n > 0:
        return f"+{n}"
    return str(n)


def print_star_events(repos, stars_by_repo, days, specific_date=None):
    """Print star events grouped by day."""
    # Group all stars by date
    by_date = defaultdict(list)
    for repo_name, stars in stars_by_repo.items():
        for star in stars:
            by_date[star["date"]].append({
                "repo": repo_name,
                "user": star["user"],
            })

    if specific_date:
        dates = [specific_date]
    else:
        dates = sorted(by_date.keys(), reverse=True)

    if not dates or not any(by_date.get(d) for d in dates):
        print("\n  No star events found in the specified period.")
        return

    for date in dates:
        events = by_date.get(date, [])
        if not events:
            if specific_date:
                print(f"\n  No stars on {date}")
            continue

        # Group by repo
        repo_events = defaultdict(list)
        for e in events:
            repo_events[e["repo"]].append(e["user"])

        print(f"\n  {date}  ({len(events)} star{'s' if len(events) != 1 else ''})")
        print(f"  {'=' * 50}")
        for repo, users in sorted(repo_events.items(), key=lambda x: -len(x[1])):
            user_list = ", ".join(users[:5])
            if len(users) > 5:
                user_list += f" (+{len(users) - 5} more)"
            print(f"    +{len(users)}  {repo}")
            print(f"         by: {user_list}")
            print(f"         {star_page_url(repo)}")


def print_summary_table(repos):
    """Print a summary of all repos sorted by stars."""
    # Filter to repos with at least 1 star
    starred = [r for r in repos if r["stargazerCount"] > 0]
    starred.sort(key=lambda r: r["stargazerCount"], reverse=True)

    if not starred:
        print("\n  No repos with stars found.")
        return

    print(f"\n  {'Repo':<50} {'Stars':>6} {'Forks':>6} {'Issues':>7} {'PRs':>5}")
    print(f"  {'-'*50} {'-'*6} {'-'*6} {'-'*7} {'-'*5}")
    for repo in starred:
        name = repo["nameWithOwner"]
        if len(name) > 49:
            name = name[:46] + "..."
        print(f"  {name:<50} {repo['stargazerCount']:>6} "
              f"{repo['forkCount']:>6} "
              f"{repo['issues']['totalCount']:>7} "
              f"{repo['pullRequests']['totalCount']:>5}")

    total_stars = sum(r["stargazerCount"] for r in repos)
    total_forks = sum(r["forkCount"] for r in repos)
    print(f"\n  Total: {len(repos)} repos, {total_stars} stars, {total_forks} forks")


def print_snapshot_comparison(deltas, prev_date):
    """Print comparison between current state and a previous snapshot."""
    if not deltas:
        print(f"\n  No changes since {prev_date}.")
        return

    print(f"\n  Changes since {prev_date}:")
    print(f"  {'=' * 60}")
    for d in deltas:
        parts = []
        if d["starDelta"] != 0:
            parts.append(f"stars: {format_delta(d['starDelta'])} ({d['starsCurrent']})")
        if d["forkDelta"] != 0:
            parts.append(f"forks: {format_delta(d['forkDelta'])} ({d['forksCurrent']})")
        if d["issueDelta"] != 0:
            parts.append(f"issues: {format_delta(d['issueDelta'])} ({d['issuesCurrent']})")
        print(f"    {d['repo']}")
        print(f"      {', '.join(parts)}")
        print(f"      {d['url']}/stargazers")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="star_radar_poc",
        description="Star Radar POC -- see which repos are getting attention",
    )
    parser.add_argument("--days", type=int, default=7,
                        help="Number of days to look back (default: 7)")
    parser.add_argument("--date", type=str, default=None,
                        help="Show stars for a specific date (YYYY-MM-DD)")
    parser.add_argument("--all", action="store_true",
                        help="Show all star events (no date limit)")
    parser.add_argument("--snapshot", action="store_true",
                        help="Save current stats as a dated snapshot")
    parser.add_argument("--compare", type=str, nargs="?", const="latest",
                        help="Compare with a previous snapshot (date or 'latest')")
    parser.add_argument("--summary", action="store_true",
                        help="Show summary table of all repos")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON instead of formatted text")
    args = parser.parse_args()

    print("Star Radar POC -- github-traffic-tracker #69")
    print("Fetching repos across all orgs...")

    repos = fetch_all_repos()
    print(f"Found {len(repos)} repos across personal + org accounts.")

    # Snapshot mode
    if args.snapshot:
        path = save_snapshot(repos)
        print(f"Snapshot saved: {path}")

    # Compare mode
    if args.compare:
        date_str = None if args.compare == "latest" else args.compare
        prev = load_snapshot(date_str)
        if not prev:
            print("No previous snapshot found. Run with --snapshot first.")
        else:
            prev_date = prev.get("collectedAt", "unknown")[:10]
            deltas = compare_snapshots(repos, prev)
            if args.json:
                print(json.dumps(deltas, indent=2))
            else:
                print_snapshot_comparison(deltas, prev_date)
        if not args.summary and not args.date and not args.all:
            return

    # Summary table
    if args.summary:
        print_summary_table(repos)

    # Star events (the main feature)
    if args.all:
        since = None
        days_label = "all time"
    elif args.date:
        since = datetime.fromisoformat(args.date + "T00:00:00+00:00")
        days_label = args.date
    else:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)
        days_label = f"last {args.days} days"

    # Only fetch stargazer details for repos that have stars
    starred_repos = [r for r in repos if r["stargazerCount"] > 0]
    print(f"\nFetching stargazer history for {len(starred_repos)} starred repos ({days_label})...")

    stars_by_repo = {}
    for i, repo in enumerate(starred_repos):
        name = repo["nameWithOwner"]
        owner, rname = name.split("/", 1)
        sys.stdout.write(f"\r  [{i+1}/{len(starred_repos)}] {name}...")
        sys.stdout.flush()
        stars = fetch_recent_stargazers(owner, rname, since_date=since)
        if stars:
            stars_by_repo[name] = stars
    print(f"\r  Done. {sum(len(s) for s in stars_by_repo.values())} star events found." + " " * 40)

    if args.json:
        output = {}
        for repo_name, stars in stars_by_repo.items():
            output[repo_name] = stars
        print(json.dumps(output, indent=2))
    else:
        print_star_events(repos, stars_by_repo, args.days, specific_date=args.date)

    # Always show summary if we didn't already
    if not args.summary and not args.compare:
        print_summary_table(repos)


if __name__ == "__main__":
    main()
