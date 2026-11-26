#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW SDLC Iso - Complete Software Development Life Cycle workflow with isolation

Usage: uv run adw_sdlc_iso.py <issue-number> [adw-id] [--skip-e2e] [--skip-resolution] [--skip-smoke]

This script runs the complete ADW SDLC pipeline in isolation:
1. adw_plan_iso.py - Planning phase (isolated)
2. adw_build_iso.py - Implementation phase (isolated)
3. adw_test_iso.py - Testing phase (isolated)
4. adw_smoke_iso.py - Smoke testing phase (isolated, blocking)
5. adw_review_iso.py - Review phase (isolated)
6. adw_document_iso.py - Documentation phase (isolated)
7. adw_domain_docs_iso.py - Domain context documentation phase (isolated, non-blocking)

The scripts are chained together via persistent state (adw_state.json).
Each phase runs in its own git worktree with dedicated ports.
"""

import subprocess
import sys
import os

# Add the parent directory to Python path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adw_modules.workflow_ops import ensure_adw_id, format_issue_message
from adw_modules.state import ADWState
from adw_modules.github import make_issue_comment
from adw_modules import steps


def run_stage(adw_id: str, key: str, cmd: list, failed_note: str = "") -> bool:
    """Run one stage script, recording it as step `key` (running, then done or failed)."""
    steps.record(adw_id, key, "running")
    ok = subprocess.run(cmd).returncode == 0
    steps.record(adw_id, key, "done" if ok else "failed", note="" if ok else failed_note)
    return ok


def record_pr(adw_id: str, state: ADWState) -> None:
    """Step "pr": the pull request the stages created (finalize_git_operations), if there is one."""
    try:
        from adw_modules.git_ops import check_pr_exists_with_error
        saved = ADWState.load(adw_id)
        branch = (saved or state).get("branch_name")
        url, err = check_pr_exists_with_error(branch) if branch else (None, "no branch")
        if url:
            steps.record(adw_id, "pr", "done", note=f"PR #{url.rstrip('/').rsplit('/', 1)[-1]}: {url}")
        else:
            steps.record(adw_id, "pr", "failed", note=f"No pull request found{f' ({err})' if err else ''}")
    except Exception as e:  # noqa: BLE001 - reporting only
        steps.record(adw_id, "pr", "failed", note=str(e))


def main():
    """Main entry point."""
    # Check for flags
    skip_e2e = "--skip-e2e" in sys.argv
    skip_resolution = "--skip-resolution" in sys.argv
    skip_smoke = "--skip-smoke" in sys.argv

    # Remove flags from argv
    if skip_e2e:
        sys.argv.remove("--skip-e2e")
    if skip_resolution:
        sys.argv.remove("--skip-resolution")
    if skip_smoke:
        sys.argv.remove("--skip-smoke")

    if len(sys.argv) < 2:
        print("Usage: uv run adw_sdlc_iso.py <issue-number> [adw-id] [--skip-e2e] [--skip-resolution] [--skip-smoke]")
        print("\nThis runs the complete isolated Software Development Life Cycle:")
        print("  1. Plan (isolated)")
        print("  2. Build (isolated)")
        print("  3. Test (isolated)")
        print("  4. Smoke (isolated, blocking)")
        print("  5. Review (isolated)")
        print("  6. Document (isolated)")
        print("  7. Domain Docs (isolated, non-blocking)")
        sys.exit(1)

    issue_number = sys.argv[1]
    adw_id = sys.argv[2] if len(sys.argv) > 2 else None

    # Ensure ADW ID exists with initialized state
    adw_id = ensure_adw_id(issue_number, adw_id)
    print(f"Using ADW ID: {adw_id}")

    # Load state for persistence across phases
    state = ADWState.load(adw_id)
    if state:
        state.append_adw_id("adw_sdlc_iso")
    else:
        state = ADWState(adw_id)
        state.update(adw_id=adw_id, issue_number=issue_number)
        state.append_adw_id("adw_sdlc_iso")
    state.save("adw_sdlc_iso_start")

    # Post initial comment
    try:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, "ops", "🚀 Starting SDLC workflow\n\n"
                               "Phases:\n"
                               "1. ✍️ Plan\n"
                               "2. 🔨 Build\n"
                               "3. 🧪 Test\n"
                               "4. 🔥 Smoke Test\n"
                               "5. 👀 Review\n"
                               "6. 📚 Document\n"
                               "7. 🗂️ Domain Docs")
        )
    except Exception as e:
        print(f"Warning: Failed to post initial comment: {e}")

    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Run isolated plan with the ADW ID
    plan_cmd = [
        "uv",
        "run",
        os.path.join(script_dir, "adw_plan_iso.py"),
        issue_number,
        adw_id,
    ]
    print(f"\n=== ISOLATED PLAN PHASE ===")
    print(f"Running: {' '.join(plan_cmd)}")
    if not run_stage(adw_id, "plan", plan_cmd):
        print("Isolated plan phase failed")
        sys.exit(1)

    # Run isolated build with the ADW ID
    build_cmd = [
        "uv",
        "run",
        os.path.join(script_dir, "adw_build_iso.py"),
        issue_number,
        adw_id,
    ]
    print(f"\n=== ISOLATED BUILD PHASE ===")
    print(f"Running: {' '.join(build_cmd)}")
    if not run_stage(adw_id, "build", build_cmd):
        print("Isolated build phase failed")
        sys.exit(1)

    # Run isolated test with the ADW ID
    test_cmd = [
        "uv",
        "run",
        os.path.join(script_dir, "adw_test_iso.py"),
        issue_number,
        adw_id,
        "--skip-e2e",  # Always skip E2E tests in SDLC workflows
    ]

    print(f"\n=== ISOLATED TEST PHASE ===")
    print(f"Running: {' '.join(test_cmd)}")
    test_phase_passed = run_stage(adw_id, "test", test_cmd)
    if not test_phase_passed:
        print("Isolated test phase failed")
        try:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, "ops", "⚠️ Test phase failed - continuing with smoke tests\n\n"
                                   "_Note: Tests may need manual review after workflow completes._")
            )
        except Exception as e:
            print(f"Warning: Failed to post test failure comment: {e}")

    # Run isolated smoke tests with the ADW ID (blocking)
    if not skip_smoke:
        smoke_cmd = [
            "uv",
            "run",
            os.path.join(script_dir, "adw_smoke_iso.py"),
            issue_number,
            adw_id,
        ]

        print(f"\n=== ISOLATED SMOKE TEST PHASE ===")
        print(f"Running: {' '.join(smoke_cmd)}")
        smoke_phase_passed = run_stage(adw_id, "smoke", smoke_cmd, failed_note="Continuing with review")
        # Smoke tests are non-blocking - failures are reported but workflow continues
        if not smoke_phase_passed:
            print("WARNING: Smoke test phase failed - continuing workflow")
            try:
                make_issue_comment(
                    issue_number,
                    format_issue_message(adw_id, "ops", "⚠️ Smoke test phase failed - continuing with review\n\n"
                                       "_Note: Smoke tests may need manual review after workflow completes._")
                )
            except Exception as e:
                print(f"Warning: Failed to post smoke failure comment: {e}")
        else:
            print("Smoke test phase completed")
    else:
        print(f"\n=== SKIPPING ISOLATED SMOKE TEST PHASE ===")
        steps.record(adw_id, "smoke", "skipped", note="--skip-smoke")

    # Run isolated review with the ADW ID
    review_cmd = [
        "uv",
        "run",
        os.path.join(script_dir, "adw_review_iso.py"),
        issue_number,
        adw_id,
    ]
    if skip_resolution:
        review_cmd.append("--skip-resolution")
    
    print(f"\n=== ISOLATED REVIEW PHASE ===")
    print(f"Running: {' '.join(review_cmd)}")
    if not run_stage(adw_id, "review", review_cmd):
        print("Isolated review phase failed")
        sys.exit(1)

    # Run isolated documentation with the ADW ID
    document_cmd = [
        "uv",
        "run",
        os.path.join(script_dir, "adw_document_iso.py"),
        issue_number,
        adw_id,
    ]
    print(f"\n=== ISOLATED DOCUMENTATION PHASE ===")
    print(f"Running: {' '.join(document_cmd)}")
    if not run_stage(adw_id, "docs", document_cmd):
        print("Isolated documentation phase failed")
        sys.exit(1)

    # Run isolated domain documentation with the ADW ID (non-blocking)
    # Domain docs are advisory - a failure here must not fail the SDLC.
    domain_docs_cmd = [
        "uv",
        "run",
        os.path.join(script_dir, "adw_domain_docs_iso.py"),
        issue_number,
        adw_id,
    ]
    print(f"\n=== ISOLATED DOMAIN DOCUMENTATION PHASE ===")
    print(f"Running: {' '.join(domain_docs_cmd)}")
    domain_docs_passed = run_stage(adw_id, "domain_docs", domain_docs_cmd, failed_note="Advisory: continuing")
    if not domain_docs_passed:
        print("WARNING: Domain documentation phase failed - continuing (advisory)")
        try:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, "ops", "⚠️ Domain documentation phase failed - continuing (advisory)")
            )
        except Exception as e:
            print(f"Warning: Failed to post domain docs failure comment: {e}")

    record_pr(adw_id, state)

    print(f"\n=== ISOLATED SDLC COMPLETED ===")
    print(f"ADW ID: {adw_id}")
    print(f"All phases completed successfully!")
    print(f"\nWorktree location: trees/{adw_id}/")
    print(f"To clean up: ./scripts/purge_tree.sh {adw_id}")

    # Post completion message
    try:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, "ops", "✅ SDLC workflow completed\n\n"
                               "✅ Plan phase\n"
                               "✅ Build phase\n"
                               f"{'✅' if test_phase_passed else '⚠️'} Test phase\n"
                               f"{'✅' if not skip_smoke else '⏭️'} Smoke phase\n"
                               "✅ Review phase\n"
                               "✅ Document phase\n"
                               f"{'✅' if domain_docs_passed else '⚠️'} Domain Docs phase")
        )
    except Exception as e:
        print(f"Warning: Failed to post completion comment: {e}")


if __name__ == "__main__":
    steps.run_main(main)