#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW SDLC ZTE Iso - Zero Touch Execution: Complete SDLC with automatic shipping

Usage: uv run adw_sdlc_zte_iso.py <issue-number> [adw-id] [--skip-e2e] [--skip-resolution] [--skip-smoke]

This script runs the complete ADW SDLC pipeline with automatic shipping:
1. adw_plan_iso.py - Planning phase (isolated)
2. adw_build_iso.py - Implementation phase (isolated)
3. adw_test_iso.py - Testing phase (isolated)
4. adw_smoke_iso.py - Smoke testing phase (isolated, blocking)
5. adw_review_iso.py - Review phase (isolated)
6. adw_document_iso.py - Documentation phase (isolated)
7. adw_ship_iso.py - Ship phase (approve & merge PR)

ZTE = Zero Touch Execution: The entire workflow runs to completion without
human intervention, automatically shipping code to production if all phases pass.

The scripts are chained together via persistent state (adw_state.json).
Each phase runs on the same git worktree with dedicated ports.
"""

import subprocess
import sys
import os

# Add the parent directory to Python path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from adw_modules.workflow_ops import ensure_adw_id, format_issue_message
from adw_modules.state import ADWState
from adw_modules.github import make_issue_comment


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
        print(
            "Usage: uv run adw_sdlc_zte_iso.py <issue-number> [adw-id] [--skip-e2e] [--skip-resolution] [--skip-smoke]"
        )
        print("\n🚀 Zero Touch Execution: Complete SDLC with automatic shipping")
        print("\nThis runs the complete isolated Software Development Life Cycle:")
        print("  1. Plan (isolated)")
        print("  2. Build (isolated)")
        print("  3. Test (isolated)")
        print("  4. Smoke (isolated, blocking)")
        print("  5. Review (isolated)")
        print("  6. Document (isolated)")
        print("  7. Ship (approve & merge PR) 🚢")
        print("\n⚠️  WARNING: This will automatically merge to main if all phases pass!")
        sys.exit(1)

    issue_number = sys.argv[1]
    adw_id = sys.argv[2] if len(sys.argv) > 2 else None

    # Ensure ADW ID exists with initialized state
    adw_id = ensure_adw_id(issue_number, adw_id)
    print(f"Using ADW ID: {adw_id}")

    # Load state for persistence across phases
    state = ADWState.load(adw_id)
    if state:
        state.append_adw_id("adw_sdlc_zte_iso")
    else:
        state = ADWState(adw_id)
        state.update(adw_id=adw_id, issue_number=issue_number)
        state.append_adw_id("adw_sdlc_zte_iso")
    state.save("adw_sdlc_zte_iso_start")

    # Post initial ZTE message
    try:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, "ops", "🚀 **Starting Zero Touch Execution (ZTE)**\n\n"
                               "This workflow will automatically:\n"
                               "1. ✍️ Plan the implementation\n"
                               "2. 🔨 Build the solution\n"
                               "3. 🧪 Test the code\n"
                               "4. 🔥 Smoke test in browser\n"
                               "5. 👀 Review the implementation\n"
                               "6. 📚 Generate documentation\n"
                               "7. 🚢 **Ship to production** (approve & merge PR)\n\n"
                               "⚠️ Code will be automatically merged if all phases pass!")
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
    plan = subprocess.run(plan_cmd)
    if plan.returncode != 0:
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
    build = subprocess.run(build_cmd)
    if build.returncode != 0:
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
    test = subprocess.run(test_cmd)
    if test.returncode != 0:
        print("Isolated test phase failed")
        # For ZTE, we should stop if tests fail
        state.update(test_phase_passed=False)
        state.save("adw_sdlc_zte_iso_test_failed")
        try:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, "ops", "❌ **ZTE Aborted** - Test phase failed\n\n"
                                   "Automatic shipping cancelled due to test failures.\n"
                                   "Please fix the tests and run the workflow again.")
            )
        except:
            pass
        sys.exit(1)

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
        smoke = subprocess.run(smoke_cmd)
        # Smoke tests are blocking - failures stop the ZTE workflow
        if smoke.returncode != 0:
            print("ERROR: Smoke test phase failed - aborting ZTE workflow")
            state.update(smoke_phase_passed=False)
            state.save("adw_sdlc_zte_iso_smoke_failed")
            try:
                make_issue_comment(
                    issue_number,
                    format_issue_message(adw_id, "ops", "❌ **ZTE Aborted** - Smoke test phase failed\n\n"
                                       "Automatic shipping cancelled due to smoke test failures.\n"
                                       "Please fix the smoke tests and run the workflow again.")
                )
            except:
                pass
            sys.exit(1)
        else:
            print("Smoke test phase completed")
    else:
        print(f"\n=== SKIPPING ISOLATED SMOKE TEST PHASE ===")

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
    review = subprocess.run(review_cmd)
    if review.returncode != 0:
        print("Isolated review phase failed")
        state.update(review_phase_passed=False)
        state.save("adw_sdlc_zte_iso_review_failed")
        try:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, "ops", "❌ **ZTE Aborted** - Review phase failed\n\n"
                                   "Automatic shipping cancelled due to review failures.\n"
                                   "Please address the review issues and run the workflow again.")
            )
        except:
            pass
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
    document = subprocess.run(document_cmd)
    if document.returncode != 0:
        print("Isolated documentation phase failed")
        # Documentation failure shouldn't block shipping
        print("WARNING: Documentation phase failed but continuing with shipping")

    # Run isolated ship with the ADW ID
    ship_cmd = [
        "uv",
        "run",
        os.path.join(script_dir, "adw_ship_iso.py"),
        issue_number,
        adw_id,
    ]
    print(f"\n=== ISOLATED SHIP PHASE (APPROVE & MERGE) ===")
    print(f"Running: {' '.join(ship_cmd)}")
    ship = subprocess.run(ship_cmd)
    if ship.returncode != 0:
        print("Isolated ship phase failed")
        state.update(ship_phase_passed=False)
        state.save("adw_sdlc_zte_iso_ship_failed")
        try:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, "ops", "❌ **ZTE Failed** - Ship phase failed\n\n"
                                   "Could not automatically approve and merge the PR.\n"
                                   "Please check the ship logs and merge manually if needed.")
            )
        except:
            pass
        sys.exit(1)

    # Save final state
    state.save("adw_sdlc_zte_iso_complete")

    print(f"\n=== 🎉 ZERO TOUCH EXECUTION COMPLETED ===")
    print(f"ADW ID: {adw_id}")
    print(f"All phases completed successfully!")
    print(f"✅ Code has been shipped to production!")
    print(f"\nWorktree location: trees/{adw_id}/")
    print(f"To clean up: ./scripts/purge_tree.sh {adw_id}")

    try:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, "ops", "🎉 **Zero Touch Execution Complete!**\n\n"
                               "✅ Plan phase completed\n"
                               "✅ Build phase completed\n"
                               "✅ Test phase completed\n"
                               f"{'✅' if not skip_smoke else '⏭️'} Smoke phase\n"
                               "✅ Review phase completed\n"
                               "✅ Documentation phase completed\n"
                               "✅ Ship phase completed\n\n"
                               "🚢 **Code has been automatically shipped to production!**")
        )
    except:
        pass


if __name__ == "__main__":
    main()
