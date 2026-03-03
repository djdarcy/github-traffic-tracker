"""
plan_lib.executor — Plan execution with dependency resolution.

The primary value-add of plan_lib: execute_plan() handles the depends_on
graph, error propagation, and dry-run mode so consumers never implement
DAG resolution themselves.

Usage:
    from ghtraf.lib.core_lib import Action, ActionResult, Plan
    from ghtraf.lib.plan_lib import execute_plan

    def my_executor(action: Action) -> ActionResult:
        # do the real work
        return ActionResult(action=action, success=True, message="done")

    results = execute_plan(plan, my_executor, dry_run=args.dry_run)
"""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from ghtraf.lib.core_lib import Action, ActionResult, ErrorPolicy, Plan


def _topological_order(actions: list[Action]) -> list[Action]:
    """Sort actions respecting depends_on relationships.

    Uses Kahn's algorithm for topological sort. Actions without dependencies
    preserve their original plan order (stable sort). If cycles exist, the
    remaining actions are appended in original order (cycles are caught by
    Plan.validate() separately).
    """
    # Build adjacency and in-degree maps
    id_to_action: dict[str, Action] = {a.id: a for a in actions}
    action_ids = [a.id for a in actions]
    in_degree: dict[str, int] = {aid: 0 for aid in action_ids}
    dependents: dict[str, list[str]] = defaultdict(list)

    for a in actions:
        for dep in a.depends_on:
            if dep in id_to_action:
                in_degree[a.id] += 1
                dependents[dep].append(a.id)

    # Start with zero-dependency actions in original plan order
    queue = [aid for aid in action_ids if in_degree[aid] == 0]
    ordered: list[Action] = []

    while queue:
        current = queue.pop(0)
        ordered.append(id_to_action[current])
        # Release dependents, maintaining original order
        for dep_id in dependents[current]:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                queue.append(dep_id)
        # Keep queue in original plan order
        queue.sort(key=lambda x: action_ids.index(x))

    # If cycle exists, append remaining in original order
    if len(ordered) < len(actions):
        ordered_ids = {a.id for a in ordered}
        for a in actions:
            if a.id not in ordered_ids:
                ordered.append(a)

    return ordered


def execute_plan(
    plan: Plan,
    executor_fn: Callable[[Action], ActionResult],
    *,
    dry_run: bool = False,
    on_error: ErrorPolicy = "skip_deps",
) -> list[ActionResult]:
    """Execute a plan's actions with dependency resolution and error handling.

    This is the core function of plan_lib. It:
    1. Validates the plan (raises ValueError on invalid plans)
    2. Topologically sorts actions by depends_on
    3. Executes each action via executor_fn (or simulates in dry_run)
    4. Propagates failures to dependents per the error policy

    Args:
        plan: The plan to execute.
        executor_fn: Callable that performs the real work for each action.
            Receives an Action, returns an ActionResult.
        dry_run: If True, skip execution — return success results for all
            actions without calling executor_fn.
        on_error: How to handle failures:
            - "fail_fast": stop immediately on first failure
            - "skip_deps": skip actions depending on the failed one,
              continue executing independent actions (default)
            - "continue": execute everything regardless of failures

    Returns:
        List of ActionResult in execution order.

    Raises:
        ValueError: If plan.validate() finds errors (dangling deps, dupes).
    """
    # Validate first
    errors = plan.validate()
    if errors:
        raise ValueError(
            f"Invalid plan: {'; '.join(errors)}"
        )

    if not plan.actions:
        return []

    # Sort by dependencies
    sorted_actions = _topological_order(plan.actions)

    results: list[ActionResult] = []
    failed_ids: set[str] = set()

    for action in sorted_actions:
        # Check if any dependency failed
        blocked_by = [dep for dep in action.depends_on if dep in failed_ids]

        if blocked_by:
            result = ActionResult(
                action=action,
                success=False,
                skipped=True,
                message=f"Skipped: dependency failed ({', '.join(blocked_by)})",
            )
            results.append(result)
            if on_error != "continue":
                failed_ids.add(action.id)
            continue

        # Dry-run: simulate success without executing
        if dry_run:
            results.append(ActionResult(
                action=action,
                success=True,
                skipped=True,
                message="dry-run",
            ))
            continue

        # Execute the action
        try:
            result = executor_fn(action)
        except Exception as exc:
            result = ActionResult(
                action=action,
                success=False,
                error=str(exc),
            )

        results.append(result)

        if not result.success:
            if on_error == "fail_fast":
                failed_ids.add(action.id)
                break
            elif on_error == "skip_deps":
                failed_ids.add(action.id)
            # on_error == "continue": don't track failure, deps still run
    return results
