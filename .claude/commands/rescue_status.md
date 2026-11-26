# Rescue Status

Display current status of the rescue workflow.

## Arguments
- `$1` - ADW ID

## Instructions

Read the rescue state and display comprehensive status.

### 1. Load State

Read `agents/{adw_id}/rescue_state.json`

### 2. Display Status

## Output

Display formatted status report:

```
=== VIBE CODE RESCUE STATUS ===

ADW ID: {adw_id}
Current Phase: {current_phase}
Plan Version: {plan_version}

--- DISCOVERY ---
Status: {complete/incomplete}
Features Found: {count}
UI Components: {count}
  - AUTO: {count}
  - ASSISTED: {count}
  - MANUAL: {count}
Difficulty: {difficulty}

--- TRIAGE ---
Status: {complete/incomplete}
Backend Domains: {count}
  - REPLACE: {count}
  - ADAPT: {count}
  - SKIP: {count}
Task Graph: {task_count} tasks
Estimated Hours: {min}-{max}

--- EXECUTION ---
Status: {complete/incomplete}
Tasks:
  - Completed: {count}
  - Failed: {count}
  - Pending: {count}
  - Skipped: {count}
Current Task: {task_id or "none"}

--- VALIDATION ---
Status: {complete/incomplete}
Tests: {passed}/{total} ({percent}%)
Visual Match: {percent}%
Feature Parity: {percent}%

--- CHECKPOINTS ---
{list checkpoints with approval status}

--- LEARNINGS ---
{list learnings discovered during execution}

--- NEXT STEPS ---
{Recommendation based on current state}
```

Also output JSON for programmatic access:

```json
{
  "adw_id": "{adw_id}",
  "current_phase": "execution",
  "overall_progress_percent": 65,
  "phases": {
    "discovery": {"complete": true, "details": {...}},
    "triage": {"complete": true, "details": {...}},
    "execution": {"complete": false, "progress_percent": 70, "details": {...}},
    "validation": {"complete": false, "details": {...}}
  },
  "blockers": [],
  "next_action": "Continue execution - 8 tasks remaining"
}
```

## Validation

- State file exists and loads
- All phases have status
- Progress percentages are accurate
- Next steps are actionable

$ARGUMENTS
