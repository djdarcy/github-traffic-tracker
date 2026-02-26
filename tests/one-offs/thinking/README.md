# JSONL Session Log Toolkit

Currently we have some quick tools for exploring and recovering data from Claude Code JSONL session transcripts.

Built during the recovery of the "Stats Infrastructure Migration & Standalone Extraction" plan,
which had been overwritten when a new plan was approved in plan mode. The JSONL transcript
preserves every tool call and result, making recovery possible — but the undocumented format
required iterative schema discovery first.

## Scripts

| Script | Purpose | Key Discovery |
|--------|---------|---------------|
| `inspect_jsonl_schema.py` | Schema exploration — the "what even is this file?" phase | `obj["content"]` (top-level) is **empty** for tool calls; actual data lives in `obj["message"]["content"]`. The `"user"` type covers both human input AND tool results — discriminated by the `toolUseResult` key. |
| `search_session_log.py` | General content search across the JSONL | Keyword/tool-type filtering with context windows |
| `extract_plan_from_jsonl.py` | Targeted plan recovery from Write/Read tool calls | Read results arrive in a user-type message 2-5 lines after the Read tool_use call; content has Claude Code line-number prefixes (`     1->`) that need stripping |

## Investigation Flow

```
grep first              →  inspect schema           →  extract content
(find line numbers)        (understand JSON structure)  (recover specific text)
search_session_log.py      inspect_jsonl_schema.py      extract_plan_from_jsonl.py
```

## Example: Recover an Overwritten Plan

```bash
# Step 1: Confirm the plan text exists somewhere in the transcript
python search_session_log.py transcript.jsonl "Stats Infrastructure Migration"

# Step 2: Understand the JSONL structure (if first time)
python inspect_jsonl_schema.py transcript.jsonl --message-types
python inspect_jsonl_schema.py transcript.jsonl --tool-names

# Step 3: Find all Write/Read operations on plan files
python extract_plan_from_jsonl.py transcript.jsonl

# Step 4: Recover content from a specific Read operation
python extract_plan_from_jsonl.py transcript.jsonl --line 18207
```

## JSONL Structure (Key Findings)

Claude Code session transcripts are newline-delimited JSON. Each line is one event.

**Top-level `type` field values:**
- `assistant` — model responses and tool USE calls
- `user` — human messages AND tool RESULTS (same type!)
- `progress` — hook events between tool call and result
- `system` — context injections
- `custom-title` — session title updates

**The two-structure problem:**
- Tool USE inputs: `obj["message"]["content"][N] = {"type": "tool_use", "name": "Write", "input": {...}}`
- Tool RESULTS: `obj["message"]["content"][0] = {"type": "tool_result", "content": "<file text>"}`
- Both are under `obj["message"]["content"]`, NOT `obj["content"]` (which is empty/absent)
- Discriminator: `"toolUseResult"` key is present on tool result messages, absent on real user messages

## Session Log Locations

Claude Code stores session logs at:
```
~/.claude/sesslogs/<PROJECT_SLUG>__<SESSION_UUID>_<USERNAME>/transcript.jsonl
```

Example:
```
C:\Users\Extreme\.claude\sesslogs\COMFYUI-DAZZLESWITCH_AND_PREVIEW-BRIDGE-EXTENDED__1338f9cc-..._Extreme\transcript.jsonl
```
