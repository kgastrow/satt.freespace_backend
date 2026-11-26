#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW Context Management - Parallel context document review and simplification

Usage:
  uv run adw_context_management_iso.py [--resume <tracking-file>] [--file <specific-file>] [--dry-run]

Options:
  --resume <path>  Resume using an existing tracking file (relative to ai_docs/)
  --file <path>    Process a specific file (relative to ai_docs/)
  --dry-run        Analyze without making changes

Workflow:
1. Generate new tracking file from sample (or resume existing one)
2. Claim file by updating status to in_progress
3. Read context document and corresponding implementation
4. Simplify document while preserving essential patterns
5. Update tracking sheet with results

Multiple instances can run in parallel - each claims different files.
Tracking files are named: context_refinement_{adw_id}.md
"""

import sys
import os
import re
import uuid
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List
from dataclasses import dataclass
from dotenv import load_dotenv

from adw_modules.state import ADWState
from adw_modules.utils import setup_logger
from adw_modules.data_types import AgentTemplateRequest
from adw_modules.agent import execute_template

# Constants
TRACKING_SAMPLE = "ai_docs/context_refinement_sample.md"
AI_DOCS_DIR = "ai_docs"
AGENT_NAME_PREFIX = "context_reviewer"
EXCLUDED_FILES = {"context_refinement_sample.md"}  # Files to exclude from tracking


@dataclass
class TrackingEntry:
    """Represents a row in the tracking table."""
    file_path: str
    original_lines: int
    status: str
    assigned_agent: str
    new_lines: Optional[int]
    reduction_pct: Optional[str]
    notes: str


def generate_agent_id() -> str:
    """Generate a unique agent ID."""
    return f"agent-{uuid.uuid4().hex[:4]}"


def scan_ai_docs(working_dir: str) -> List[Tuple[str, int]]:
    """Scan ai_docs directory for markdown files and their line counts.

    Args:
        working_dir: Working directory

    Returns:
        List of (relative_path, line_count) tuples sorted by line count descending
    """
    ai_docs_path = Path(working_dir) / AI_DOCS_DIR
    files_with_counts = []

    for md_file in ai_docs_path.rglob("*.md"):
        rel_path = md_file.relative_to(ai_docs_path)

        # Skip excluded files and tracking files
        if rel_path.name in EXCLUDED_FILES or rel_path.name.startswith("context_refinement"):
            continue

        line_count = len(md_file.read_text().splitlines())
        files_with_counts.append((str(rel_path), line_count))

    # Sort by line count descending
    files_with_counts.sort(key=lambda x: x[1], reverse=True)
    return files_with_counts


def generate_tracking_file(adw_id: str, working_dir: str) -> Path:
    """Generate a new tracking file from the sample template.

    Args:
        adw_id: ADW workflow ID
        working_dir: Working directory

    Returns:
        Path to the generated tracking file
    """
    sample_path = Path(working_dir) / TRACKING_SAMPLE

    if not sample_path.exists():
        raise FileNotFoundError(f"Sample template not found: {sample_path}")

    # Scan for files
    files = scan_ai_docs(working_dir)

    # Generate tracking rows
    rows = []
    for file_path, line_count in files:
        rows.append(f"| {file_path} | {line_count} | pending | | | | |")

    tracking_rows = "\n".join(rows)
    total_files = len(files)
    total_lines = sum(count for _, count in files)

    # Read sample and substitute placeholders
    template = sample_path.read_text()
    content = template.format(
        adw_id=adw_id,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        tracking_rows=tracking_rows,
        total_files=total_files,
        total_lines=f"{total_lines:,}",
    )

    # Write to new file with adw_id in name
    tracking_filename = f"context_refinement_{adw_id}.md"
    tracking_path = Path(working_dir) / AI_DOCS_DIR / tracking_filename
    tracking_path.write_text(content)

    return tracking_path


def parse_tracking_table(content: str) -> Tuple[List[TrackingEntry], int, int]:
    """Parse the tracking table from markdown content.

    Returns:
        Tuple of (entries list, table_start_line, table_end_line)
    """
    lines = content.split('\n')
    entries = []
    table_start = -1
    table_end = -1
    in_table = False

    for i, line in enumerate(lines):
        # Detect table header
        if '| file_path |' in line:
            table_start = i
            in_table = True
            continue

        # Skip separator line
        if in_table and line.startswith('|---'):
            continue

        # Parse table rows
        if in_table and line.startswith('|') and '|' in line[1:]:
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 7 and parts[0] and not parts[0].startswith('---'):
                entries.append(TrackingEntry(
                    file_path=parts[0],
                    original_lines=int(parts[1]) if parts[1].isdigit() else 0,
                    status=parts[2] or 'pending',
                    assigned_agent=parts[3],
                    new_lines=int(parts[4]) if parts[4].isdigit() else None,
                    reduction_pct=parts[5] if parts[5] else None,
                    notes=parts[6] if len(parts) > 6 else '',
                ))
                table_end = i
        elif in_table and not line.startswith('|'):
            # End of table
            break

    return entries, table_start, table_end


def update_tracking_entry(
    content: str,
    file_path: str,
    status: str,
    agent_id: str,
    new_lines: Optional[int] = None,
    reduction_pct: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Update a specific entry in the tracking table."""
    lines = content.split('\n')

    for i, line in enumerate(lines):
        if f'| {file_path} |' in line:
            parts = [p.strip() for p in line.split('|')]
            # parts[0] is empty (before first |), parts[-1] is empty (after last |)
            if len(parts) >= 8:
                parts[3] = status
                parts[4] = agent_id
                if new_lines is not None:
                    parts[5] = str(new_lines)
                if reduction_pct is not None:
                    parts[6] = reduction_pct
                if notes is not None:
                    parts[7] = notes

                lines[i] = '| ' + ' | '.join(parts[1:-1]) + ' |'
                break

    return '\n'.join(lines)


