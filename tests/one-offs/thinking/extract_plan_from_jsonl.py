#!/usr/bin/env python3
"""Recover overwritten plan file content from a Claude Code JSONL session transcript.

This is the ACTUAL script derived from the session where we recovered the
"Stats Infrastructure Migration & Standalone Extraction" plan that had been
overwritten by the "Setup Script + Templatization + Dog-Fooding" plan.

== The Problem ==

Claude Code keeps plans in ~/.claude/plans/<slug>.md (e.g. federated-purring-kay.md).
When a new plan is approved in plan mode, it OVERWRITES the file. The prior plan
content is gone from disk, but the JSONL transcript captures every Write/Edit tool
call and every Read tool call result -- including the file content as the model
read it just before overwriting.

== Key Discovery: Two Different JSON Structures ==

This was the main surprise during investigation. The JSONL has TWO structures for
what looks like the same kind of message:

1. assistant-type messages (tool USE, not result):
   obj["message"]["content"] = [{"type": "tool_use", "name": "Write", "input": {...}}]
   ^ This is where Write/Edit inputs live (new_string, old_string, content)

2. user-type messages (tool RESULT):
   obj["message"]["content"] = [{"type": "tool_result", "content": "<file text>"}]
   obj["toolUseResult"] = {...}    <-- also here, abbreviated
   ^ This is where Read results live (what the file contained)

The search_session_log.py in this folder searches obj["content"] (top-level),
which works for assistant messages. But tool RESULTS are in obj["message"]["content"]
-- a different path. That's why a second, targeted script was needed.

== What Actually Worked ==

Step 1: grep for the plan name to confirm it's in the file at all.
Step 2: Search for Write tool calls targeting .claude/plans/ to map the full
        history of plan overwrites and find line numbers.
Step 3: For each Write/Edit, identify the subsequent Read of the same file.
Step 4: Find the user-type message immediately after that Read -- it contains
        the tool result in obj["message"]["content"][0]["content"].
Step 5: Print the content. That's the plan as it existed before being overwritten.

== Usage ==

    python extract_plan_from_jsonl.py <jsonl_path> [--plan-slug <name>] [--line <N>]

Examples:
    # Show full history of plan overwrites for federated-purring-kay
    python extract_plan_from_jsonl.py transcript.jsonl

    # Recover the plan content that was read at a specific line
    python extract_plan_from_jsonl.py transcript.jsonl --line 18207

    # Filter to a specific plan file slug
    python extract_plan_from_jsonl.py transcript.jsonl --plan-slug federated-purring-kay
"""

import argparse
import json
import sys
from pathlib import Path


PLANS_PATH_FRAGMENT = ".claude/plans/"  # matches both forward and backslash


def normalize_path(p):
    """Normalize slashes so .claude/plans/ matches Windows paths too."""
    return p.replace("\\", "/")


def is_plan_file(path_str):
    return PLANS_PATH_FRAGMENT in normalize_path(path_str)


def extract_tool_calls_to_plans(lines, plan_slug=None):
    """
    Pass 1: Find all Write, Edit, and Read tool calls targeting plan files.
    Returns list of (line_num, tool_name, file_path, content_summary).
    """
    results = []

    for linenum, raw in enumerate(lines, 1):
        raw = raw.strip()
        if not raw:
            continue
        # Quick pre-filter: skip lines that don't mention plans at all
        if "plans" not in raw and "Plans" not in raw:
            continue

        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue

        # Tool USE calls are in obj["message"]["content"] for assistant-type messages
        # (NOT obj["content"] -- that path is empty or absent for these)
        msg = obj.get("message", {})
        if not isinstance(msg, dict):
            continue
        msg_content = msg.get("content", [])
        if not isinstance(msg_content, list):
            continue

        for block in msg_content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue

            tool_name = block.get("name", "")
            inp = block.get("input", {})
            file_path = inp.get("file_path", inp.get("path", ""))

            if not is_plan_file(file_path):
                continue
            if plan_slug and plan_slug not in file_path:
                continue

            # Summarize what changed
            if tool_name == "Write":
                content_preview = inp.get("content", "")[:120].replace("\n", " ")
                summary = f'Write -> "{content_preview}..."'
            elif tool_name == "Edit":
                old = inp.get("old_string", "")[:60].replace("\n", " ")
                new = inp.get("new_string", "")[:60].replace("\n", " ")
                summary = f'Edit: "{old}..." -> "{new}..."'
            elif tool_name == "Read":
                summary = "Read (result in next user-type message)"
            else:
                summary = f"{tool_name}"

            results.append({
                "line": linenum,
                "tool": tool_name,
                "file": file_path,
                "summary": summary,
                "input": inp,  # full input for Write/Edit recovery
            })

    return results


def find_tool_result_for_read(lines, read_line_num):
    """
    Given a line number where a Read tool_use occurred, find the subsequent
    user-type message that contains the tool result (file contents).

    The result is in: obj["message"]["content"][0]["content"]
    -- NOT in obj["content"] which is empty for these messages.

    Looks at up to 20 lines after the Read to find the user message.
    Returns the file content string, or None.
    """
    # The Read tool call is at read_line_num (1-indexed).
    # The tool result arrives in a user-type message a few lines later
    # (typically 2-5 lines: progress events sit between them).
    search_start = read_line_num  # 0-indexed start
    search_end = min(read_line_num + 20, len(lines))

    for i in range(search_start, search_end):
        raw = lines[i].strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if obj.get("type") != "user":
            continue

        # Check for toolUseResult key -- quick indicator this is a tool result message
        if "toolUseResult" not in obj:
            continue

        msg = obj.get("message", {})
        msg_content = msg.get("content", [])
        if not isinstance(msg_content, list) or not msg_content:
            continue

        block = msg_content[0]
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_result":
            continue

        content = block.get("content", "")
        if isinstance(content, str) and len(content) > 10:
            return content, i + 1  # return (content, actual_line_num)

    return None, None


