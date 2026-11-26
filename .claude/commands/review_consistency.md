# Review Consistency

Follow the `Instructions` below to **review implementation consistency** against context documentation. Analyze the specified code area and compare it against the patterns, conventions, and requirements documented in `ai_docs/`.

## Variables

context_file: $1 (path to the context document to review against, e.g., "ai_docs/backend/context/crud.md")
review_area: $2 (code directory to review, e.g., "app/backend/src/crud")
output_path: $3 (EXACT file path to write the report to - use this path exactly, do not modify it)
adw_id: $4 if provided, otherwise use timestamp
agent_name: $5 if provided, otherwise use 'consistency_reviewer'

## Instructions

### 1. Read Context Documentation

- Read the specified context file (`context_file`) thoroughly
- Extract key patterns, conventions, and requirements documented
- Note any critical rules (e.g., "ALWAYS filter by organization_id")
- Identify mandatory patterns vs. optional best practices

### 2. Analyze Implementation

Systematically analyze the code in `review_area`:

#### 2.1 Pattern Compliance Check
- List all files in the review area
- For each significant file, check if it follows documented patterns
- Note any deviations from documented conventions

#### 2.2 Antipattern Detection
Look for common antipatterns:
- **Hard deletes**: Use of `DELETE` without soft delete pattern
- **Missing tenant isolation**: Queries without `organization_id` filtering
- **Sync I/O in async context**: Blocking calls in async functions
- **Business logic in wrong layer**: Logic in API layer instead of services
- **Inconsistent naming**: Names that don't follow conventions
- **Missing type hints**: Untyped function parameters or returns
- **Hardcoded values**: Magic strings/numbers instead of config

#### 2.3 Dead Code Detection
Search for:
- Unused imports (grep for imported but unused names)
- Unused functions (defined but never called)
- Commented-out code blocks
- Obsolete feature flags or conditional code

#### 2.4 Duplicate Code Detection
Identify:
- Similar function implementations across files
- Copy-pasted code blocks
- Logic that should be abstracted into shared utilities

### 3. Cross-Reference Validation

Compare documentation examples with actual implementation:
- Are the import paths in docs correct?
- Do the code patterns in docs match what's in the codebase?
- Are there documented features that don't exist in code?
- Are there implemented features not documented?

### 4. Generate Report

**CRITICAL: Write your report to the EXACT path specified in `output_path`.** Do not modify this path or add timestamps/prefixes/suffixes. The orchestrator expects the file at this exact location.

Use the Write tool to create the report file at `output_path`.

**Severity Levels:**
- `critical`: Security risk or data integrity issue (must fix immediately)
- `high`: Breaks documented patterns, technical debt accumulator
- `medium`: Inconsistency, should fix in next sprint
- `low`: Minor style issue, fix when touching the file
- `info`: Observation, not necessarily wrong

### Output Format

Write a markdown report with the following structure:

```markdown
# Consistency Review: <context_filename>

**Context File:** `<path to context doc reviewed>`
**Review Area:** `<code directory reviewed>`
**Files Analyzed:** <count>
**Compliance Score:** <0-100>%

## Summary

<2-3 sentence executive summary of findings>

---

## Pattern Violations

| File | Line | Pattern | Severity | Description |
|------|------|---------|----------|-------------|
| `path/to/file.py` | 42 | pattern_name | high | What is wrong |

### Fix Suggestions

#### `path/to/file.py:42` - pattern_name
How to fix it

---

## Antipatterns

| Type | File | Line | Severity | Description |
|------|------|------|----------|-------------|
| missing_tenant_isolation | `path/to/file.py` | 15 | critical | Description |

### Fix Suggestions

#### `path/to/file.py:15` - missing_tenant_isolation
How to fix it

---

## Dead Code

| File | Line | Type | Confidence | Description |
|------|------|------|------------|-------------|
| `path/to/file.py` | 100 | unused_import | high | What is dead |

---

## Duplicate Code

### Duplication 1
**Files:** `path/to/file1.py:20`, `path/to/file2.py:35`

What is duplicated

**Suggestion:** How to DRY this up

---

## Documentation Drift

| Location | Issue | Description |
|----------|-------|-------------|
| Line 25 | outdated | What is wrong with the doc |

### Fix Suggestions

#### Line 25 - outdated
How to update the doc

---

## Recommendations

### High Priority

- [ ] **[refactor]** Description - `affected/file1.py`, `affected/file2.py`

### Medium Priority

- [ ] **[security]** Description - `affected/file.py`

### Low Priority

- [ ] **[documentation]** Description - `affected/file.py`
```

**Notes:**
- Omit any section that has no findings (e.g., if no dead code found, omit the Dead Code section)
- Use checkboxes (`- [ ]`) for recommendations to enable tracking
- Include the severity emoji prefix for quick scanning: 🔴 critical, 🟠 high, 🟡 medium, 🔵 low, ⚪ info

## Review Guidelines

### Critical Rules to Always Check

1. **Multi-tenancy**: Every CRUD operation on tenant-scoped models must filter by `organization_id`
2. **Soft deletes**: Never use hard deletes, always set `deleted_time`
3. **Async patterns**: All database and I/O operations must be async
4. **Auth dependency**: All protected endpoints must use auth dependencies
5. **Type safety**: Function signatures should have type hints

### What to Ignore

- Minor formatting inconsistencies (handled by formatters)
- Test files (different patterns apply)
- Generated code (e.g., migrations)
- Vendor/third-party code

### Output Notes

- Be thorough but prioritize actionable findings
- Group related issues together
- Provide concrete fix suggestions, not vague advice
- Calculate compliance_score based on files that follow vs. deviate from patterns

### Final Output

After writing the markdown report to the EXACT `output_path` provided, output only:

```
DONE
```

Do not output anything else. Do not output your analysis as text - it must be written to the file. The orchestrator will read the report from the file at `output_path`.
