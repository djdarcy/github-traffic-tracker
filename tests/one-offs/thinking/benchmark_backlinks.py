"""Benchmark generate-backlinks.py (DIY regex) vs obsidiantools.

Run from repo root:
    python tests/one-offs/thinking/benchmark_backlinks.py

Compares speed and link counts between our zero-dep tool and the
obsidiantools library. Useful as a periodic spot-check to ensure
our tool stays accurate as the vault grows.
"""

import time
import subprocess
import sys
from pathlib import Path

VAULT_PATH = Path("private/claude")
RUNS = 3


def benchmark_diy(vault_path: Path, runs: int = RUNS):
    """Benchmark our generate-backlinks.py script."""
    times = []
    last_output = ""
    for _ in range(runs):
        start = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "scripts/generate-backlinks.py", "--stats"],
            capture_output=True, text=True, cwd=vault_path.parent if vault_path.is_absolute() else None
        )
        times.append(time.perf_counter() - start)
        last_output = result.stdout.strip() or result.stderr.strip()

    avg = sum(times) / len(times)
    return avg, times, last_output


def benchmark_obsidiantools(vault_path: Path, runs: int = RUNS):
    """Benchmark obsidiantools library."""
    try:
        from obsidiantools.api import Vault
    except ImportError:
        return None, [], "obsidiantools not installed (pip install obsidiantools)"

    times = []
    vault = None
    for _ in range(runs):
        start = time.perf_counter()
        vault = Vault(vault_path).connect()
        times.append(time.perf_counter() - start)

    avg = sum(times) / len(times)

    forward_count = sum(len(v) for v in vault.wikilinks_index.values())
    backlink_count = sum(len(v) for v in vault.backlinks_index.values())
    file_count = len(vault.md_file_index)
    isolated = len(vault.isolated_notes) if hasattr(vault, "isolated_notes") else "N/A"

    stats = {
        "files": file_count,
        "forward_links": forward_count,
        "backlink_edges": backlink_count,
        "isolated": isolated,
    }
    return avg, times, stats


def main():
    print(f"Vault: {VAULT_PATH.resolve()}")
    print(f"Runs per tool: {RUNS}")
    print()

    # DIY
    diy_avg, diy_times, diy_output = benchmark_diy(VAULT_PATH)
    print("=== DIY Regex (generate-backlinks.py) ===")
    print(f"Avg time: {diy_avg:.3f}s  (runs: {', '.join(f'{t:.3f}' for t in diy_times)})")
    for line in diy_output.split("\n"):
        line = line.strip()
        if any(k in line for k in ["Total .md", "Forward", "backlink", "Backlink", "Isolated", "Broken"]):
            print(f"  {line}")
    print()

    # obsidiantools
    ot_avg, ot_times, ot_stats = benchmark_obsidiantools(VAULT_PATH)
    print("=== obsidiantools ===")
    if ot_avg is None:
        print(f"  {ot_stats}")
    else:
        print(f"Avg time: {ot_avg:.3f}s  (runs: {', '.join(f'{t:.3f}' for t in ot_times)})")
        for k, v in ot_stats.items():
            print(f"  {k}: {v}")
    print()

    # Comparison
    print("=== Head-to-Head ===")
    if ot_avg is not None:
        ratio = ot_avg / diy_avg if diy_avg > 0 else float("inf")
        print(f"Speed: DIY {diy_avg:.3f}s vs OT {ot_avg:.3f}s  (OT is {ratio:.0f}x slower)")

        # Link count comparison
        if isinstance(ot_stats, dict):
            print(f"Files:    DIY scans vault dir | OT found {ot_stats['files']}")
            print(f"Forward:  check DIY stats above | OT found {ot_stats['forward_links']}")
            print(f"Backlink: check DIY stats above | OT found {ot_stats['backlink_edges']}")
            print()
            print("Differences in link counts are expected:")
            print("  - DIY catches YAML frontmatter wikilinks; OT does not")
            print("  - DIY filters code blocks and inline backticks; OT may not")
            print("  - OT may resolve aliases differently")
    else:
        print("obsidiantools not available for comparison")

    print()
    print("For detailed cross-validation:")
    print("  python scripts/generate-backlinks.py --validate")


if __name__ == "__main__":
    main()
