# ADW (Agentic Developer Workflow) Context Guide

## Architecture Overview

```
adws/
├── adw_*_iso.py              # Workflow orchestrators (entry points)
├── smoke_test_runner.py      # Direct Playwright smoke test executor
├── e2e_test_runner.py        # Direct Playwright E2E test executor
├── adw_modules/              # Shared Python modules
│   ├── agent.py              # Claude Code CLI execution
│   ├── data_types.py         # Pydantic models (SlashCommand, ADWStateData)
│   ├── database_ops.py       # Isolated database management
│   ├── git_ops.py            # Git operations
│   ├── github.py             # GitHub API
│   ├── multi_phase_ops.py    # Multi-phase plan parsing
│   ├── state.py              # ADWState persistence
│   ├── test_ops.py           # Test execution
│   ├── utils.py              # parse_json, make_adw_id, setup_logger
│   ├── worktree_ops.py       # Git worktree management
│   └── workflow_ops.py       # High-level workflow operations
└── adw_triggers/             # Event triggers (webhook, cron)
```

---

## Workflow Taxonomy (19 Total)

### Entry Point Workflows (create worktree, start from issue)

| Workflow | Purpose |
|----------|---------|
| `adw_plan_iso.py` | Plan-only from issue, creates worktree + branch |
| `adw_patch_iso.py` | Direct patch from `adw_patch` keyword, creates worktree |

### Dependent Workflows (require existing worktree/state)

| Workflow | Purpose | Requires |
|----------|---------|----------|
| `adw_build_iso.py` | Implement plan in worktree | plan_file, worktree |
| `adw_test_iso.py` | Run tests with resolution | worktree |
| `adw_smoke_iso.py` | Run smoke tests (blocking) | worktree, running app |
| `adw_review_iso.py` | Review implementation | worktree |
| `adw_document_iso.py` | Generate documentation | worktree |
| `adw_ship_iso.py` | Merge to main | all state populated |

### Composite Workflows (chain multiple phases)

| Workflow | Phases |
|----------|--------|
| `adw_plan_build_iso.py` | Plan + Build |
| `adw_plan_build_test_iso.py` | Plan + Build + Test |
| `adw_plan_build_review_iso.py` | Plan + Build + Review |
| `adw_plan_build_test_review_iso.py` | Plan + Build + Test + Review |
| `adw_plan_build_document_iso.py` | Plan + Build + Document |
| `adw_sdlc_iso.py` | Plan + Build + Test + Smoke + Review + Document |
| `adw_sdlc_zte_iso.py` | Full SDLC + Ship (Zero Touch Execution) |

### Multi-Phase Workflow

| Workflow | Purpose |
|----------|---------|
| `adw_multi_phase_sdlc_iso.py` | Large features split into phases with dependencies |

### Router Workflow

| Workflow | Purpose |
|----------|---------|
| `adw_sdlc_router_iso.py` | Auto-routes by issue type and complexity |

### Utility Workflows (standalone tools)

| Workflow | Purpose | Worktree |
|----------|---------|----------|
| `adw_context_management_iso.py` | Parallel context doc refinement | No |
| `adw_implementation_consistency_iso.py` | Parallel code review vs docs | No |

---

## Key Concepts

- **ADW ID**: Format `YYYYMMDDHHMMSS-<8-char-uuid>` (e.g., `20260107143052-a1b2c3d4`)
- **Worktree**: Isolated execution in `trees/{adw_id}/`
- **Database**: Isolated `appdb_{adw_id_suffix}` (last 8 chars of ADW ID)
- **State**: Persistent at `agents/{adw_id}/adw_state.json`
- **Ports**: Backend 9100-9114, Frontend 9200-9214 (15 concurrent)

---

## Core Patterns

### State Management

```python
from adw_modules.state import ADWState

state = ADWState.load(adw_id) or ADWState(adw_id)  # logger is optional
state.update(branch_name=branch_name, worktree_path=worktree_path)
state.save("workflow_step_name")  # Always save with step name
```

**All State Fields** (`ADWStateData`):

