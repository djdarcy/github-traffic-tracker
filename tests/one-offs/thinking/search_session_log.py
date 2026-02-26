#!/usr/bin/env python3
"""Search Claude Code JSONL session logs for specific content.

Useful for recovering overwritten plans, finding previous tool outputs,
or locating specific conversations in the transcript history.

Usage:
    python search_session_log.py <jsonl_path> <search_term> [--context N] [--type TYPE]

Examples:
    # Find all mentions of a plan name
    python search_session_log.py transcript.jsonl "Stats Infrastructure Migration"

    # Find Write tool calls to plan files
    python search_session_log.py transcript.jsonl ".claude/plans/" --type write

    # Find with surrounding context (N lines before/after in the JSON value)
    python search_session_log.py transcript.jsonl "setup-gists" --context 5

    # Find all tool calls of a specific type
    python search_session_log.py transcript.jsonl "" --type edit

Notes:
    - JSONL files can be very large (100MB+). This script streams line-by-line.
    - Each line is a JSON object representing a conversation event.
    - Tool calls, tool results, and assistant messages are all searchable.
    - The --type flag filters by tool name (write, edit, read, bash, etc.)
"""

import argparse
import json
import sys
import os
from pathlib import Path


def search_jsonl(filepath, search_term, context_lines=0, tool_type=None, max_results=50):
    """Stream through JSONL file searching for matching content."""
    filepath = Path(filepath)
    if not filepath.exists():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    file_size = filepath.stat().st_size
    print(f"Searching {filepath.name} ({file_size / 1024 / 1024:.1f} MB)...")
    print(f"  Term: {search_term!r}" if search_term else "  Term: (any)")
    if tool_type:
        print(f"  Tool filter: {tool_type}")
    print()

    results = []
    line_num = 0

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line_num += 1
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Extract searchable text from the JSON object
            matches = find_matches_in_obj(obj, search_term, tool_type, line_num)
            results.extend(matches)

            if len(results) >= max_results:
                print(f"  (stopped at {max_results} results, use --max to increase)")
                break

    print(f"\nFound {len(results)} match(es) across {line_num} lines.\n")

    for i, match in enumerate(results, 1):
        print(f"{'='*80}")
        print(f"Result {i}/{len(results)} — Line {match['line']} — {match['source']}")
        print(f"{'='*80}")

        content = match["content"]
        if context_lines > 0 and search_term:
            content = extract_context(content, search_term, context_lines)

        # Truncate very long content
        if len(content) > 5000:
            content = content[:5000] + f"\n\n... [truncated, {len(match['content'])} chars total]"

        print(content)
        print()

    return results


def find_matches_in_obj(obj, search_term, tool_type, line_num):
    """Find all matching content within a JSON object."""
    matches = []

    # Stringify for search
    obj_str = json.dumps(obj, ensure_ascii=False)

    # Quick check: does this line even contain our search term?
    if search_term and search_term.lower() not in obj_str.lower():
        return matches

    # Check tool type filter
    if tool_type:
        tool_type_lower = tool_type.lower()
        # Look for tool_use content blocks
        if "content" in obj and isinstance(obj["content"], list):
            for block in obj["content"]:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    tool_name = block.get("name", "").lower()

                    if block_type == "tool_use" and (tool_type_lower in tool_name or tool_name == tool_type_lower):
                        input_data = block.get("input", {})
                        content_str = format_tool_call(block["name"], input_data)
                        if not search_term or search_term.lower() in content_str.lower():
                            matches.append({
                                "line": line_num,
                                "source": f"tool_use: {block['name']}",
                                "content": content_str,
                            })

                    elif block_type == "tool_result":
                        # Tool results contain the output
                        result_content = block.get("content", "")
                        if isinstance(result_content, list):
                            for rc in result_content:
                                if isinstance(rc, dict) and "text" in rc:
                                    result_content = rc["text"]
                                    break
                        if isinstance(result_content, str):
                            if not search_term or search_term.lower() in result_content.lower():
                                matches.append({
                                    "line": line_num,
                                    "source": f"tool_result (for {tool_type})",
                                    "content": result_content,
                                })
        return matches

    # No tool filter — search all content
    if "content" in obj and isinstance(obj["content"], list):
        for block in obj["content"]:
            if isinstance(block, dict):
                block_type = block.get("type", "")

                if block_type == "text":
                    text = block.get("text", "")
                    if search_term.lower() in text.lower():
                        role = obj.get("role", "unknown")
                        matches.append({
                            "line": line_num,
                            "source": f"{role} message (text)",
                            "content": text,
                        })

                elif block_type == "tool_use":
                    input_data = block.get("input", {})
                    content_str = format_tool_call(block.get("name", ""), input_data)
                    if search_term.lower() in content_str.lower():
                        matches.append({
                            "line": line_num,
                            "source": f"tool_use: {block.get('name', '')}",
                            "content": content_str,
                        })

                elif block_type == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        texts = []
                        for rc in result_content:
                            if isinstance(rc, dict) and "text" in rc:
                                texts.append(rc["text"])
                        result_content = "\n".join(texts)
                    if isinstance(result_content, str) and search_term.lower() in result_content.lower():
                        matches.append({
                            "line": line_num,
                            "source": "tool_result",
                            "content": result_content,
                        })

    elif "content" in obj and isinstance(obj["content"], str):
        if search_term.lower() in obj["content"].lower():
            role = obj.get("role", "unknown")
            matches.append({
                "line": line_num,
                "source": f"{role} message",
                "content": obj["content"],
            })

    return matches


def format_tool_call(name, input_data):
    """Format a tool call for display."""
    lines = [f"Tool: {name}"]
    if isinstance(input_data, dict):
        for key, value in input_data.items():
            val_str = str(value)
            if len(val_str) > 2000:
                val_str = val_str[:2000] + f"... [{len(str(value))} chars]"
            lines.append(f"  {key}: {val_str}")
    return "\n".join(lines)


def extract_context(content, search_term, n_lines):
    """Extract N lines of context around each match."""
    lines = content.split("\n")
    term_lower = search_term.lower()
    result_lines = set()

    for i, line in enumerate(lines):
        if term_lower in line.lower():
            start = max(0, i - n_lines)
            end = min(len(lines), i + n_lines + 1)
            for j in range(start, end):
                result_lines.add(j)

    if not result_lines:
        return content

    sorted_lines = sorted(result_lines)
    output = []
    prev = -2
    for idx in sorted_lines:
        if idx > prev + 1:
            output.append("  ...")
        output.append(lines[idx])
        prev = idx

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="Search Claude Code JSONL session logs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("jsonl_path", help="Path to the JSONL transcript file")
    parser.add_argument("search_term", help="Text to search for (case-insensitive)")
    parser.add_argument("--context", "-C", type=int, default=0,
                        help="Lines of context around each match")
    parser.add_argument("--type", "-t", dest="tool_type", default=None,
                        help="Filter by tool type (write, edit, read, bash, etc.)")
    parser.add_argument("--max", "-m", type=int, default=50,
                        help="Maximum number of results (default: 50)")

    args = parser.parse_args()
    search_jsonl(args.jsonl_path, args.search_term, args.context, args.tool_type, args.max)


if __name__ == "__main__":
    main()