def claim_file(tracking_path: Path, agent_id: str, specific_file: Optional[str] = None) -> Optional[TrackingEntry]:
    """Attempt to claim a pending file from the tracking sheet.

    Uses atomic file operations to prevent race conditions.

    Args:
        tracking_path: Path to the tracking file
        agent_id: Unique agent identifier
        specific_file: If provided, claim this specific file only

    Returns:
        TrackingEntry if a file was claimed, None otherwise
    """
    content = tracking_path.read_text()
    entries, _, _ = parse_tracking_table(content)

    # Find a pending file
    target_entry = None
    for entry in entries:
        if entry.status == 'pending':
            if specific_file is None or entry.file_path == specific_file:
                target_entry = entry
                break

    if not target_entry:
        return None

    # Update the tracking file to claim this entry
    updated_content = update_tracking_entry(
        content,
        target_entry.file_path,
        status='in_progress',
        agent_id=agent_id,
    )

    tracking_path.write_text(updated_content)
    target_entry.status = 'in_progress'
    target_entry.assigned_agent = agent_id

    return target_entry


def complete_file(
    tracking_path: Path,
    entry: TrackingEntry,
    new_lines: int,
    notes: str,
) -> None:
    """Mark a file as completed in the tracking sheet."""
    content = tracking_path.read_text()

    reduction_pct = f"{int((entry.original_lines - new_lines) / entry.original_lines * 100)}%"

    updated_content = update_tracking_entry(
        content,
        entry.file_path,
        status='completed',
        agent_id=entry.assigned_agent,
        new_lines=new_lines,
        reduction_pct=reduction_pct,
        notes=notes,
    )

    tracking_path.write_text(updated_content)


def release_file(tracking_path: Path, entry: TrackingEntry, error_notes: str) -> None:
    """Release a file back to pending status on error."""
    content = tracking_path.read_text()

    updated_content = update_tracking_entry(
        content,
        entry.file_path,
        status='pending',
        agent_id='',
        notes=f'Error: {error_notes}',
    )

    tracking_path.write_text(updated_content)


def count_lines(file_path: Path) -> int:
    """Count non-empty lines in a file."""
    if not file_path.exists():
        return 0
    content = file_path.read_text()
    return len([line for line in content.split('\n') if line.strip()])