| Field | Type | Description |
|-------|------|-------------|
| `adw_id` | str | Unique workflow identifier |
| `issue_number` | str? | GitHub issue number |
| `branch_name` | str? | Git branch name |
| `plan_file` | str? | Path to plan file |
| `issue_class` | IssueClassSlashCommand? | `/chore`, `/bug`, `/feature` |
| `worktree_path` | str? | Path to isolated worktree |
| `backend_port` | int? | Allocated backend port (9100-9114) |
| `frontend_port` | int? | Allocated frontend port (9200-9214) |
| `database_name` | str? | Isolated database (e.g., `appdb_ccfd0008`) |
| `model_set` | ModelSet | `"base"` or `"heavy"` |
| `all_adws` | list[str] | Workflows that have run |
| `smoke_test_passed` | int? | Count of passed smoke tests |
| `smoke_test_failed` | int? | Count of failed smoke tests |
| `smoke_test_skipped` | int? | Count of skipped smoke tests |
| `smoke_test_screenshot_urls` | list[str] | R2 URLs for screenshots |
| `workflow_stage` | str? | Current stage for resume |
| `workflow_pid` | int? | Main workflow process ID |
| `workflow_pgid` | int? | Process group ID for cleanup |
| `context_files_loaded` | list[str] | ai_docs files read by agents |
| `context_validation_passed` | bool? | Context validation result |
| `context_violations_count` | int? | Number of context violations |

### Agent Template Execution

```python
from adw_modules.agent import execute_template
from adw_modules.data_types import AgentTemplateRequest

request = AgentTemplateRequest(
    agent_name="descriptive_unique_name",
    slash_command="/command_name",
    args=[arg1, arg2],
    adw_id=adw_id,
    working_dir=worktree_path,  # CRITICAL for isolated workflows
)
response = execute_template(request)
```

**Critical**: Always pass `working_dir` for isolated workflows. Agent names must be unique per execution.

---

## Context Preamble Injection

For implementation/planning commands, `execute_template()` auto-injects a context preamble that instructs agents to:

1. Read `CLAUDE.md` for project conventions
2. Read `.claude/commands/conditional_context.md` for context lookup
3. Load applicable `ai_docs/` files before writing code
4. Confirm context loaded with assertion

**Commands that skip preamble** (`SKIP_CONTEXT_PREAMBLE_COMMANDS`):

```
/classify_issue, /classify_adw, /classify_sdlc_complexity,
/generate_branch_name, /commit, /pull_request, /install_worktree,
/track_agentic_kpis, /prepare_app, /start, /setup_test_auth,
/teardown_test_auth, /prime
```

---

## Command Reference

### All Slash Commands

| Category | Commands |
|----------|----------|
| **Planning** | `/feature`, `/bug`, `/chore`, `/plan_multi_phase` |
| **Implementation** | `/implement`, `/implement_phase`, `/patch` |
| **Testing** | `/test`, `/smoke_test`, `/test_e2e`, `/write_tests` |
| **Resolution** | `/resolve_failed_test`, `/resolve_failed_smoke_test`, `/resolve_failed_e2e_test`, `/resolve_build_error` |
| **Review** | `/review`, `/review_phase`, `/review_consistency` |
| **Setup** | `/install_worktree`, `/prepare_app` |
| **Utility** | `/commit`, `/pull_request`, `/generate_branch_name`, `/document`, `/track_agentic_kpis` |
| **Classification** | `/classify_issue`, `/classify_adw`, `/classify_sdlc_complexity` |
| **Context** | `/refine_context` |

### Model Selection Map

Models are selected via `SLASH_COMMAND_MODEL_MAP` in `agent.py`:

| Command | Base | Heavy |
|---------|------|-------|
| `/classify_*`, `/generate_branch_name`, `/commit`, `/pull_request` | sonnet | sonnet |
| `/plan_multi_phase`, `/refine_context` | opus | opus |
| `/implement`, `/write_tests`, `/resolve_*`, `/review*`, `/document` | sonnet | opus |
| `/feature`, `/bug`, `/chore`, `/patch` | sonnet | opus |

---

## Module Reference

| Module | Key Functions |
|--------|---------------|
| `state.py` | `ADWState.load()`, `.update()`, `.save()`, `.get_working_directory()` |
| `agent.py` | `execute_template()`, `get_model_for_slash_command()`, `get_context_preamble()` |
| `workflow_ops.py` | `ensure_adw_id()`, `format_issue_message()`, `classify_issue()`, `generate_branch_name()`, `build_plan()`, `implement_plan()`, `create_pull_request()` |
| `multi_phase_ops.py` | `MultiPhaseState`, `parse_multi_phase_plan()`, `get_phase_by_id()` |
| `worktree_ops.py` | `create_worktree()`, `setup_worktree_environment()`, `validate_worktree()`, `get_ports_for_adw()` |
| `git_ops.py` | `push_branch()`, `create_branch()`, `get_current_branch()` |
| `test_ops.py` | `run_scoped_tests()`, `run_validation_suite()`, `run_backend_tests()` |
| `database_ops.py` | `create_isolated_database()`, `drop_isolated_database()`, `get_redis_db_for_adw()` |
| `utils.py` | `parse_json()`, `make_adw_id()`, `setup_logger()`, `get_safe_subprocess_env()` |

