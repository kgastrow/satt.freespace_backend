# Generate Git Branch Name

Output a git branch name. No explanation. No preamble. Just the branch name.

## Variables

issue_class: $ARGUMENT
adw_id: $ARGUMENT
issue: $ARGUMENT

## Format

`<issue_class>-issue-<issue_number>-adw-<adw_id>-<concise_name>`

Rules for `<concise_name>`:
- 3-6 words, lowercase, hyphen-separated
- Descriptive of the task

## Examples

```
feat-issue-123-adw-20260107143052-a1b2c3d4-add-user-auth
bug-issue-456-adw-20260107150530-e5f6g7h8-fix-login-error
chore-issue-789-adw-20260108091215-i9j0k1l2-update-deps
```

## Output

Respond with the branch name only. Do not include any other text, explanation, or formatting.