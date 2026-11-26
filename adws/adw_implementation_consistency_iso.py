#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW Implementation Consistency - Parallel code review against context documentation

Usage:
  uv run adw_implementation_consistency_iso.py [--parallel <n>] [--area <specific-area>] [--heavy | --superheavy] [--issue <number>]

Options:
  --parallel <n>     Number of parallel agents (default: 3)
  --area <path>      Review a specific area only (e.g., "backend/context/crud.md")
  --heavy            Use heavy model set (opus 4.6) for thorough analysis
  --superheavy       Use superheavy model set (opus 4.7) for the most thorough analysis
  --issue <number>   Post summary to GitHub issue as a comment

Workflow:
1. Discover all context documents and map them to code areas
2. Launch parallel agents to review each area
3. Each agent runs /review_consistency for their assigned area
4. Aggregate results into a comprehensive report
5. Generate action items and recommendations

The workflow reports on:
- Pattern violations (deviations from documented conventions)
- Antipatterns (common bad practices)
- Dead code (unused imports, functions, commented code)
- Duplicate code (copy-paste violations)
- Documentation drift (docs that don't match implementation)
"""

import sys
import os
import re
import uuid
import logging
import concurrent.futures
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv

from adw_modules.state import ADWState
from adw_modules.utils import setup_logger
from adw_modules.data_types import AgentTemplateRequest
from adw_modules.agent import execute_template
from adw_modules.github import make_issue_comment

# Constants
AI_DOCS_DIR = "ai_docs"
AGENT_NAME_PREFIX = "consistency_reviewer"
REPORT_DIR = "app_docs/consistency_reports"

# Mapping of context files to code directories they document
CONTEXT_TO_CODE_MAP = {
    # Backend context files
    "backend/context/api.md": "app/backend/src/api",
    "backend/context/crud.md": "app/backend/src/crud",
    "backend/context/models.md": "app/backend/src/models",
    "backend/context/serializers.md": "app/backend/src/serialisers",
    "backend/context/auth.md": "app/backend/src/api",
    "backend/context/multitenancy.md": "app/backend/src/crud",
    "backend/context/testing.md": "app/backend/tests",
    "backend/context/caching.md": "app/backend/src/services",
    "backend/context/background_jobs.md": "app/backend/src/workers",
    "backend/context/permissions.md": "app/backend/src/api",
    "backend/context/notifications.md": "app/backend/src/services",
    "backend/context/files.md": "app/backend/src/services",
    "backend/context/cron_scheduler.md": "app/backend/src/cron",
    # Frontend context files
    "frontend/context/auth.md": "app/frontend/src/features/auth",
    "frontend/context/components.md": "app/frontend/src/components",
    "frontend/context/forms.md": "app/frontend/src/components",
    "frontend/context/routing.md": "app/frontend/src/routes",
    "frontend/context/state.md": "app/frontend/src/store",
    "frontend/context/styling.md": "app/frontend/src",
    "frontend/context/testing.md": "app/frontend/src",
    "frontend/context/i18n.md": "app/frontend/src/i18n",
    "frontend/context/permissions.md": "app/frontend/src/features",
}


@dataclass
class ReviewArea:
    """Represents an area to review."""

    context_file: str  # Relative path from ai_docs/
    code_directory: str  # Code directory to review
    status: str = "pending"
    agent_id: Optional[str] = None
    report_path: Optional[str] = None  # Path to generated markdown report
    error: Optional[str] = None


def generate_agent_id() -> str:
    """Generate a unique agent ID."""
    return f"agent-{uuid.uuid4().hex[:4]}"


def discover_review_areas(working_dir: str) -> List[ReviewArea]:
    """Discover all areas that need to be reviewed.

    Args:
        working_dir: Working directory

    Returns:
        List of ReviewArea objects representing areas to review
    """
    areas = []
    ai_docs_path = Path(working_dir) / AI_DOCS_DIR

    for context_rel, code_dir in CONTEXT_TO_CODE_MAP.items():
        context_path = ai_docs_path / context_rel
        code_path = Path(working_dir) / code_dir

        # Only add if both context file and code directory exist
        if context_path.exists() and code_path.exists():
            areas.append(
                ReviewArea(
                    context_file=f"{AI_DOCS_DIR}/{context_rel}",
                    code_directory=code_dir,
                )
            )

    return areas


def get_report_path(context_file: str, working_dir: str) -> str:
    """Get the expected report path for a context file.

    Args:
        context_file: Path like "ai_docs/backend/context/crud.md"
        working_dir: Working directory

    Returns:
        Path like "consistency_review/backend_crud.md"
    """
    # Extract area (backend/frontend) and filename
    # ai_docs/backend/context/crud.md -> backend_crud.md
    parts = context_file.replace("ai_docs/", "").split("/")
    area = parts[0]  # backend or frontend
    filename = parts[-1].replace(".md", "")  # crud
    report_name = f"{area}_{filename}.md"
    return str(Path(working_dir) / "consistency_review" / report_name)


def run_consistency_review(
    area: ReviewArea,
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Run consistency review for a single area.

    Args:
        area: The review area to process
        adw_id: ADW workflow ID
        working_dir: Working directory
        logger: Logger instance

    Returns:
        Tuple of (success, report_path, error_message)
    """
    agent_name = f"{AGENT_NAME_PREFIX}_{area.context_file.replace('/', '_').replace('.', '_')}"

    # Build args for the /review_consistency command
    # Include explicit output path to ensure consistent naming
    output_path = get_report_path(area.context_file, working_dir)
    args = [
        area.context_file,
        area.code_directory,
        output_path,
        adw_id,
        agent_name,
    ]

    request = AgentTemplateRequest(
        agent_name=agent_name,
        slash_command="/review_consistency",
        args=args,
        adw_id=adw_id,
        working_dir=working_dir,
    )

    logger.info(f"Starting review of {area.context_file} -> {area.code_directory}")

    try:
        response = execute_template(request)

        if not response.success:
            logger.error(f"Review failed for {area.context_file}: {response.output}")
            return False, None, response.output[:200]

        # Agent should respond with "DONE" - check for report file
        report_path = get_report_path(area.context_file, working_dir)
        if Path(report_path).exists():
            logger.info(f"Report generated: {report_path}")
            return True, report_path, None
        else:
            # Check if agent indicated completion
            if "DONE" in response.output:
                return False, None, "Agent completed but report file not found"
            return False, None, f"Report not generated: {response.output[:100]}"

    except Exception as e:
        logger.exception(f"Error reviewing {area.context_file}")
        return False, None, str(e)[:200]


def review_area_worker(
    area: ReviewArea,
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> ReviewArea:
    """Worker function for parallel review execution.

    Args:
        area: The review area to process
        adw_id: ADW workflow ID
        working_dir: Working directory
        logger: Logger instance

    Returns:
        Updated ReviewArea with results
    """
    area.agent_id = generate_agent_id()
    area.status = "in_progress"

    success, report_path, error = run_consistency_review(area, adw_id, working_dir, logger)

    if success and report_path:
        area.status = "completed"
        area.report_path = report_path
    else:
        area.status = "failed"
        area.error = error

    return area


@dataclass
class ReportSummary:
    """Summary extracted from a markdown report."""

    context_file: str
    code_directory: str
    report_path: str
    compliance_score: Optional[int] = None
    files_analyzed: Optional[int] = None
    summary_text: str = ""
    has_violations: bool = False
    error: Optional[str] = None


def parse_report_summary(report_path: str, area: ReviewArea) -> ReportSummary:
    """Parse a markdown report to extract summary information.

    Only reads the first ~3KB of the file where metadata is located,
    avoiding loading large reports entirely into memory.

    Args:
        report_path: Path to the markdown report
        area: The ReviewArea for context

    Returns:
        ReportSummary with extracted data
    """
    result = ReportSummary(
        context_file=area.context_file,
        code_directory=area.code_directory,
        report_path=report_path,
    )

    try:
        # Only read first 3KB - metadata and summary are at the top
        with open(report_path, 'r') as f:
            header = f.read(3072)

        # Extract compliance score (e.g., "**Compliance Score:** 85%")
        score_match = re.search(r'\*\*Compliance Score:\*\*\s*(\d+)%', header)
        if score_match:
            result.compliance_score = int(score_match.group(1))

        # Extract files analyzed (e.g., "**Files Analyzed:** 12")
        files_match = re.search(r'\*\*Files Analyzed:\*\*\s*(\d+)', header)
        if files_match:
            result.files_analyzed = int(files_match.group(1))

        # Extract summary section (usually right after metadata)
        summary_match = re.search(r'## Summary\s*\n\s*\n(.+?)(?:\n\n---|\n\n##)', header, re.DOTALL)
        if summary_match:
            result.summary_text = summary_match.group(1).strip()[:200]

        # Quick check for violations by scanning for section headers
        # We just need to know if they exist, not their content
        result.has_violations = (
            '## Pattern Violations' in header or
            '## Antipatterns' in header
        )

    except Exception as e:
        result.error = str(e)[:100]

    return result


def generate_summary_report(
    areas: List[ReviewArea],
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> str:
    """Generate a summary table from all consistency review reports.

    Args:
        areas: List of reviewed areas with report paths
        adw_id: ADW workflow ID
        working_dir: Working directory
        logger: Logger instance

    Returns:
        Path to the generated summary file
    """
    # Ensure consistency_review directory exists
    review_dir = Path(working_dir) / "consistency_review"
    review_dir.mkdir(parents=True, exist_ok=True)

    summary_file = review_dir / "SUMMARY.md"

    # Parse all reports
    summaries: List[ReportSummary] = []
    for area in areas:
        if area.report_path and Path(area.report_path).exists():
            summary = parse_report_summary(area.report_path, area)
            summaries.append(summary)
        elif area.error:
            summaries.append(ReportSummary(
                context_file=area.context_file,
                code_directory=area.code_directory,
                report_path="",
                error=area.error,
            ))

    # Calculate overall stats
    scores = [s.compliance_score for s in summaries if s.compliance_score is not None]
    avg_score = sum(scores) // len(scores) if scores else 0
    total_files = sum(s.files_analyzed or 0 for s in summaries)
    areas_with_violations = sum(1 for s in summaries if s.has_violations)

    lines = [
        "# Consistency Review Summary",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**ADW ID:** {adw_id}",
        "",
        "---",
        "",
        "## Overview",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Average Compliance Score | **{avg_score}%** |",
        f"| Areas Reviewed | {len(summaries)} |",
        f"| Total Files Analyzed | {total_files} |",
        f"| Areas with Violations | {areas_with_violations} |",
        "",
        "---",
        "",
        "## Area Reports",
        "",
        "| Area | Code Directory | Score | Files | Status | Report |",
        "|------|----------------|-------|-------|--------|--------|",
    ]

    for s in summaries:
        if s.error:
            status = "❌ Error"
            score_str = "-"
            files_str = "-"
            report_link = "-"
        else:
            if s.compliance_score is not None:
                if s.compliance_score >= 90:
                    status = "🟢 Good"
                elif s.compliance_score >= 70:
                    status = "🟡 Fair"
                else:
                    status = "🔴 Needs Work"
                score_str = f"{s.compliance_score}%"
            else:
                status = "⚪ Unknown"
                score_str = "-"
            files_str = str(s.files_analyzed) if s.files_analyzed else "-"
            # Make relative path for link
            rel_path = Path(s.report_path).name if s.report_path else ""
            report_link = f"[View]({rel_path})" if rel_path else "-"

        # Shorten context file for display
        area_name = s.context_file.replace("ai_docs/", "").replace("/context/", "/")

        lines.append(
            f"| `{area_name}` | `{s.code_directory}` | {score_str} | {files_str} | {status} | {report_link} |"
        )

    # Add summaries section
    lines.extend([
        "",
        "---",
        "",
        "## Summaries",
        "",
    ])

    for s in summaries:
        if s.summary_text:
            area_name = s.context_file.replace("ai_docs/", "").replace("/context/", "/")
            lines.extend([
                f"### {area_name}",
                "",
                s.summary_text,
                "",
            ])
        elif s.error:
            area_name = s.context_file.replace("ai_docs/", "").replace("/context/", "/")
            lines.extend([
                f"### {area_name}",
                "",
                f"**Error:** {s.error}",
                "",
            ])

    lines.extend([
        "---",
        "",
        f"*Generated by ADW Implementation Consistency Workflow ({adw_id})*",
    ])

    # Write summary
    summary_content = "\n".join(lines)
    summary_file.write_text(summary_content)
    logger.info(f"Summary written to: {summary_file}")

    return str(summary_file)


def format_github_comment(
    areas: List[ReviewArea],
    adw_id: str,
    summary_path: str,
) -> str:
    """Format the consistency review results as a GitHub comment.

    Args:
        areas: List of reviewed areas with results
        adw_id: ADW workflow ID
        summary_path: Path to the full summary file

    Returns:
        Formatted markdown string for GitHub comment
    """
    # Parse summaries from completed areas
    summaries: List[ReportSummary] = []
    for area in areas:
        if area.report_path and Path(area.report_path).exists():
            summary = parse_report_summary(area.report_path, area)
            summaries.append(summary)
        elif area.error:
            summaries.append(ReportSummary(
                context_file=area.context_file,
                code_directory=area.code_directory,
                report_path="",
                error=area.error,
            ))

    # Calculate stats
    scores = [s.compliance_score for s in summaries if s.compliance_score is not None]
    avg_score = sum(scores) // len(scores) if scores else 0
    total_files = sum(s.files_analyzed or 0 for s in summaries)
    areas_with_violations = sum(1 for s in summaries if s.has_violations)
    completed_count = sum(1 for a in areas if a.status == "completed")
    failed_count = sum(1 for a in areas if a.status == "failed")

    # Build concise comment
    lines = [
        "## Consistency Review Complete",
        "",
        f"**ADW ID:** `{adw_id}`",
        "",
        "### Overview",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Average Compliance Score | **{avg_score}%** |",
        f"| Areas Reviewed | {completed_count} |",
        f"| Areas Failed | {failed_count} |",
        f"| Total Files Analyzed | {total_files} |",
        f"| Areas with Violations | {areas_with_violations} |",
        "",
        "### Results by Area",
        "",
        "| Area | Score | Status |",
        "|------|-------|--------|",
    ]

    for s in summaries:
        area_name = s.context_file.replace("ai_docs/", "").replace("/context/", "/")
        if s.error:
            lines.append(f"| `{area_name}` | - | :x: Error |")
        elif s.compliance_score is not None:
            if s.compliance_score >= 90:
                status = ":white_check_mark: Good"
            elif s.compliance_score >= 70:
                status = ":warning: Fair"
            else:
                status = ":red_circle: Needs Work"
            lines.append(f"| `{area_name}` | {s.compliance_score}% | {status} |")
        else:
            lines.append(f"| `{area_name}` | - | :white_circle: Unknown |")

    lines.extend([
        "",
        f"Full reports available in `consistency_review/` directory.",
        "",
        f"*Generated by ADW Implementation Consistency Workflow*",
    ])

    return "\n".join(lines)


def main():
    """Main entry point."""
    load_dotenv()

    # Parse arguments
    parallel_count = 3
    specific_area = None
    use_superheavy = "--superheavy" in sys.argv
    use_heavy = "--heavy" in sys.argv and not use_superheavy

    if use_superheavy:
        model_set = "superheavy"
    elif use_heavy:
        model_set = "heavy"
    else:
        model_set = "base"

    if "--parallel" in sys.argv:
        idx = sys.argv.index("--parallel")
        if idx + 1 < len(sys.argv):
            try:
                parallel_count = int(sys.argv[idx + 1])
            except ValueError:
                pass

    if "--area" in sys.argv:
        idx = sys.argv.index("--area")
        if idx + 1 < len(sys.argv):
            specific_area = sys.argv[idx + 1]

    issue_number = None
    if "--issue" in sys.argv:
        idx = sys.argv.index("--issue")
        if idx + 1 < len(sys.argv):
            issue_number = sys.argv[idx + 1]

    # Setup
    working_dir = os.getcwd()
    adw_id = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
    logger = setup_logger(adw_id, "adw_consistency")

    logger.info(f"ADW Implementation Consistency starting - ID: {adw_id}")
    logger.info(f"Parallel agents: {parallel_count}, Model set: {model_set}")

    # Initialize state
    state = ADWState(adw_id)
    state.update(
        model_set=model_set,
        parallel_count=parallel_count,
    )
    state.save("adw_implementation_consistency_init")

    _model_set_label = {
        "base": "base (sonnet)",
        "heavy": "heavy (opus 4.6)",
        "superheavy": "superheavy (opus 4.7)",
    }[model_set]
    print(f"\n{'='*60}")
    print(f"Implementation Consistency Review")
    print(f"ADW ID: {adw_id}")
    print(f"Parallel Agents: {parallel_count}")
    print(f"Model Set: {_model_set_label}")
    print(f"{'='*60}\n")

    # Discover areas to review
    areas = discover_review_areas(working_dir)

    if specific_area:
        # Filter to specific area
        areas = [a for a in areas if specific_area in a.context_file]
        if not areas:
            print(f"Error: No matching area found for '{specific_area}'")
            sys.exit(1)

    if not areas:
        print("No review areas found. Ensure ai_docs/ context files exist.")
        sys.exit(1)

    print(f"Discovered {len(areas)} areas to review:\n")
    for area in areas:
        print(f"  📄 {area.context_file}")
        print(f"     → {area.code_directory}")

    print(f"\n{'='*60}")
    print("Starting parallel reviews...")
    print(f"{'='*60}\n")

    # Run reviews in parallel
    completed_areas = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallel_count) as executor:
        future_to_area = {
            executor.submit(
                review_area_worker, area, adw_id, working_dir, logger
            ): area
            for area in areas
        }

        for future in concurrent.futures.as_completed(future_to_area):
            original_area = future_to_area[future]
            try:
                result_area = future.result()
                completed_areas.append(result_area)

                if result_area.status == "completed":
                    print(f"✅ {result_area.context_file}: Report generated")
                else:
                    print(f"❌ {result_area.context_file}: {result_area.error}")

            except Exception as e:
                logger.exception(f"Error processing {original_area.context_file}")
                original_area.status = "failed"
                original_area.error = str(e)
                completed_areas.append(original_area)
                print(f"❌ {original_area.context_file}: {e}")

    # Generate summary from individual reports
    print(f"\n{'='*60}")
    print("Generating summary...")
    print(f"{'='*60}\n")

    summary_path = generate_summary_report(completed_areas, adw_id, working_dir, logger)

    # Count completed vs failed
    completed_count = sum(1 for a in completed_areas if a.status == "completed")
    failed_count = sum(1 for a in completed_areas if a.status == "failed")

    # Print summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"\nAreas Reviewed:    {completed_count}")
    print(f"Areas Failed:      {failed_count}")
    print(f"\n📝 Summary Report: {summary_path}")
    print(f"📂 Individual Reports: consistency_review/")
    print(f"{'='*60}\n")

    # Post to GitHub issue if specified
    if issue_number:
        print(f"Posting summary to GitHub issue #{issue_number}...")
        try:
            comment = format_github_comment(completed_areas, adw_id, summary_path)
            make_issue_comment(issue_number, comment)
            print(f"✅ Posted summary to issue #{issue_number}")
            logger.info(f"Posted summary to GitHub issue #{issue_number}")
        except Exception as e:
            print(f"❌ Failed to post to GitHub: {e}")
            logger.error(f"Failed to post to GitHub issue #{issue_number}: {e}")

    # Save final state
    state.update(
        completed=True,
        areas_reviewed=completed_count,
        report_path=summary_path,
        issue_number=issue_number,
    )
    state.save("adw_implementation_consistency_complete")


if __name__ == "__main__":
    main()
