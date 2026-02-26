#!/usr/bin/env python3
"""Explore the schema of a Claude Code JSONL session transcript.

This captures the exact exploratory steps used when investigating the
federated-purring-kay session to understand the JSONL structure before
writing any recovery logic.

== Why This Exists ==

The Claude Code JSONL format is not documented. When you first open one of
these files, every line is a very long JSON object and you can't tell what
structure to expect. The initial investigation used a series of iterative
bash one-liners (sed + python3 -c) to progressively reveal the schema.

This script consolidates those one-liners into a single reusable tool.

== What We Discovered During The Original Investigation ==

Run order and what each step revealed:

  Step 1 (--line-count):
    The file has ~18,800 lines. Lines are very long (each is one JSON object).
    Confirmed: wc -l gives a quick size check without parsing.

  Step 2 (--sample N):
    Printed raw first 800 chars of several lines. Revealed top-level keys:
      parentUuid, isSidechain, userType, cwd, sessionId, version, gitBranch,
      slug, type, message, uuid, timestamp
    Key finding: "type" field (not "role") is the primary discriminator.
    Values seen: "assistant", "user", "progress", "custom-title", "system"

  Step 3 (--message-types):
    Counted all distinct values of obj["type"]. Showed:
      assistant (model responses, tool USE calls)
      user      (human messages AND tool RESULTS -- same type!)
      progress  (hook events between tool call and result)
      system    (context injections)
      custom-title (session title updates)
    Key finding: "user" type covers both actual user messages AND tool results.
    The discriminator between them is the presence of "toolUseResult" key.

  Step 4 (--sample-by-type user):
    Sampled user-type messages. Discovered:
      - Some have obj["content"] = [] (empty!)
      - Tool results are in obj["message"]["content"][0]["content"]
      - Presence of "toolUseResult" key signals a tool result (not user input)
    Key finding: obj["content"] (top-level) is empty for tool result messages.
    The actual content is nested under obj["message"]["content"].

  Step 5 (--sample-by-type assistant):
    Sampled assistant-type messages. Discovered:
      - Tool USE calls (Write, Read, Edit, Bash) are in obj["message"]["content"]
      - obj["content"] (top-level) is also empty for these
      - Structure: [{"type": "tool_use", "name": "Write", "input": {...}}]
    Key finding: Both tool USE and tool RESULT live in obj["message"]["content"],
    not obj["content"]. search_session_log.py searches obj["content"] which is
    why it couldn't find these.

  Step 6 (--keys-at-line N):
    Used on specific lines found via grep to see all keys for that exact object.
    Confirmed "toolUseResult" presence/absence as discriminator.
    Revealed: toolUseResult contains abbreviated version of the result
    (not the full content), while the full content is in message.content.

== The Grep Step (not in this script) ==

Before any of this, the actual first step was using the Grep tool from Claude Code:
  - Pattern: "Stats Infrastructure Migration"
  - Pattern: ".claude/plans/"
  These returned line numbers even though each line was too long to display
  (shown as "[Omitted long matching line]"). That's enough to know WHERE to look.

== Usage ==

    python inspect_jsonl_schema.py <jsonl_path> [options]

    --line-count              Show total line count and file size
    --sample N                Print raw first 800 chars of line N
    --sample-by-type TYPE     Print 3 sample objects of given type
    --message-types           Count all distinct obj["type"] values
    --keys-at-line N          Print all top-level keys for line N
    --content-paths N         Walk all paths in the JSON at line N (depth-limited)
    --tool-names              Count all distinct tool names used in the session
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def load_lines(filepath):
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {filepath}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.readlines()


def cmd_line_count(lines, filepath):
    path = Path(filepath)
    size_mb = path.stat().st_size / 1024 / 1024
    nonempty = sum(1 for l in lines if l.strip())
    print(f"File: {filepath}")
    print(f"Size: {size_mb:.1f} MB")
    print(f"Lines: {len(lines)} total, {nonempty} non-empty")


def cmd_sample(lines, line_num, char_limit=800):
    """Print raw first N chars of a specific line number (1-indexed)."""
    idx = line_num - 1
    if idx < 0 or idx >= len(lines):
        print(f"Line {line_num} out of range (file has {len(lines)} lines)", file=sys.stderr)
        return
    raw = lines[idx].strip()
    print(f"=== Line {line_num} (raw, first {char_limit} chars) ===")
    sys.stdout.buffer.write(raw[:char_limit].encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")
    print(f"\n(total length: {len(raw)} chars)")


def cmd_message_types(lines):
    """Count all distinct values of obj['type'] across the whole file."""
    counts = Counter()
    errors = 0
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
            t = obj.get("type", "<missing>")
            counts[t] += 1
        except json.JSONDecodeError:
            errors += 1

    print("Message type distribution:")
    for t, count in counts.most_common():
        print(f"  {t:<20s} {count:>6d}")
    if errors:
        print(f"  (parse errors: {errors})")


def cmd_sample_by_type(lines, target_type, n=3):
    """Print N sample objects of a given type, showing structure."""
    found = 0
    for linenum, raw in enumerate(lines, 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != target_type:
            continue

        found += 1
        print(f"\n{'='*70}")
        print(f"Sample {found} of type={target_type!r} at line {linenum}")
        print(f"{'='*70}")

        # Print top-level keys and their value summaries
        print("Top-level keys:")
        for k, v in obj.items():
            if k in ("message", "content", "data"):
                # Show structure recursively one level
                if isinstance(v, dict):
                    print(f"  {k}: {{dict, keys: {list(v.keys())}}}")
                    # Show message.content structure if present
                    if k == "message" and "content" in v:
                        mc = v["content"]
                        if isinstance(mc, list):
                            print(f"    .content: [list of {len(mc)} items]")
                            for i, item in enumerate(mc[:3]):
                                if isinstance(item, dict):
                                    item_type = item.get("type", "?")
                                    item_name = item.get("name", "")
                                    item_keys = list(item.keys())
                                    summary = f"type={item_type!r}"
                                    if item_name:
                                        summary += f", name={item_name!r}"
                                    if item_type == "tool_result":
                                        result_content = item.get("content", "")
                                        if isinstance(result_content, str):
                                            summary += f", content[:{min(80,len(result_content))}]={result_content[:80]!r}"
                                    summary += f", keys={item_keys}"
                                    print(f"      [{i}]: {summary}")
                        elif isinstance(mc, str):
                            print(f"    .content: {mc[:100]!r}")
                elif isinstance(v, list):
                    print(f"  {k}: [list of {len(v)} items]")
            elif k == "toolUseResult":
                print(f"  {k}: PRESENT (keys: {list(v.keys()) if isinstance(v, dict) else type(v).__name__})")
            else:
                val_repr = repr(v)
                if len(val_repr) > 80:
                    val_repr = val_repr[:80] + "..."
                print(f"  {k}: {val_repr}")

        if found >= n:
            break

    if found == 0:
        print(f"No messages of type={target_type!r} found.")


def cmd_keys_at_line(lines, line_num):
    """Print all top-level keys for a specific line."""
    idx = line_num - 1
    if idx < 0 or idx >= len(lines):
        print(f"Line {line_num} out of range", file=sys.stderr)
        return
    raw = lines[idx].strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON parse error at line {line_num}: {e}", file=sys.stderr)
        return

    print(f"=== Line {line_num}: top-level keys ===")
    for k, v in obj.items():
        val_type = type(v).__name__
        if isinstance(v, (str, int, float, bool)) or v is None:
            val_repr = repr(v)
            if len(val_repr) > 100:
                val_repr = val_repr[:100] + "..."
            print(f"  {k} ({val_type}): {val_repr}")
        elif isinstance(v, dict):
            print(f"  {k} (dict, {len(v)} keys): {list(v.keys())}")
        elif isinstance(v, list):
            print(f"  {k} (list, {len(v)} items)")
        else:
            print(f"  {k} ({val_type})")


def walk_paths(obj, prefix="", depth=0, max_depth=4, output=None):
    """Recursively walk all JSON paths, showing value summaries."""
    if output is None:
        output = []
    if depth > max_depth:
        output.append(f"{prefix}: <max depth>")
        return output

    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            walk_paths(v, path, depth + 1, max_depth, output)
    elif isinstance(obj, list):
        if len(obj) == 0:
            output.append(f"{prefix}: []")
        else:
            for i, item in enumerate(obj[:3]):  # show first 3 items
                walk_paths(item, f"{prefix}[{i}]", depth + 1, max_depth, output)
            if len(obj) > 3:
                output.append(f"{prefix}[...{len(obj)-3} more items]")
    else:
        val = repr(obj)
        if len(val) > 120:
            val = val[:120] + f"... ({len(str(obj))} chars)"
        output.append(f"{prefix}: {val}")

    return output


def cmd_content_paths(lines, line_num, max_depth=4):
    """Walk all JSON paths in a line's object, depth-limited."""
    idx = line_num - 1
    if idx < 0 or idx >= len(lines):
        print(f"Line {line_num} out of range", file=sys.stderr)
        return
    raw = lines[idx].strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON parse error at line {line_num}: {e}", file=sys.stderr)
        return

    print(f"=== Line {line_num}: all paths (max depth {max_depth}) ===")
    paths = walk_paths(obj, max_depth=max_depth)
    for p in paths:
        sys.stdout.buffer.write((p + "\n").encode("utf-8", errors="replace"))


