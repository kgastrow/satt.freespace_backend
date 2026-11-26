# Skip Task

Mark a task as skipped and handle dependencies.

## Arguments
- `$1` - ADW ID
- `$2` - Task ID to skip
- `$3` - Reason for skipping

## Instructions

### 1. Load State

Read `agents/{adw_id}/rescue_state.json`

### 2. Validate Task

Check that:
- Task exists in task graph
- Task is not already completed
- Task is not currently running

### 3. Mark as Skipped

Update task status to "skipped" with reason.

### 4. Handle Dependencies

For tasks that depend on the skipped task:
- If the skipped task was optional, dependents can proceed
- If the skipped task was required, mark dependents as blocked
- Log the dependency impact

### 5. Update State

Save updated rescue state.

## Output

```
=== TASK SKIPPED ===

Task: {task_id}
Description: {task_description}
Reason: {skip_reason}

Impact:
  - Direct dependents: {count}
  - Affected tasks: {list}

Dependents Status:
  - task-025-wire-DataTable: Now blocked (required dependency)
  - task-026-test-DataTable: Now blocked (required dependency)

Recommendation: Consider using template DataTable component
```

Update rescue_state.json:
- Task status = "skipped"
- Task skip_reason = provided reason
- Update execution.skipped_tasks list

## Validation

- Task exists
- Status updated to skipped
- Dependents handled appropriately
- State saved

$ARGUMENTS
