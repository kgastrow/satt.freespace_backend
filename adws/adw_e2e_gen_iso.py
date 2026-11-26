#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic"]
# ///

"""
Generic E2E Test Generation — supports multiple input modes.

Generates and executes Playwright E2E tests per-module with parallel generation
and per-module retry/resolve. Works with any project, with or without existing
test specifications.

Usage:
  uv run adw_e2e_gen_iso.py --discover [--spec-dir <dir>] [--adw-id <id>]
  uv run adw_e2e_gen_iso.py --from-specs <dir> [--adw-id <id>]
  uv run adw_e2e_gen_iso.py --manifest <path> [--adw-id <id>]
  uv run adw_e2e_gen_iso.py <decomposition.json> <adw_id>  # backward compat

Common flags:
  --working-dir <path>   Repository root (default: cwd)
  --max-attempts N       Retry attempts per module (default: 5)
  --max-parallel N       Parallel generation workers (default: 4)
  --generate-only        Generate tests without executing them

Exit codes:
  0: Always (advisory mode)
"""

import sys
import os
import json
import re
import logging
import uuid
import concurrent.futures
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from adw_modules.agent import execute_template
from adw_modules.data_types import AgentTemplateRequest
from adw_modules.utils import setup_logger, check_env_vars
from adw_modules.e2e_quality_gate import run_quality_gate, format_failure_for_resolver
from adw_modules.cost_tracker import CostTracker

# Import reusable functions from greenfield orchestrator
from adw_e2e_validation_iso import (
    execute_e2e_test,
    resolve_e2e_failure,
    commit_e2e_artifacts,
    build_defect_report,
    MAX_E2E_ATTEMPTS,
    MAX_GENERATION_ATTEMPTS,
    TARGET_AUDIENCES_WITH_UI,
    AUDIENCE_LABELS,
    AGENT_APP_PREPARER,
    DEFAULT_PER_MODULE_USD_CAP,
    NO_GATE_FEEDBACK_SENTINEL,
)

# Agent names
AGENT_E2E_GEN_WRITER = "e2e_gen_writer"
AGENT_DISCOVERY = "e2e_discovery"


