# ghtraf/lib/ — DazzleLib Candidate Libraries

Shared, project-agnostic libraries that power ghtraf's CLI commands. Each library
is designed for eventual extraction to standalone [DazzleLib](https://github.com/DazzleLib)
packages on PyPI. ghtraf serves as the **reference implementation** that proves
the interfaces work before extraction.

## The PEV Lifecycle

All ghtraf commands that modify state follow the **Plan-Execute-Verify (PEV)
lifecycle** — a 6-stage pattern where stages 1–3 are universal and stages 4–6
are pluggable:

```
scan(source, destination) → Plan           ← plan_lib (universal)
render(plan)              → user sees it   ← plan_lib (universal)
approve(plan)             → user says go   ← plan_lib (universal)
execute(plan, executor_fn)→ [ActionResult]  ← domain library (pluggable)
verify(results)           → check results  ← domain library (pluggable)
rollback(manifest)        → undo if needed ← domain library (pluggable)
```

The key insight: **stages 1–3 are library code** (provided by plan_lib), while
**stages 4–6 are protocol implementations** that domain-specific libraries supply.
preserve_lib is one such implementation (file-centric operations), but the same
interfaces work for network operations, API clients, or any domain where you need
trustworthy `--dry-run` and rollback.

This means `--dry-run` and real execution share 100% of decision logic — both
call the same `plan_*()` function. Only the execute step differs.

See [#53](https://github.com/djdarcy/github-traffic-tracker/issues/53) for the
architecture epic and motivation (the fork-pattern anti-pattern).

## Libraries

### core_lib (220 lines, 33 tests)

**Types-only foundation.** Zero internal dependencies. Provides the dataclasses
that every other library and consumer shares.

| Type | Purpose |
|------|---------|
| `Action` | Single operation in a plan (identity via string ID like `"gist:create:badge"`) |
| `ActionResult` | Outcome of executing an action (success, output, error) |
| `Plan` | Ordered collection of actions with dependency validation |
| `ConflictResolution` | How to handle conflicts: OVERWRITE, SKIP, ASK, RENAME, etc. (7 modes) |
| `FileCategory` | Classification of source vs destination file (IDENTICAL, MODIFIED, NEW, etc.) |
| `PlanRenderer` | Protocol that plan display implementations satisfy |

**Status:** Shipped (v0.3.3). See [#54](https://github.com/djdarcy/github-traffic-tracker/issues/54).

### plan_lib (678 lines, 50 tests)

**Execution engine and rendering.** Implements PEV stages 1–3 (scan, render,
approve) plus the `execute_plan()` orchestrator for stage 4.

| Function | PEV Stage | Purpose |
|----------|-----------|---------|
| `scan_destination()` | Scan | Compare source files against destination directory |
| `DefaultTextRenderer` | Render | Color-coded terminal plan display with THAC0 integration |
| `execute_plan()` | Execute | Topological dependency resolution, `executor_fn` dispatch, error policy |

The `executor_fn: Callable[[Action], ActionResult]` pattern keeps plan_lib
domain-agnostic. Commands provide closures over their domain libraries:

```python
# ghtraf init: executor wraps preserve_lib
executor = make_init_executor(preserve_lib)
results = execute_plan(plan, executor)

# ghtraf create: executor wraps gh.py API calls
executor = make_create_executor(gh_client)
results = execute_plan(plan, executor)
```

**Status:** Shipped (v0.3.3). See [#54](https://github.com/djdarcy/github-traffic-tracker/issues/54).

### log_lib (641 lines, 27 tests)

**THAC0 verbosity system.** Single-axis verbosity where `level <= threshold`
determines output visibility. Named channels with per-channel overrides.

| Component | Purpose |
|-----------|---------|
| `OutputManager` | Central coordinator — verbosity threshold, channel routing |
| `ChannelConfig` | Per-channel override (enable/disable, custom FD) |
| `Hint` | Context-filtered diagnostic hints with dedup |
| `trace` | Function tracing decorator |

CLI flags: `-v` (verbose), `-vv` (debug), `-q` (quiet), `-qq` (silent),
`--channel=name` (enable specific channel).

**Origin:** Verbatim copy from Prime-Square-Sum. Project-specific channels
configured at runtime via `ghtraf/channels.py`.

**Status:** Shipped (v0.3.0). See [#14](https://github.com/djdarcy/github-traffic-tracker/issues/14),
[#15](https://github.com/djdarcy/github-traffic-tracker/issues/15).

### help_lib (676 lines)

**Universal CLI help system.** Separates help content from presentation, allowing
the same content to appear as examples, tips, or contextual help.

| Component | Purpose |
|-----------|---------|
| `HelpContent` / `HelpSection` | Structured help content model |
| `HelpBuilder` | Fluent API for building help content |
| `ExampleFormatter` / `TipFormatter` | Presentation strategies |

**Origin:** Verbatim copy from Prime-Square-Sum.

**Status:** Shipped (v0.3.0). See [#14](https://github.com/djdarcy/github-traffic-tracker/issues/14).

### preserve_lib (8,687 lines, 35 tests)

**File preservation with manifests, verification, and rollback.** Provides PEV
stages 4–6 for file-centric operations: manifest-tracked copy/move, hash
verification, metadata preservation, and rollback from manifests.

| Module | Purpose | DazzleLib Target |
|--------|---------|-----------------|
| `manifest.py` | Operation manifests (file list + hashes) | dazzle_filekit |
| `verification.py` | Post-op hash verification, three-way compare | dazzle_filekit |
| `operations.py` | Copy/move/verify/restore orchestration | Partial → dazzle_filekit |
| `metadata.py` | File metadata collection and application | dazzle_filekit |
| `destination.py` | Source vs destination scanning | preserve-specific |
| `links.py` | Cross-platform junction/symlink/hardlink | dazzle_filekit or standalone |
| `pathutils.py` | Path analysis and pattern detection | dazzle_filekit |
| `path_warnings.py` | Long-path Windows warnings | preserve-specific |
| `restore.py` | Restore files from manifests | preserve-specific |
| `dazzlelink/` | Lazy-restore via .dazzlelink sidecar files | Standalone package candidate |

**Origin:** Copied from preservelib. Import paths adjusted to `ghtraf.lib.preserve_lib`.

**Status:** Shipped (v0.3.4). 27 smoke tests + 8 executor bridge integration tests.
See [#66](https://github.com/djdarcy/github-traffic-tracker/issues/66).

## Future Libraries (Not Yet Started)

| Library | Purpose | Tracking |
|---------|---------|----------|
| `project_lib` | Multi-layer config resolution (CLI > project > global) | [#68](https://github.com/djdarcy/github-traffic-tracker/issues/68) |
| `cli_kit` | Argparse scaffolding, version management | Not yet filed |

## Dependency Graph

```
core_lib          ← types only, zero deps
    ↑
plan_lib          ← imports core_lib types
    ↑
preserve_lib      ← imports core_lib types (FileCategory, ConflictResolution)
    ↑
commands/         ← import all three; provide executor_fn closures

log_lib           ← independent (no lib/ deps)
help_lib          ← independent (no lib/ deps)
```

## Design Rules

1. **No ghtraf-specific code in libraries.** Project-specific channels, descriptions,
   and configuration are injected at runtime, not baked in.
2. **Copy-first when porting.** `cp` first, `sed` import paths, `diff` to verify.
   Never read-and-rewrite through an editor.
3. **Integration test first.** Write one end-to-end test before building a new
   library to catch API mismatches early.
4. **Stdlib only.** Zero external dependencies. The only runtime requirement is
   Python 3.10+ and the `gh` CLI for API operations.

## Design History

Key design documents (filenames only — located in `private`):

- `2026-02-28__17-10-32__dev-workflow-process_dryrun-contract-system.md` — Original dry-run contract analysis
- `2026-03-02__17-45-17__dev-workflow-process_installer-class-and-plan-lib-design.md` — Installer class and plan_lib design
- `2026-03-02__18-05-16__DISCUSS_Rnd4_FINAL_ASSESSMENT_dazzlelib-installer-ecosystem.md` — Locked design decisions (Collaborate3 with Gemini 2.5 Pro)
- `2026-03-02__20-16-20__full-postmortem_core-lib-plan-lib-and-session-discoveries.md` — Implementation postmortem
- `2026-03-02__21-48-45__dev-workflow-process_missing-issues-and-plan-gaps.md` — Gap analysis and corrected dependency graph
- `2026-03-01__01-43-38__dev-workflow-process_installer-pattern-extraction-dazzlelib.md` — DazzleLib extraction strategy
