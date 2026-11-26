# Context Document Refinement Tracking

This document tracks the progress of context document reviews and simplification efforts. Each agent should claim a file by updating the `assigned_agent` and `status` columns before beginning work.

## Workflow Info

- **ADW ID**: {adw_id}
- **Created**: {created_at}
- **Status**: In Progress

## Instructions for Agents

1. **Claim a file**: Set `status` to `in_progress` and add your agent ID to `assigned_agent`
2. **Review**: Compare the context document against actual implementation code
3. **Simplify**: Remove redundancy, outdated info, and verbose explanations while preserving essential patterns
4. **Update**: Record `new_lines`, `reduction_%`, and any `notes`
5. **Complete**: Set `status` to `completed`

## Priority Order

Files are listed by line count (largest first). Prioritize larger files for maximum impact.

## Tracking Table

| file_path | original_lines | status | assigned_agent | new_lines | reduction_% | notes |
|-----------|----------------|--------|----------------|-----------|-------------|-------|
{tracking_rows}

## Summary Statistics

- **Total files**: {total_files}
- **Total lines**: {total_lines}
- **Completed**: 0
- **In progress**: 0
- **Pending**: {total_files}
- **Total reduction**: 0 lines (0%)

## Reduction Guidelines

When reviewing each document:

1. **Remove**: Obvious statements, excessive examples, outdated patterns
2. **Condense**: Multiple examples into single representative ones
3. **Preserve**: Critical patterns, gotchas, security requirements, naming conventions
4. **Verify**: Cross-reference with actual implementation to ensure accuracy
5. **Target**: Aim for 30-50% reduction while maintaining clarity

## Agent Coordination

- Only work on files with `status: pending`
- Update status to `in_progress` before starting
- If you encounter conflicts, abandon your changes and pick a different file
- Complete one file fully before claiming another
