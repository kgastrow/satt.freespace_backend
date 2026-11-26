# E2E Test: Smoke Test Workflow

Test the smoke test workflow functionality to verify it can generate and execute smoke tests dynamically.

## User Story

As a developer using ADW workflows
I want smoke tests to automatically validate my changes in a browser
So that I can catch UI issues before human review

## Test Prerequisites

- Chrome must be available on the system (macOS/Darwin)
- A sample specification file must exist for testing
- The application must be running on the expected port

## Test Steps

### Part 1: Chrome Detection

1. Test Chrome detection utility:
   ```python
   import sys
   sys.path.insert(0, 'adws')
   from adw_modules.utils import is_chrome_available

   available, reason = is_chrome_available()
   print(f"Chrome available: {available}")
   if reason:
       print(f"Reason: {reason}")
   ```

2. **Verify** the function returns `(True, None)` on macOS
3. Take a screenshot of the output

### Part 2: Smoke Test Command Invocation

4. Create a minimal test specification file:
   ```bash
   mkdir -p /tmp/smoke_test_demo
   cat > /tmp/smoke_test_demo/test_spec.md <<'EOF'
   # Feature: Test Export Button

   ## Feature Description
   Add an export button to the main page that allows users to export data as CSV.

   ## User Story
   As a user
   I want to export my data
   So that I can use it in other applications

   ## Acceptance Criteria
   - Export button is visible on main page
   - Clicking export button downloads CSV file
   - CSV contains correct data
   EOF
   ```

5. Simulate git changes by creating a mock diff output
6. **Verify** the specification file was created successfully
7. Take a screenshot

### Part 3: Smoke Test Execution

8. Test that the `/smoke_test` command can be invoked:
   ```bash
   # Note: This would normally be invoked by adw_smoke_iso.py
   # For E2E testing, we verify the command exists and has proper documentation
   ls -la .claude/commands/smoke_test.md
   ```

9. **Verify** the smoke test command file exists
10. Read the smoke test command file to verify structure
11. **Verify** it contains instructions for:
    - Chrome availability checking
    - Spec file analysis
    - Git diff analysis
    - Dynamic test generation
    - Direct Playwright runner execution
12. Take a screenshot of command structure

### Part 4: Result Format Validation

13. Create a sample smoke test result JSON:
    ```python
    from adws.adw_modules.data_types import SmokeTestResult

    # Test valid smoke test result
    result = SmokeTestResult(
        test_name="Verify Export Button Visible",
        status="passed",
        test_description="Checks that the export button is visible on the main page",
        screenshots=["/path/to/screenshot1.png"],
        error=None
    )

    print(f"Test result: {result.model_dump_json(indent=2)}")
    ```

14. **Verify** the SmokeTestResult model accepts valid data
15. **Verify** the status field only accepts "passed", "failed", or "skipped"
16. Take a screenshot

### Part 5: Non-Blocking Behavior

17. Verify that `adw_smoke_iso.py` exists:
    ```bash
    ls -la adws/adw_smoke_iso.py
    ```

18. Read the script and verify:
    - It exits with code 0 even on failures
    - It checks Chrome availability first
    - It skips gracefully when Chrome unavailable
    - It posts results to GitHub issue

19. **Verify** the script contains non-blocking logic
20. Take a screenshot of key sections

### Part 6: SDLC Integration

21. Verify smoke test integration in SDLC workflows:
    ```bash
    grep -n "smoke" adws/adw_sdlc_iso.py
    grep -n "skip-smoke" adws/adw_sdlc_iso.py
    ```

22. **Verify** smoke test phase is included in the workflow
23. **Verify** `--skip-smoke` flag is supported
24. Take a screenshot of integration points

25. Verify smoke test is added to ADW classification:
    ```bash
    grep -n "adw_smoke_iso" .claude/commands/classify_adw.md
    ```

26. **Verify** `/adw_smoke_iso` is listed as a valid command
27. Take a screenshot

## Success Criteria

- Chrome detection utility works correctly on macOS
- `/smoke_test` command documentation exists and is well-structured
- `SmokeTestResult` data type accepts valid smoke test results
- `adw_smoke_iso.py` orchestrator implements non-blocking behavior
- Smoke test phase is integrated into SDLC workflows
- `--skip-smoke` flag allows bypassing smoke tests
- ADW classification includes smoke test workflow
- All verification steps pass
- At least 5 screenshots are captured

## Notes

- This is a structural/integration test, not a full end-to-end browser test
- Actual browser automation with Playwright would require a running application
- The test verifies that all components are in place and properly structured
- For full smoke test validation, use the application with real features