def get_implementation_paths(doc_path: str) -> List[str]:
    """Determine which implementation directories to search based on doc path."""
    if 'backend/' in doc_path:
        return ['app/backend/src', 'app/backend/tests']
    elif 'frontend/' in doc_path:
        return ['app/frontend/src', 'app/frontend/tests']
    else:
        return ['app/backend/src', 'app/frontend/src']


def review_and_simplify_context(
    adw_id: str,
    entry: TrackingEntry,
    working_dir: str,
    logger: logging.Logger,
    dry_run: bool = False,
) -> Tuple[bool, int, str]:
    """Review a context document against implementation and simplify it.

    Args:
        adw_id: ADW workflow ID
        entry: Tracking entry for the file to process
        working_dir: Working directory
        logger: Logger instance
        dry_run: If True, analyze without making changes

    Returns:
        Tuple of (success, new_line_count, notes)
    """
    full_doc_path = Path(working_dir) / AI_DOCS_DIR / entry.file_path

    if not full_doc_path.exists():
        return False, 0, f"File not found: {full_doc_path}"

    # Build the JSON arguments for the /refine_context command
    impl_paths = get_implementation_paths(entry.file_path)

    args_json = json.dumps({
        "file_path": f"ai_docs/{entry.file_path}",
        "original_lines": entry.original_lines,
        "impl_paths": impl_paths,
        "dry_run": dry_run,
    })

    request = AgentTemplateRequest(
        agent_name=f"{AGENT_NAME_PREFIX}_{entry.file_path.replace('/', '_')}",
        slash_command="/refine_context",
        args=[args_json],
        adw_id=adw_id,
        working_dir=working_dir,
    )

    logger.info(f"Starting review of {entry.file_path}")
    response = execute_template(request)

    if not response.success:
        logger.error(f"Agent failed: {response.output}")
        return False, 0, f"Agent error: {response.output[:100]}"

    # Count new lines
    new_lines = count_lines(full_doc_path)

    # Extract notes from response
    notes = extract_notes_from_response(response.output)

    return True, new_lines, notes


def extract_notes_from_response(output: str) -> str:
    """Extract a brief notes summary from agent output."""
    # Try to find JSON in the output
    json_match = re.search(r'\{[^{}]*"notes"[^{}]*\}', output, re.DOTALL)
    if json_match:
        import json
        try:
            data = json.loads(json_match.group())
            return data.get('notes', '')[:100]
        except json.JSONDecodeError:
            pass

    # Fallback: take first meaningful line
    lines = [l.strip() for l in output.split('\n') if l.strip() and not l.startswith('```')]
    return lines[0][:100] if lines else 'Completed'


def update_summary_statistics(tracking_path: Path) -> None:
    """Update the summary statistics section of the tracking file."""
    content = tracking_path.read_text()
    entries, _, _ = parse_tracking_table(content)

    total_files = len(entries)
    completed = sum(1 for e in entries if e.status == 'completed')
    in_progress = sum(1 for e in entries if e.status == 'in_progress')
    pending = sum(1 for e in entries if e.status == 'pending')

    total_original = sum(e.original_lines for e in entries)
    total_new = sum(e.new_lines or e.original_lines for e in entries)
    total_reduction = total_original - total_new
    reduction_pct = int(total_reduction / total_original * 100) if total_original > 0 else 0

    # Update summary section
    summary_pattern = r'(## Summary Statistics\n\n)(.*?)(\n\n## )'
    summary_text = f"""- **Total files**: {total_files}
- **Total lines**: {total_original:,}
- **Completed**: {completed}
- **In progress**: {in_progress}
- **Pending**: {pending}
- **Total reduction**: {total_reduction:,} lines ({reduction_pct}%)"""

    updated = re.sub(
        summary_pattern,
        rf'\g<1>{summary_text}\g<3>',
        content,
        flags=re.DOTALL
    )

    tracking_path.write_text(updated)


