# Chrome Smoke Testing Framework

**ADW ID:** 756cce26 | **Date:** 2026-01-06 | **Specification:** specs/issue-4-adw-756cce26-sdlc_planner-add-chrome-smoke-testing.md

## Overview

Integrated contextual smoke testing into ADW workflows that validates completed work in a real browser environment via dynamically-generated tests. Tests verify UI visibility, button interactivity, form input, and happy path workflows. Chrome availability is automatically detected (Mac/non-WSL only), and test failures are non-blocking.

## Implementation

### Files Modified

| File | Change |
|------|--------|
| `adws/adw_modules/utils.py` | Added `is_chrome_available()` - detects Mac/Darwin and validates Playwright MCP config |
| `adws/adw_modules/data_types.py` | Added `/smoke_test` to `SlashCommand` enum, `adw_smoke_iso` to `ADWWorkflow` enum, `SmokeTestResult` model |
| `adws/adw_modules/agent.py` | Model mapping for `/smoke_test` command (Sonnet for cost efficiency) |
| `.claude/commands/smoke_test.md` | Generates 2-4 contextual tests from spec files and git diffs |
| `adws/adw_smoke_iso.py` | Orchestrates smoke testing with non-blocking failures and GitHub reporting |
| `adws/adw_sdlc_iso.py` | Integrated smoke phase between Test and Review |
| `adws/adw_sdlc_zte_iso.py` | Same integration as above |
| `.claude/commands/classify_adw.md` | Added `adw_smoke_iso` to valid ADW commands |
| `.claude/commands/e2e/test_smoke_test_workflow.md` | E2E test for smoke test functionality |
| `.ports.env` | Port configuration for isolated worktree environments |
| `playwright-mcp-config.json` | Playwright MCP server configuration |

### Architecture Decisions

- **Chrome Detection**: Platform-aware (Mac/Darwin only via `platform.system() == "Darwin"`), validates Playwright MCP config exists, gracefully skips on Linux/WSL (checks `/proc/version` for Microsoft/WSL markers)
- **Dynamic Generation**: Tests generated from spec files and git diffs—not static or regression-focused; ensures contextual relevance and zero maintenance burden
- **Non-Blocking Design**: Test failures don't halt workflows; results post to GitHub and workflow continues to Review phase regardless of outcomes
- **Screenshot Capture**: Captured at key steps, saved to `agents/<adw_id>/smoke_test/img/<test_name>/` with sequential naming (`01_name.png`, etc.)
- **SDLC Placement**: Workflow sequence: Plan → Build → Test → **Smoke** → Review → Document
- **Performance**: 2-4 tests max per feature, 5-10 steps per test, basic happy path only

## Usage

### Automatic Execution

Smoke tests run automatically in standard SDLC workflows (`adw_sdlc_iso.py`, `adw_sdlc_zte_iso.py`):
1. After Test phase completes successfully
2. Before Review phase begins
3. Results posted to GitHub issue
4. Workflow continues regardless of test outcomes

### Skip Smoke Tests

```bash
uv run adws/adw_sdlc_iso.py <issue-number> --skip-smoke
```

### Manual Execution

```bash
uv run adws/adw_smoke_iso.py <issue-number> <adw-id>
```

**Prerequisites:**
- ADW state exists (run `adw_plan_iso.py` first)
- Valid worktree created
- Chrome available (Mac/non-WSL)
- Playwright MCP configured (`.mcp.playwright.json` exists)

### Manual Command Execution

```bash
claude --mcp-config .mcp.playwright.json /smoke_test <spec_file> <adw_id> <agent_name> [app_url]
```

## Configuration

### Chrome Requirements

1. Mac/Darwin platform via `platform.system() == "Darwin"`
2. Not WSL (validates `/proc/version` for Microsoft/WSL markers)
3. Playwright MCP configured (`.mcp.playwright.json` exists)

### Application URL Detection

1. Checks `.ports.env` in worktree directory for `FRONTEND_PORT`
2. Constructs `http://localhost:${FRONTEND_PORT}`
3. Falls back to `http://localhost:5173`

### Environment Variables

- `GITHUB_PAT`: For posting results to GitHub issues (optional if using `gh` CLI)

## Results Format

Posted to GitHub issues:

```markdown
## 🔥 Smoke Test Results

**3/4 smoke tests passed** (1 failed)

_Note: Smoke test failures are non-blocking and logged for review._

### ❌ Failed
- **Verify Export Form Accepts Input**: Checks form accepts user input
  - Error: `Form input field was disabled, could not enter text`
  - Screenshots: 1 captured

### ✅ Passed
- **Verify New Feature UI is Visible**: New export button is visible
  - Screenshots: 2 captured
- **Verify Export Button is Clickable**: Clicking exports triggers action
  - Screenshots: 2 captured
```

## Testing

### Validate Chrome Detection

```bash
cd /Users/kgastrow/ayzer.webapp.template/trees/756cce26
uv run python -c "import sys; sys.path.insert(0, 'adws'); from adw_modules.utils import is_chrome_available; print(is_chrome_available())"
```

Expected: `(True, None)` on Mac, `(False, 'reason...')` on Linux/WSL

### Run E2E Test

```bash
cd /Users/kgastrow/ayzer.webapp.template/trees/756cce26
claude /e2e:test_smoke_test_workflow
```

Validates: Chrome detection, spec analysis, test generation, Playwright execution, JSON results, non-blocking behavior

### Test Non-Blocking Behavior

1. Break a UI element intentionally
2. Run SDLC workflow with smoke tests enabled
3. Observe failure reporting to GitHub
4. Verify workflow continues to Review phase
5. Revert breaking change

## Design Notes

### Non-Blocking Philosophy

Smoke tests intentionally don't block workflows to:
- Enable fast iteration without environmental blockers
- Allow human review to assess test failure criticality
- Handle Chrome unavailability gracefully on non-Mac platforms

### Dynamic vs. Static Testing

Unlike versioned E2E tests, smoke tests are dynamically generated per feature:
- Contextually relevant to specific implementation
- Zero maintenance burden for test files
- Focus on new functionality, not regression testing
- Fast execution (2-4 tests, basic interactions)

### Platform Limitations

Mac requirement is due to Playwright MCP browser automation constraints. Linux/WSL systems automatically skip tests with clear messaging—expected behavior, not a failure.

### Screenshot Management

Saved to `agents/<adw_id>/smoke_test/img/<test_name>/` with sequential naming. Provide visual verification during review; future enhancement: automatic GitHub upload.

### Performance Targets

- 2-4 tests per feature
- 5-10 steps per test
- Basic happy path only (edge cases in unit/integration tests)
