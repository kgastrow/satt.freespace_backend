# Refine Context Document
> Review and refine and simplify an AI context document while preserving essential patterns.

## Arguments
- $ARGUMENTS: JSON object with file_path, original_lines, impl_paths, and dry_run

## Instructions

Parse the arguments:
```
$ARGUMENTS
```

### Step 1: Read the Context Document
Read the full context document at the specified `file_path` (relative to ai_docs/).

### Step 2: Verify Against Implementation
Search the implementation directories specified in `impl_paths` to verify documented patterns match actual code. Look for:
- Function/class names mentioned in the doc
- Code patterns and examples
- File paths referenced

### Step 3: Identify Issues
Note any:
- **Inaccuracies**: Documentation that doesn't match implementation
- **Redundancy**: Repeated explanations or excessive examples
- **Verbosity**: Long explanations that could be tables or bullet points
- **Outdated info**: References to removed or changed code

### Step 4: Simplify (unless dry_run is true)
If not in dry-run mode, edit the document to:
- Remove obvious statements and redundant explanations
- Condense multiple similar code examples into single representative ones
- Convert verbose lists to tables where appropriate
- Fix any inaccuracies found
- Preserve: critical patterns, gotchas, security requirements, naming conventions

### Step 5: Output Results
Return a JSON object:
```json
{
  "success": true,
  "changes_made": ["list of changes or findings"],
  "inaccuracies_found": ["list of doc/implementation mismatches"],
  "notes": "brief summary (max 100 chars)"
}
```

## Critical Rules
- NEVER remove security-related documentation
- NEVER remove gotchas or common mistakes sections
- Preserve all naming conventions and required patterns
- When in doubt, keep the content
- Always verify examples against actual implementation before removing