def recover_plan_at_line(lines, target_line):
    """
    Given a specific line number where a Read of a plan file happened,
    recover the file content that was returned to the model.
    """
    content, result_line = find_tool_result_for_read(lines, target_line)
    if content:
        # Strip the line-number prefix Claude Code adds (format: "     1->text")
        cleaned = strip_line_numbers(content)
        return cleaned, result_line
    return None, None


def strip_line_numbers(text):
    """
    Claude Code's Read tool returns content with line number prefixes:
        "     1->actual content here\n     2->next line\n"
    Strip these to recover the raw file text.
    """
    lines_out = []
    for line in text.split("\n"):
        # Pattern: leading spaces, digits, then "→" or "->" or "→"
        # The actual character used is the Unicode right arrow U+2192
        if "→" in line:
            arrow_pos = line.index("→")
            lines_out.append(line[arrow_pos + 1:])
        elif "->" in line[:10]:  # only strip near the start
            arrow_pos = line.index("->")
            lines_out.append(line[arrow_pos + 2:])
        else:
            lines_out.append(line)
    return "\n".join(lines_out)


def main():
    parser = argparse.ArgumentParser(
        description="Recover overwritten plan content from Claude Code JSONL session logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("jsonl_path", help="Path to the JSONL transcript file")
    parser.add_argument(
        "--plan-slug",
        default=None,
        help="Filter to a specific plan file slug (e.g. 'federated-purring-kay')",
    )
    parser.add_argument(
        "--line",
        type=int,
        default=None,
        help="Recover content from a Read at this specific line number",
    )
    parser.add_argument(
        "--all-writes",
        action="store_true",
        help="Show full Write/Edit content for every plan file change",
    )
    args = parser.parse_args()

    jsonl_path = Path(args.jsonl_path)
    if not jsonl_path.exists():
        # Try resolving the symlink path that Claude Code's sesslog uses
        print(f"File not found: {jsonl_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {jsonl_path} ...", file=sys.stderr)
    with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    print(f"  {len(lines)} lines loaded.\n", file=sys.stderr)

    # If --line was given, just recover that specific Read result
    if args.line:
        content, result_line = recover_plan_at_line(lines, args.line)
        if content:
            print(f"=== Plan content from Read at line {args.line} (result at line {result_line}) ===\n")
            print(content)
        else:
            print(f"No tool result found near line {args.line}.", file=sys.stderr)
            print("Tip: Make sure --line points to an assistant-type Read tool call.", file=sys.stderr)
        return

    # Pass 1: Map all plan file operations
    print("Pass 1: Scanning for all plan file operations...\n")
    tool_calls = extract_tool_calls_to_plans(lines, plan_slug=args.plan_slug)

    if not tool_calls:
        print("No plan file operations found.")
        if args.plan_slug:
            print(f"  (searched for slug: {args.plan_slug})")
        return

    print(f"Found {len(tool_calls)} plan file operation(s):\n")
    for tc in tool_calls:
        print(f"  Line {tc['line']:5d}  {tc['tool']:6s}  {tc['file']}")
        if args.all_writes and tc["tool"] in ("Write", "Edit"):
            print(f"            {tc['summary']}")
    print()

    # Pass 2: For each Read, recover the file content
    read_calls = [tc for tc in tool_calls if tc["tool"] == "Read"]
    if not read_calls:
        print("No Read operations found. Cannot recover plan content from reads.")
        print("\nTo recover from a Write/Edit, use --all-writes to see the written content.")
        if args.all_writes:
            for tc in tool_calls:
                if tc["tool"] == "Write":
                    print(f"\n{'='*70}")
                    print(f"Write at line {tc['line']}:")
                    print(f"{'='*70}")
                    content = tc["input"].get("content", "")
                    print(strip_line_numbers(content))
                elif tc["tool"] == "Edit":
                    print(f"\n{'='*70}")
                    print(f"Edit at line {tc['line']} — new_string:")
                    print(f"{'='*70}")
                    new_str = tc["input"].get("new_string", "")
                    print(strip_line_numbers(new_str))
        return

    print(f"Pass 2: Recovering content from {len(read_calls)} Read operation(s)...\n")
    for tc in read_calls:
        content, result_line = recover_plan_at_line(lines, tc["line"])
        print(f"{'='*70}")
        if content:
            print(f"Plan content read at line {tc['line']} (tool result at line {result_line}):")
            print(f"File: {tc['file']}")
            print(f"Content length: {len(content)} chars")
            print(f"{'='*70}\n")
            print(content)
        else:
            print(f"Read at line {tc['line']}: could not find tool result in next 20 lines.")
            print(f"File: {tc['file']}")
        print()

    # Also show Write/Edit content if --all-writes
    if args.all_writes:
        write_calls = [tc for tc in tool_calls if tc["tool"] in ("Write", "Edit")]
        if write_calls:
            print(f"\n{'='*70}")
            print("Write/Edit history (--all-writes):")
            print(f"{'='*70}\n")
            for tc in write_calls:
                print(f"--- {tc['tool']} at line {tc['line']} ---")
                if tc["tool"] == "Write":
                    content = tc["input"].get("content", "")
                    print(strip_line_numbers(content))
                elif tc["tool"] == "Edit":
                    new_str = tc["input"].get("new_string", "")
                    print(f"[new_string]:\n{strip_line_numbers(new_str)}")
                print()


if __name__ == "__main__":
    main()
