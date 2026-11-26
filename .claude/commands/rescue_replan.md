# Re-plan Task Graph

Re-generate the task graph based on learnings from execution.

## Arguments
- `$1` - ADW ID
- `$2` - Reason for re-plan

## Input Files
- `triage/task_graph.json` (current plan)
- `agents/{adw_id}/rescue_state.json` (state with learnings)

## Instructions

### 1. Analyze Current State

Read the rescue state to understand:
- Completed tasks (keep marked as completed)
- Failed tasks (analyze why)
- Skipped tasks (may need re-evaluation)
- Learnings discovered during execution

### 2. Determine Re-plan Strategy

**For task failures:**
- If failure is a blocking dependency, create alternative tasks
- If failure is non-critical, mark dependents as skippable
- If failure reveals missing prerequisite, add new tasks

**For new learnings:**
- If discovery reveals new complexity, add tasks to handle it
- If component is simpler than expected, merge tasks
- If API mismatch found, add data transformation tasks

### 3. Re-plan Triggers

Handle each trigger type:

**`blocked` - All remaining tasks blocked by failures:**
- Identify the blocking failed task(s)
- Create bypass tasks or alternative approaches
- Update dependencies to use bypass

**`task_failed:{task_id}` - Specific task failed:**
- Analyze failure reason from error_message
- Create corrective task or workaround
- Mark original task as superseded

**`scope_change` - User requested scope reduction:**
- Remove tasks for excluded features
- Update dependencies
- Recalculate estimates

**`complexity_discovered` - Found unexpected complexity:**
- Break complex task into smaller tasks
- Add prerequisite tasks
- Update estimates

### 4. Archive Current Plan

The orchestrator archives the current plan before calling this command.
Reference previous versions in `triage/task_graph_v{N}.json`.

### 5. Generate Updated Plan

Create new `triage/task_graph.json` with:

```json
{
  "version": 2,
  "generated_at": "ISO timestamp",
  "replan_reason": "{reason from $2}",
  "previous_version": "triage/task_graph_v1.json",
  "changes": [
    {
      "type": "removed",
      "task_id": "task-015-component-DataTable",
      "reason": "Using template DataTable instead"
    },
    {
      "type": "added",
      "task_id": "task-040-wire-DataTableAdapter",
      "reason": "Need adapter for template DataTable"
    },
    {
      "type": "modified",
      "task_id": "task-020-wire-UserCard",
      "change": "Updated dependency to task-040"
    }
  ],
  "tasks": [
    // ... updated task list
  ]
}
```

### 6. Preserve Completed Work

- Keep completed tasks marked as `status: "completed"`
- Do not regenerate outputs from completed tasks
- Maintain commit history reference

### Re-plan Limits

Do NOT re-plan for:
- Minor errors that retry can fix
- Expected failures (MANUAL tier components that were marked risky)
- Already-skipped optional tasks
- Cosmetic issues

DO re-plan when:
- Task fails 3+ times with same error
- Blocking dependency prevents any progress
- User requests scope change
- Critical integration discovered

## Output

Updated `triage/task_graph.json` with:
- Incremented `version`
- `replan_reason` field
- `changes` array documenting what changed
- Updated task list

Report summary:
```
=== RE-PLAN SUMMARY ===

Version: 1 -> 2
Reason: task_failed:task-015-component-DataTable

Changes:
  - Removed: task-015-component-DataTable (3 failures, using template)
  - Added: task-040-wire-DataTableAdapter (bridge to template)
  - Modified: task-020-wire-UserCard (new dependency)

Task Stats:
  - Completed: 12
  - Pending: 18 (was 20)
  - Removed: 2

Estimated remaining: 15-20 hours
```

## Validation

- New task_graph.json is valid
- Version incremented
- Completed tasks preserved
- No circular dependencies
- All new tasks have valid slash_commands

$ARGUMENTS