def generate_adw_id() -> str:
    """Generate a unique ADW ID in the standard format."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    uid = uuid.uuid4().hex[:12]
    return f"{ts}-{uid}"


# ---------------------------------------------------------------------------
# Manifest builders
# ---------------------------------------------------------------------------

def build_manifest_from_specs(spec_dir: str, working_dir: str) -> Dict[str, Any]:
    """Build a manifest from existing .md spec files.

    Scans spec_dir for test_*.md files, extracts metadata (routes, API
    endpoints, user stories), and groups related specs into modules.
    """
    spec_files = sorted(
        f for f in os.listdir(spec_dir)
        if f.startswith("test_") and f.endswith(".md")
    )

    if not spec_files:
        return {"project_summary": "", "source": "specs", "modules": []}

    # Parse each spec file
    specs: List[Dict[str, Any]] = []
    for fname in spec_files:
        fpath = os.path.join(spec_dir, fname)
        try:
            with open(fpath, "r") as f:
                content = f.read()
        except OSError:
            continue

        spec: Dict[str, Any] = {
            "file": fname,
            "path": fpath,
            "name": "",
            "routes": [],
            "api_endpoints": [],
            "user_story": "",
        }

        # Extract name from heading
        m = re.search(r"^#\s+E2E Test:\s*(.+)", content, re.MULTILINE)
        if m:
            spec["name"] = m.group(1).strip()
        else:
            # Derive from filename: test_login_success.md -> Login Success
            base = fname.replace("test_", "").replace(".md", "")
            spec["name"] = base.replace("_", " ").title()

        # Extract routes from test steps (Navigate to `/path`)
        spec["routes"] = list(set(re.findall(r"Navigate to [`'\"]?(/[^\s`'\"]+)", content)))

        # Extract API endpoints from tables or inline
        spec["api_endpoints"] = list(set(
            re.findall(r"(GET|POST|PUT|PATCH|DELETE)\s+(/api/[^\s|`]+)", content)
        ))

        # Extract user story
        story_match = re.search(
            r"## User Story\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL
        )
        if story_match:
            spec["user_story"] = story_match.group(1).strip()

        # Determine audience from routes
        audience = "end_user"
        for route in spec["routes"]:
            if route.startswith("/platform-admin"):
                audience = "platform_admin"
                break
            if route.startswith("/admin"):
                audience = "admin"
                break
        spec["audience"] = audience

        specs.append(spec)

    # Group specs into modules by route prefix
    modules = _group_specs_into_modules(specs, spec_dir)

    return {
        "project_summary": f"Manifest built from {len(spec_files)} spec files in {spec_dir}",
        "source": "specs",
        "modules": modules,
    }


def _group_specs_into_modules(
    specs: List[Dict[str, Any]], spec_dir: str
) -> List[Dict[str, Any]]:
    """Group parsed specs into modules by feature area."""
    # Extract feature key from filename: test_create_role.md -> role
    # test_list_roles.md -> role, test_edit_role.md -> role
    feature_groups: Dict[str, List[Dict[str, Any]]] = {}

    for spec in specs:
        fname = spec["file"]
        # Remove test_ prefix, .md suffix, and action prefix
        base = fname.replace("test_", "").replace(".md", "")
        # Remove common action prefixes
        for prefix in [
            "create_", "list_", "edit_", "delete_", "view_",
            "update_", "assign_", "remove_", "manage_",
            "browse_", "submit_", "mark_", "revoke_",
            "suspend_", "cancel_", "send_", "upload_",
            "download_",
        ]:
            if base.startswith(prefix):
                base = base[len(prefix):]
                break

        # Normalize: 2fa_setup -> 2fa, notification_panel -> notification
        # Take first meaningful word(s) as feature key
        parts = base.split("_")
        if len(parts) >= 2:
            feature_key = "_".join(parts[:2])
        else:
            feature_key = parts[0]

        # Further normalize known groupings
        normalization_map = {
            "notification_panel": "notifications",
            "notification_bell": "notifications",
            "notification_preferences": "notifications",
            "notification_templates": "notifications",
            "notification_unsubscribe": "notifications",
            "bulk_notifications": "notifications",
            "realtime_announcements": "announcements",
            "login_success": "auth",
            "login_invalid": "auth",
            "logout": "auth",
            "registration": "auth",
            "forgot_password": "auth",
            "reset_password": "auth",
            "token_refresh": "auth",
            "session_expiry": "sessions",
            "view_sessions": "sessions",
            "revoke_session": "sessions",
            "sso_login": "sso",
            "sso_settings": "sso",
            "2fa_setup": "2fa",
            "2fa_login": "2fa",
            "2fa_disable": "2fa",
            "2fa_enforcement": "2fa",
            "change_password": "account",
            "change_email": "account",
            "delete_account": "account",
            "view_profile": "profile",
            "update_profile": "profile",
            "upload_avatar": "profile",
            "connected_accounts": "profile",
            "create_organization": "organizations",
            "list_organizations": "organizations",
            "view_organization": "organizations",
            "update_organization": "organizations",
            "delete_organization": "organizations",
            "organization_members": "organizations",
            "create_role": "roles",
            "list_roles": "roles",
            "edit_role": "roles",
            "delete_role": "roles",
            "assign_role": "roles",
            "remove_role": "roles",
            "permission_gate": "roles",
            "create_user": "users",
            "list_users": "users",
            "edit_user": "users",
            "delete_user": "users",
            "suspend_user": "users",
            "impersonation": "users",
            "upload_file": "files",
            "download_file": "files",
            "list_files": "files",
            "delete_file": "files",
            "file_settings": "files",
            "storage_usage": "files",
            "data_export": "data_export",
            "export_progress": "data_export",
            "maintenance_mode": "maintenance",
            "maintenance_page": "maintenance",
            "maintenance_alert": "maintenance",
            "email_settings": "settings",
            "system_config": "settings",
            "feature_flags": "settings",
            "rate_limits": "settings",
            "api_keys": "settings",
            "cron_jobs": "settings",
            "request_logs": "settings",
            "settings_navigation": "settings",
            "sidebar_navigation": "navigation",
            "admin_hub": "navigation",
            "404_page": "navigation",
            "onboarding_fields": "onboarding",
            "onboarding_form": "onboarding",
            "onboarding_multistep": "onboarding",
            "onboarding_status": "onboarding",
            "onboarding_admin": "onboarding",
            "api_error": "errors",
            "smoke_test": "smoke",
            "locale_persistence": "i18n",
            "language_support": "i18n",
            "metrics_dashboard": "monitoring",
            "audit_logs": "monitoring",
            "websocket_connect": "websocket",
            "read_article": "help_center",
            "manage_articles": "help_center",
            "browse_articles": "help_center",
            "view_feedback": "feedback",
            "submit_feedback": "feedback",
            "cancel_deletion": "account",
        }

        lookup = base
        if lookup in normalization_map:
            feature_key = normalization_map[lookup]
        # Also try the full base without splitting
        elif "_".join(parts) in normalization_map:
            feature_key = normalization_map["_".join(parts)]

        if feature_key not in feature_groups:
            feature_groups[feature_key] = []
        feature_groups[feature_key].append(spec)

    # Convert groups to modules
    modules: List[Dict[str, Any]] = []
    for feature_key, group_specs in sorted(feature_groups.items()):
        # Determine audience (majority vote)
        audiences = [s["audience"] for s in group_specs]
        audience = max(set(audiences), key=audiences.count)

        # Collect routes and endpoints
        all_routes: List[str] = []
        all_endpoints: List[str] = []
        all_stories: List[str] = []
        spec_paths: List[str] = []

        for s in group_specs:
            all_routes.extend(s["routes"])
            all_endpoints.extend(f"{m} {p}" for m, p in s["api_endpoints"])
            if s["user_story"]:
                all_stories.append(s["user_story"])
            spec_paths.append(s["path"])

        # Build acceptance criteria from spec names
        criteria = [f"{s['name']} works correctly" for s in group_specs]

        module_name = feature_key.replace("_", " ").title()

        module: Dict[str, Any] = {
            "id": feature_key.replace("_", "-"),
            "name": module_name,
            "description": f"E2E tests for {module_name.lower()} features",
            "target_audience": audience,
            "priority": "high" if feature_key in ("auth", "navigation") else "medium",
            "dependencies": [],
            "user_stories": all_stories[:5],
            "acceptance_criteria": criteria,
            "estimated_complexity": "medium",
            "spec_path": spec_paths[0] if len(spec_paths) == 1 else "",
            "spec_paths": spec_paths,
            "routes": sorted(set(all_routes)),
            "api_endpoints": sorted(set(all_endpoints)),
            "component_paths": [],
        }
        modules.append(module)

    return modules


def run_discovery(
    working_dir: str,
    adw_id: str,
    spec_dir: Optional[str],
    logger: logging.Logger,
) -> Optional[Dict[str, Any]]:
    """Run the discovery agent to scan the project and produce a manifest."""
    output_path = os.path.join(
        working_dir, "specs", "e2e_gen", adw_id, "manifest.json"
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    args = [output_path]
    if spec_dir:
        args.append(spec_dir)
    else:
        args.append("")  # empty spec_dir

    logger.info(f"Running discovery agent (output: {output_path})")

    request = AgentTemplateRequest(
        agent_name=AGENT_DISCOVERY,
        slash_command="/discover_e2e_targets",
        args=args,
        adw_id=adw_id,
        working_dir=working_dir,
    )
    response = execute_template(request)

    if not response.success:
        logger.error(f"Discovery agent failed: {response.output[:500]}")
        return None

    if not os.path.exists(output_path):
        logger.error(f"Discovery agent did not write manifest: {output_path}")
        return None

    with open(output_path, "r") as f:
        manifest = json.load(f)

    logger.info(f"Discovery produced {len(manifest.get('modules', []))} modules")
    return manifest


# ---------------------------------------------------------------------------
# Test generation (uses /write_e2e_test instead of /write_greenfield_e2e)
# ---------------------------------------------------------------------------

def get_e2e_gen_module_output_paths(
    adw_id: str,
    audience: str,
    module_id: str,
    module_index: int,
    working_dir: str,
) -> Tuple[str, str]:
    """Compute output paths for generic e2e test files.

    Uses 40-42 number range to avoid collision with template tests (01-23)
    and greenfield tests (30-32).
    """
    safe_id = adw_id.replace("-", "_").replace("/", "_")
    safe_module = module_id.replace("_", "-")

    spec_path = os.path.join(
        working_dir,
        ".claude", "commands", "e2e",
        f"test_e2e_gen_{safe_id}_{audience}_{module_id}.md",
    )

    audience_base = {"end_user": 41, "admin": 40, "platform_admin": 42}.get(audience, 43)
    test_num = f"{audience_base}-{module_index:02d}"

    test_path = os.path.join(
        working_dir,
        "app", "frontend", "tests", "e2e",
        f"{test_num}-e2e-gen-{audience.replace('_', '-')}-{safe_module}.spec.ts",
    )
    return spec_path, test_path


def generate_e2e_test_generic(
    manifest_path: str,
    audience: str,
    spec_output_path: str,
    test_output_path: str,
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
    module_id: str = "",
    cost_tracker: Optional[CostTracker] = None,
) -> Tuple[bool, str]:
    """Spawn Claude agent to generate E2E test using /write_e2e_test.

    Same retry logic as generate_e2e_test in adw_e2e_validation_iso.py,
    but calls the generic /write_e2e_test skill with a manifest.

    After each agent invocation, runs the shared quality gate against the
    generated `.spec.ts`. A gate failure becomes feedback for the next
    attempt and counts against the generation retry budget.

    Returns ``(success, gate_summary)``.
    """
    label = f"{audience}/{module_id}" if module_id else audience

    os.makedirs(os.path.dirname(spec_output_path), exist_ok=True)
    os.makedirs(os.path.dirname(test_output_path), exist_ok=True)

    bucket = module_id or audience
    prior_feedback: Optional[str] = None
    last_gate_summary = "no gate run"

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        logger.info(
            f"Generating E2E test for {label} "
            f"(attempt {attempt}/{MAX_GENERATION_ATTEMPTS})"
        )

        agent_suffix = f"{audience}_{module_id}_{attempt}" if module_id else f"{audience}_{attempt}"
        agent_name = f"{AGENT_E2E_GEN_WRITER}_{agent_suffix}"

        # Always pass exactly 7 args; see NO_GATE_FEEDBACK_SENTINEL docstring
        # in adw_e2e_validation_iso for why a sentinel is used instead of "".
        args = [
            manifest_path, audience, spec_output_path, test_output_path,
            adw_id, module_id,
            prior_feedback if prior_feedback else NO_GATE_FEEDBACK_SENTINEL,
        ]

        request = AgentTemplateRequest(
            agent_name=agent_name,
            slash_command="/write_e2e_test",
            args=args,
            adw_id=adw_id,
            working_dir=working_dir,
        )

        response = execute_template(request)
        if cost_tracker is not None:
            cost_tracker.record_from_template_request(
                adw_id, agent_name, bucket=bucket, logger=logger,
            )

        if not response.success:
            logger.warning(
                f"E2E test generation agent failed for {label} "
                f"(attempt {attempt}): {response.output[:500]}"
            )
            if attempt < MAX_GENERATION_ATTEMPTS:
                continue
            logger.error(f"E2E test generation exhausted all {MAX_GENERATION_ATTEMPTS} attempts for {label}")
            return False, "agent failed"

        if not os.path.exists(test_output_path):
            logger.warning(
                f"Agent did not write test file: {test_output_path} "
                f"(attempt {attempt}/{MAX_GENERATION_ATTEMPTS})"
            )
            if attempt < MAX_GENERATION_ATTEMPTS:
                continue
            logger.error(f"Test file not produced after {MAX_GENERATION_ATTEMPTS} attempts for {label}")
            return False, "test file missing"

        if not os.path.exists(spec_output_path):
            logger.warning(f"Agent did not write spec file (advisory): {spec_output_path}")

        # Quality gate
        gate = run_quality_gate(test_output_path, working_dir, logger)
        last_gate_summary = gate.summary()
        if gate.passed:
            logger.info(f"Generated E2E test for {label} (attempt {attempt}): {last_gate_summary}")
            logger.info(f"  Test: {test_output_path}")
            return True, last_gate_summary

        logger.warning(
            f"Quality gate failed for {label} (attempt {attempt}): {last_gate_summary}"
        )
        prior_feedback = format_failure_for_resolver(gate)
        if attempt < MAX_GENERATION_ATTEMPTS:
            continue
        logger.error(
            f"Quality gate did not pass after {MAX_GENERATION_ATTEMPTS} generation attempts for {label}"
        )
        return False, last_gate_summary

    return False, last_gate_summary


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def group_manifest_modules_by_audience(
    manifest: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """Group manifest modules by target_audience, filtering backend_only."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for module in manifest.get("modules", []):
        audience = module.get("target_audience", "end_user")
        if audience == "backend_only":
            continue
        if audience not in groups:
            groups[audience] = []
        groups[audience].append(module)
    return groups