def cmd_tool_names(lines):
    """Count all distinct tool names used as tool_use calls."""
    counts = Counter()
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        if '"tool_use"' not in raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        # Tool calls are in obj["message"]["content"]
        msg = obj.get("message", {})
        if not isinstance(msg, dict):
            continue
        for block in msg.get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                counts[block.get("name", "<unknown>")] += 1

    if not counts:
        print("No tool_use calls found.")
        return
    print("Tool usage counts:")
    for name, count in counts.most_common():
        print(f"  {name:<20s} {count:>5d}")


def main():
    parser = argparse.ArgumentParser(
        description="Explore the schema of a Claude Code JSONL session transcript",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("jsonl_path", help="Path to the JSONL transcript file")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--line-count", action="store_true",
        help="Show file size and line count"
    )
    group.add_argument(
        "--sample", type=int, metavar="N",
        help="Print raw first 800 chars of line N (1-indexed)"
    )
    group.add_argument(
        "--message-types", action="store_true",
        help="Count distinct obj['type'] values across whole file"
    )
    group.add_argument(
        "--sample-by-type", metavar="TYPE",
        help="Print 3 sample objects of given type (assistant, user, progress, etc.)"
    )
    group.add_argument(
        "--keys-at-line", type=int, metavar="N",
        help="Print all top-level keys for line N"
    )
    group.add_argument(
        "--content-paths", type=int, metavar="N",
        help="Walk all JSON paths in line N (depth-limited to 4)"
    )
    group.add_argument(
        "--tool-names", action="store_true",
        help="Count all distinct tool names used in the session"
    )

    parser.add_argument(
        "--count", type=int, default=3,
        help="Number of samples for --sample-by-type (default: 3)"
    )
    parser.add_argument(
        "--depth", type=int, default=4,
        help="Max depth for --content-paths (default: 4)"
    )

    args = parser.parse_args()

    # --line-count doesn't need to parse every line
    if args.line_count:
        path = Path(args.jsonl_path)
        if not path.exists():
            print(f"File not found: {args.jsonl_path}", file=sys.stderr)
            sys.exit(1)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        cmd_line_count(lines, args.jsonl_path)
        return

    print(f"Loading {args.jsonl_path} ...", file=sys.stderr)
    lines = load_lines(args.jsonl_path)
    print(f"  {len(lines)} lines loaded.\n", file=sys.stderr)

    if args.sample is not None:
        cmd_sample(lines, args.sample)
    elif args.message_types:
        cmd_message_types(lines)
    elif args.sample_by_type:
        cmd_sample_by_type(lines, args.sample_by_type, n=args.count)
    elif args.keys_at_line is not None:
        cmd_keys_at_line(lines, args.keys_at_line)
    elif args.content_paths is not None:
        cmd_content_paths(lines, args.content_paths, max_depth=args.depth)
    elif args.tool_names:
        cmd_tool_names(lines)


if __name__ == "__main__":
    main()