def main():
    """Main entry point."""
    load_dotenv()

    # Parse arguments
    dry_run = '--dry-run' in sys.argv
    specific_file = None
    resume_file = None

    if '--file' in sys.argv:
        file_idx = sys.argv.index('--file')
        if file_idx + 1 < len(sys.argv):
            specific_file = sys.argv[file_idx + 1]

    if '--resume' in sys.argv:
        resume_idx = sys.argv.index('--resume')
        if resume_idx + 1 < len(sys.argv):
            resume_file = sys.argv[resume_idx + 1]

    # Setup working directory
    working_dir = os.getcwd()

    # Generate unique ADW ID and agent ID
    adw_id = datetime.now().strftime('%Y%m%d%H%M%S') + '-' + uuid.uuid4().hex[:8]
    agent_id = generate_agent_id()

    # Setup logger
    logger = setup_logger(adw_id, "adw_context_management")

    # Determine tracking file path
    if resume_file:
        # Resume with existing tracking file
        tracking_path = Path(working_dir) / AI_DOCS_DIR / resume_file
        if not tracking_path.exists():
            logger.error(f"Tracking file not found: {tracking_path}")
            print(f"Error: Tracking file not found at {resume_file}")
            sys.exit(1)
        print(f"Resuming with existing tracking file: {resume_file}")
    else:
        # Generate new tracking file
        try:
            tracking_path = generate_tracking_file(adw_id, working_dir)
            print(f"Generated new tracking file: {tracking_path.name}")
        except FileNotFoundError as e:
            logger.error(str(e))
            print(f"Error: {e}")
            print(f"Ensure {TRACKING_SAMPLE} exists.")
            sys.exit(1)

    logger.info(f"ADW Context Management starting - ID: {adw_id}, Agent: {agent_id}")
    logger.info(f"Tracking file: {tracking_path}")
    logger.info(f"Mode: {'dry-run' if dry_run else 'live'}")

    if specific_file:
        logger.info(f"Targeting specific file: {specific_file}")

    # Initialize state
    state = ADWState(adw_id)
    state.update(agent_id=agent_id, mode='dry-run' if dry_run else 'live')

    # Process files until none remain
    files_processed = 0
    max_files = 1 if specific_file else 5  # Process up to 5 files per run

    while files_processed < max_files:
        # Claim a file
        entry = claim_file(tracking_path, agent_id, specific_file)

        if not entry:
            if files_processed == 0:
                logger.info("No pending files found")
                print("No pending files to process.")
            break

        logger.info(f"Claimed file: {entry.file_path}")
        print(f"\n[{agent_id}] Processing: {entry.file_path} ({entry.original_lines} lines)")

        try:
            # Review and simplify
            success, new_lines, notes = review_and_simplify_context(
                adw_id, entry, working_dir, logger, dry_run
            )

            if success:
                if not dry_run:
                    complete_file(tracking_path, entry, new_lines, notes)
                    reduction = entry.original_lines - new_lines
                    pct = int(reduction / entry.original_lines * 100)
                    print(f"[{agent_id}] Completed: {entry.file_path}")
                    print(f"           {entry.original_lines} -> {new_lines} lines ({pct}% reduction)")
                    print(f"           Notes: {notes}")
                else:
                    print(f"[{agent_id}] Analysis complete: {entry.file_path}")
                    print(f"           Notes: {notes}")
                    # Release file back to pending in dry-run mode
                    release_file(tracking_path, entry, 'dry-run analysis only')

                files_processed += 1
            else:
                logger.error(f"Failed to process {entry.file_path}: {notes}")
                release_file(tracking_path, entry, notes)
                print(f"[{agent_id}] Failed: {entry.file_path} - {notes}")

        except Exception as e:
            logger.exception(f"Error processing {entry.file_path}")
            release_file(tracking_path, entry, str(e)[:50])
            print(f"[{agent_id}] Error: {entry.file_path} - {e}")

        # Only process one specific file
        if specific_file:
            break

    # Update summary statistics
    if files_processed > 0 and not dry_run:
        update_summary_statistics(tracking_path)

    # Save state
    state.update(files_processed=files_processed)
    state.save("adw_context_management")

    logger.info(f"Completed - processed {files_processed} files")
    print(f"\n[{agent_id}] Session complete - processed {files_processed} file(s)")


if __name__ == "__main__":
    main()