def run_e2e_gen(
    manifest: Dict[str, Any],
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
    manifest_path: str,
    max_attempts: int = MAX_E2E_ATTEMPTS,
    max_parallel: int = 4,
    generate_only: bool = False,
    cost_tracker: Optional[CostTracker] = None,
    per_module_usd_cap: float = DEFAULT_PER_MODULE_USD_CAP,
) -> Dict[str, Any]:
    """Main orchestration: generate and optionally execute E2E tests.

    Mirrors run_e2e_validation from adw_e2e_validation_iso.py but uses
    the generic /write_e2e_test skill and works with any manifest source.
    Threads a CostTracker through every agent call and enforces a
    per-module USD cap on the retry/resolve loop.
    """
    if cost_tracker is None:
        cost_tracker = CostTracker()
        owns_tracker = True
    else:
        owns_tracker = False

    result: Dict[str, Any] = {
        "adw_id": adw_id,
        "source": manifest.get("source", "unknown"),
        "audiences": [],
        "module_results": [],
        "total_passed": 0,
        "total_failed": 0,
        "total_skipped": 0,
    }

    audience_groups = group_manifest_modules_by_audience(manifest)

    if not audience_groups:
        logger.info("No UI modules found in manifest — nothing to generate")
        return result

    audiences_found = ", ".join(
        f"{a} ({len(mods)} modules)" for a, mods in audience_groups.items()
    )
    logger.info(f"Manifest audiences: {audiences_found}")

    # Prepare app (unless generate-only)
    if not generate_only:
        try:
            sys.path.insert(0, os.path.join(working_dir, "adws"))
            from adw_modules.utils import is_chrome_available
            available, reason = is_chrome_available()
            if not available:
                logger.warning(f"Chrome not available: {reason}. Will generate only.")
                generate_only = True
        except ImportError:
            pass

        if not generate_only:
            logger.info("Preparing application for E2E testing...")
            prepare_request = AgentTemplateRequest(
                agent_name=AGENT_APP_PREPARER,
                slash_command="/prepare_app",
                args=[],
                adw_id=adw_id,
                working_dir=working_dir,
            )
            prepare_response = execute_template(prepare_request)
            cost_tracker.record_from_template_request(
                adw_id, AGENT_APP_PREPARER, bucket="prepare_app", logger=logger,
            )
            if not prepare_response.success:
                logger.warning(f"App preparation may have failed: {prepare_response.output[:300]}")

    generated_files: List[str] = []

    for audience in TARGET_AUDIENCES_WITH_UI:
        if audience not in audience_groups:
            continue

        modules = audience_groups[audience]
        label = AUDIENCE_LABELS.get(audience, audience)

        print(f"\n  === E2E Generation: {label} ({len(modules)} modules) ===")
        logger.info(f"E2E generation for {audience}: {len(modules)} modules")

        # Parallel generation
        generation_results: Dict[str, Tuple[str, str, bool, str]] = {}

        print(f"  Generating tests ({max_parallel} parallel)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as executor:
            future_to_module: Dict[concurrent.futures.Future, Tuple[Dict, int, str, str, str]] = {}

            for idx, module in enumerate(modules):
                module_id = module.get("id", f"module-{idx}")
                spec_path, test_path = get_e2e_gen_module_output_paths(
                    adw_id, audience, module_id, idx, working_dir,
                )
                future = executor.submit(
                    generate_e2e_test_generic,
                    manifest_path, audience, spec_path, test_path,
                    adw_id, working_dir, logger, module_id, cost_tracker,
                )
                future_to_module[future] = (module, idx, module_id, spec_path, test_path)

            for future in concurrent.futures.as_completed(future_to_module):
                module, idx, module_id, spec_path, test_path = future_to_module[future]
                module_name = module.get("name", module_id)
                try:
                    gen_success, gate_summary = future.result()
                    generation_results[module_id] = (spec_path, test_path, gen_success, gate_summary)
                    status = "generated" if gen_success else "FAILED"
                    print(f"    [{status}] {module_name} — {gate_summary}")
                except Exception as e:
                    logger.exception(f"Generation error for {module_id}")
                    generation_results[module_id] = (spec_path, test_path, False, f"exception: {e}")
                    print(f"    [ERROR] {module_name}: {e}")

        # Sequential execution (unless generate-only)
        audience_module_results: List[Dict[str, Any]] = []

        for idx, module in enumerate(modules):
            module_id = module.get("id", f"module-{idx}")
            module_name = module.get("name", module_id)
            spec_path, test_path, gen_success, gate_summary = generation_results.get(
                module_id, ("", "", False, "no result")
            )

            module_result: Dict[str, Any] = {
                "module_id": module_id,
                "module_name": module_name,
                "target_audience": audience,
                "test_spec_path": None,
                "test_file_path": None,
                "total_attempts": 0,
                "passed": False,
                "defects": [],
                "error": None,
                "generation_gate": gate_summary,
            }

            if not gen_success:
                module_result["error"] = (
                    f"Test generation failed for {module_name}: {gate_summary}"
                )
                result["total_skipped"] += 1
                audience_module_results.append(module_result)
                result["module_results"].append(module_result)
                print(f"    {module_name}: SKIPPED ({gate_summary})")
                continue

            module_result["test_file_path"] = test_path
            generated_files.append(test_path)
            if os.path.exists(spec_path):
                module_result["test_spec_path"] = spec_path
                generated_files.append(spec_path)

            if generate_only:
                module_result["passed"] = True  # Mark as passed since we're not executing
                result["total_passed"] += 1
                audience_module_results.append(module_result)
                result["module_results"].append(module_result)
                print(f"    {module_name}: GENERATED (execution skipped)")
                continue

            # Retry loop per module — bounded by attempts AND per-module $ cap
            for attempt in range(1, max_attempts + 1):
                if cost_tracker.bucket_exceeds(module_id, max_usd=per_module_usd_cap):
                    bucket = cost_tracker.bucket_total(module_id)
                    spent = bucket.cost_usd if bucket else 0.0
                    module_result["defects"].append(
                        f"Per-module USD cap ${per_module_usd_cap:.2f} reached "
                        f"(spent ${spent:.2f}); halting retries for {module_name}"
                    )
                    print(f"      Cap reached (${spent:.2f}/${per_module_usd_cap:.2f}) — halting")
                    break

                module_result["total_attempts"] = attempt
                print(f"    {module_name}: attempt {attempt}/{max_attempts}...", end=" ", flush=True)
                logger.info(f"E2E attempt {attempt}/{max_attempts} for {audience}/{module_id}")

                passed, error_msg = execute_e2e_test(
                    test_path, adw_id, audience, working_dir, logger,
                )

                if passed:
                    module_result["passed"] = True
                    print("PASSED")
                    logger.info(f"E2E PASSED for {audience}/{module_id} on attempt {attempt}")
                    break

                print("FAILED")
                logger.warning(f"E2E failed for {audience}/{module_id} (attempt {attempt}): {error_msg}")

                if attempt == max_attempts:
                    module_result["defects"].append(
                        f"E2E test failed after {max_attempts} attempts for {module_name}. "
                        f"Last error: {error_msg}"
                    )
                    print(f"      Exhausted all {max_attempts} attempts")
                    break

                print(f"      Resolving...", end=" ", flush=True)
                resolved, _ = resolve_e2e_failure(
                    test_path, error_msg or "Unknown error",
                    adw_id, audience, attempt, working_dir, logger,
                    cost_tracker=cost_tracker, cost_bucket=module_id,
                )

                if not resolved:
                    module_result["defects"].append(
                        f"Could not resolve E2E failure for {module_name} (attempt {attempt}). "
                        f"Error: {error_msg}"
                    )
                    print("no progress — stopping retries")
                    break

                print("resolved — retrying")

            if module_result["passed"]:
                result["total_passed"] += 1
            elif not module_result.get("error"):
                result["total_failed"] += 1

            audience_module_results.append(module_result)
            result["module_results"].append(module_result)

        result["audiences"].append({
            "target_audience": audience,
            "modules": audience_module_results,
            "passed": sum(1 for m in audience_module_results if m["passed"]),
            "failed": sum(1 for m in audience_module_results if not m["passed"] and not m.get("error")),
            "skipped": sum(1 for m in audience_module_results if m.get("error")),
        })

    # Commit all generated test files
    if generated_files:
        print(f"\n  Committing {len(generated_files)} E2E test artifact(s) to main...")
        commit_e2e_artifacts(
            generated_files, adw_id,
            f"test: add E2E tests for {adw_id}",
            working_dir, logger,
        )

    # Defect report
    failed_modules = [m for m in result["module_results"] if not m.get("passed") and m.get("defects")]
    if failed_modules:
        report_dir = os.path.join(working_dir, "specs", "e2e_gen", adw_id)
        os.makedirs(report_dir, exist_ok=True)
        defect_path = build_defect_report(
            result["module_results"], adw_id, working_dir, logger,
        )
        if defect_path:
            commit_e2e_artifacts(
                [defect_path], adw_id,
                f"docs: add E2E defect report for {adw_id}",
                working_dir, logger,
            )

    # Cost summary
    cost_summary_path = os.path.join(
        working_dir, "specs", "e2e_gen", adw_id, "cost_summary.json",
    )
    try:
        cost_tracker.write_summary(cost_summary_path, adw_id)
        result["cost_summary_path"] = cost_summary_path
        result["cost"] = cost_tracker.grand_total().to_dict()
    except Exception as e:
        logger.warning(f"Failed to write cost summary: {e}")

    if owns_tracker:
        cost_tracker.print_summary(header=f"E2E Generation Cost Summary ({adw_id})")

    return result


def print_summary(result: Dict[str, Any]) -> None:
    """Print human-readable summary of E2E generation results."""
    module_results = result.get("module_results", [])
    if not module_results:
        print("\n  No E2E tests were generated.")
        return

    total_passed = result.get("total_passed", 0)
    total_failed = result.get("total_failed", 0)
    total_skipped = result.get("total_skipped", 0)
    source = result.get("source", "unknown")

    print(f"\n--- E2E Generation Summary (source: {source}) ---")
    print(f"  Passed: {total_passed}  Failed: {total_failed}  Skipped: {total_skipped}")

    for audience_data in result.get("audiences", []):
        audience = audience_data.get("target_audience", "?")
        label = AUDIENCE_LABELS.get(audience, audience)
        a_passed = audience_data.get("passed", 0)
        a_failed = audience_data.get("failed", 0)
        a_skipped = audience_data.get("skipped", 0)
        print(f"\n  {label}: {a_passed} passed, {a_failed} failed, {a_skipped} skipped")

        for m in audience_data.get("modules", []):
            module_name = m.get("module_name", m.get("module_id", "?"))
            if m.get("error"):
                status = "SKIP"
            elif m.get("passed"):
                status = "PASS"
            else:
                status = "FAIL"

            attempts = m.get("total_attempts", 0)
            defect_count = len(m.get("defects", []))
            print(f"    [{status}] {module_name}: {attempts} attempt(s), {defect_count} defect(s)")

            if m.get("test_file_path"):
                print(f"           Test: {m['test_file_path']}")

            for defect in m.get("defects", []):
                msg = defect[:200] + "..." if len(defect) > 200 else defect
                print(f"           Defect: {msg}")

    if total_failed > 0:
        print(f"\n  Advisory: {total_failed} module(s) have unresolved E2E defects.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for standalone execution."""
    load_dotenv()

    # Defaults
    max_attempts = MAX_E2E_ATTEMPTS
    max_parallel = 4
    # Default to repo root (parent of adws/), not cwd — Playwright config,
    # node_modules, and fixtures live under app/frontend/ in the repo root.
    working_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    adw_id = ""
    spec_dir: Optional[str] = None
    manifest_path: Optional[str] = None
    discover_mode = False
    from_specs_dir: Optional[str] = None
    generate_only = False

    # Parse flags
    args = sys.argv[1:]
    positional_args: List[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--working-dir" and i + 1 < len(args):
            working_dir = args[i + 1]
            i += 2
        elif args[i] == "--max-attempts" and i + 1 < len(args):
            max_attempts = int(args[i + 1])
            i += 2
        elif args[i] == "--max-parallel" and i + 1 < len(args):
            max_parallel = int(args[i + 1])
            i += 2
        elif args[i] == "--adw-id" and i + 1 < len(args):
            adw_id = args[i + 1]
            i += 2
        elif args[i] == "--spec-dir" and i + 1 < len(args):
            spec_dir = args[i + 1]
            i += 2
        elif args[i] == "--manifest" and i + 1 < len(args):
            manifest_path = args[i + 1]
            i += 2
        elif args[i] == "--from-specs" and i + 1 < len(args):
            from_specs_dir = args[i + 1]
            i += 2
        elif args[i] == "--discover":
            discover_mode = True
            i += 1
        elif args[i] == "--generate-only":
            generate_only = True
            i += 1
        elif args[i] == "--help":
            print(__doc__)
            sys.exit(0)
        else:
            positional_args.append(args[i])
            i += 1

    if not adw_id:
        adw_id = generate_adw_id()

    # Setup
    logger = setup_logger(adw_id, "adw_e2e_gen_iso")
    logger.info(f"Starting E2E Generation — ADW: {adw_id}")
    check_env_vars(logger)

    # Determine mode and build manifest
    manifest: Optional[Dict[str, Any]] = None
    manifest_file: Optional[str] = None

    if discover_mode:
        # --discover mode: run discovery agent
        print(f"E2E Generation — Discovery Mode — ADW: {adw_id}")
        manifest = run_discovery(working_dir, adw_id, spec_dir, logger)
        if manifest:
            manifest_file = os.path.join(
                working_dir, "specs", "e2e_gen", adw_id, "manifest.json"
            )

    elif from_specs_dir:
        # --from-specs mode: build manifest from .md specs
        print(f"E2E Generation — From Specs ({from_specs_dir}) — ADW: {adw_id}")
        abs_spec_dir = os.path.join(working_dir, from_specs_dir) if not os.path.isabs(from_specs_dir) else from_specs_dir
        manifest = build_manifest_from_specs(abs_spec_dir, working_dir)
        # Write manifest for the generator agent to read
        manifest_file = os.path.join(
            working_dir, "specs", "e2e_gen", adw_id, "manifest.json"
        )
        os.makedirs(os.path.dirname(manifest_file), exist_ok=True)
        with open(manifest_file, "w") as f:
            json.dump(manifest, f, indent=2)
        logger.info(f"Manifest written to {manifest_file}")

    elif manifest_path:
        # --manifest mode: use pre-built manifest
        print(f"E2E Generation — Manifest Mode ({manifest_path}) — ADW: {adw_id}")
        abs_path = os.path.join(working_dir, manifest_path) if not os.path.isabs(manifest_path) else manifest_path
        with open(abs_path, "r") as f:
            manifest = json.load(f)
        manifest_file = abs_path

    elif len(positional_args) >= 2:
        # Backward compat: <decomposition.json> <adw_id>
        from adw_e2e_validation_iso import run_e2e_validation, print_e2e_validation_summary
        decomp_path = positional_args[0]
        adw_id = positional_args[1]
        print(f"E2E Generation — Greenfield Compat Mode — ADW: {adw_id}")
        result = run_e2e_validation(
            decomposition_path=decomp_path,
            adw_id=adw_id,
            working_dir=working_dir,
            logger=logger,
            max_attempts=max_attempts,
            max_parallel_generation=max_parallel,
        )
        print_e2e_validation_summary(result)
        sys.exit(0)

    else:
        print(__doc__)
        sys.exit(0)

    if not manifest or not manifest.get("modules"):
        print("No modules found. Nothing to generate.")
        sys.exit(0)

    module_count = len(manifest["modules"])
    print(f"Manifest: {module_count} modules")
    print(f"Max attempts per module: {max_attempts}, Parallel generation: {max_parallel}")
    if generate_only:
        print("Mode: generate-only (no test execution)")

    # Run the pipeline
    result = run_e2e_gen(
        manifest=manifest,
        adw_id=adw_id,
        working_dir=working_dir,
        logger=logger,
        manifest_path=manifest_file,
        max_attempts=max_attempts,
        max_parallel=max_parallel,
        generate_only=generate_only,
    )

    print_summary(result)

    # Write result JSON
    result_dir = os.path.join(working_dir, "specs", "e2e_gen", adw_id)
    os.makedirs(result_dir, exist_ok=True)
    result_path = os.path.join(result_dir, "e2e_gen_result.json")
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    logger.info(f"Result written to {result_path}")

    # Advisory — always exit 0
    sys.exit(0)


if __name__ == "__main__":
    main()