---

## Anti-Patterns

| Bad | Good | Why |
|-----|------|-----|
| Missing `working_dir` in request | Always include `working_dir=worktree_path` | Isolated workflows fail without it |
| Passing data between functions without state | `state.update()` then `state.save()` | Survives crashes |
| Hardcoded paths | `state.get("plan_file")` or dynamic | Portable |
| Generic agent names (`"reviewer"`) | Unique names (`f"phase_reviewer_{phase_id}"`) | Avoid collisions |
| `subprocess.run(cmd)` without check | Check `result.returncode != 0` | Handle failures |
| Using worktree without validation | `validate_worktree()` first | Catch invalid state |

---

## Smoke Test Workflow

**Architecture**: Direct Playwright execution (not MCP) for ~10x faster performance.

**Flow:**
1. First run: Claude generates test JSON via `/smoke_test` -> saved to `agents/{adw_id}/smoke_test_runner/smoke_tests.json`
2. `smoke_test_runner.py` executes tests directly (no Claude/MCP)
3. Retries: Re-execute runner with cached tests (FAST, no regeneration)

**Performance**: 10-20s per run vs 3-5min with MCP

**Test Definition Format:**
```json
{
  "application_url": "http://localhost:5173",
  "auth": {"access_token": "...", "refresh_token": "..."},
  "tests": [{"name": "Test", "steps": [{"action": "navigate", "url": "/"}]}]
}
```

---

## Multi-Phase Workflow

**Key Pattern:**
```python
mp_state = MultiPhaseState(adw_id)
mp_state.initialize_phases([p.id for p in plan.phases])

if mp_state.dependencies_met(phase):
    mp_state.mark_phase_started(phase_id)
    # ... execute ...
    mp_state.mark_phase_completed(phase_id, commit_sha)
```

**Notes:**
- Dependencies support "Phase N" references (auto-resolved to IDs)
- `/prepare_app` runs on both fresh start and resume
- Phase file scopes must be strictly respected

---

## Decision Tree

```
New issue?
├─ Yes -> adw_sdlc_router_iso.py (auto-routes by complexity)
│        ├─ /feature (complex) -> adw_multi_phase_sdlc_iso.py
│        └─ /feature (simple), /bug, /chore -> adw_sdlc_iso.py
└─ No -> Run dependent workflow with existing adw_id

Need auto-merge? -> adw_sdlc_zte_iso.py
Skip smoke tests? -> Pass --skip-smoke flag
```

---

## Checklist

### State & Config
- [ ] State loaded/saved after significant changes
- [ ] `working_dir` passed to all template executions
- [ ] Unique agent names
- [ ] Use `push_branch()` from git_ops

### Error Handling
- [ ] Error handling on all subprocess calls
- [ ] Worktree validated before use
- [ ] JSON parsing handles markdown-wrapped responses
- [ ] Cleanup in try/finally

### Multi-Phase
- [ ] Dependencies can use "Phase N" format
- [ ] `/prepare_app` on fresh start and resume
- [ ] Phase file scopes respected

---

## Troubleshooting

### Pydantic ValidationError for SlashCommand

**Symptom:** `Input should be '/chore', '/bug', ... input_value='/new_command'`

**Cause:** New slash command not registered in type system.

**Fix:** Update TWO files:
1. `adws/adw_modules/data_types.py` - Add to `SlashCommand` Literal
2. `adws/adw_modules/agent.py` - Add to `SLASH_COMMAND_MODEL_MAP`

**Note:** Error appears in stderr, not execution.log (exception before logging established).

### Database/Redis Isolation

**Symptom:** Migration conflicts or data bleeding between parallel ADWs

**Cause:** Sharing main database/Redis

**Fix:** Each ADW gets isolated resources:
- Database: `appdb_{last_8_chars_of_adw_id}`
- Redis: Databases 2-14 (deterministically assigned)
- PgBouncer bypassed for isolated DBs (direct PostgreSQL connection)
