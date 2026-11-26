# Rescue Checkpoint

Create a manual checkpoint in the rescue workflow.

## Arguments
- `$1` - ADW ID
- `$2` - Checkpoint type (triage/execution/validation/custom)
- `$3` - Notes (optional)

## Instructions

### 1. Load State

Read `agents/{adw_id}/rescue_state.json`

### 2. Generate Checkpoint Summary

Based on checkpoint type, gather relevant metrics:

**Triage Checkpoint:**
- Discovery findings
- Triage decisions
- Task graph summary
- Feasibility assessment

**Execution Checkpoint:**
- Tasks completed
- Tasks failed
- Current progress
- Blockers encountered

**Validation Checkpoint:**
- Test results
- Visual match score
- Feature parity score
- Known issues

### 3. Post GitHub Comment

If issue_number is available, post checkpoint to GitHub:

```markdown
## Vibe Code Rescue: {Checkpoint Type} Checkpoint

**ADW:** `{adw_id}`
**Timestamp:** {timestamp}

### Summary
{checkpoint-specific summary}

### Metrics
{relevant metrics}

### Notes
{provided notes}

---

Reply with:
- `continue` - Proceed with rescue
- `pause` - Pause for manual review
- `abort` - Cancel rescue

---
*ADW Rescue Workflow | {adw_id}*
```

### 4. Record Checkpoint

Add to rescue state checkpoints array.

### 5. Wait for Response (optional)

If workflow is configured for blocking checkpoints:
- Poll for response
- Handle continue/pause/abort

## Output

```
=== CHECKPOINT CREATED ===

Type: {checkpoint_type}
Timestamp: {timestamp}
Notes: {notes}

Posted to: GitHub Issue #{issue_number}

Current State:
  - Phase: {current_phase}
  - Progress: {percent}%
  - Tasks: {completed}/{total}

Awaiting response...
(Or: Checkpoint recorded, continuing execution)
```

Update rescue_state.json:
- Add to checkpoints array
- Include timestamp, type, notes

## Validation

- Checkpoint recorded in state
- GitHub comment posted (if configured)
- Response handled appropriately

$ARGUMENTS
