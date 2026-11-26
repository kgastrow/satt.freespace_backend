# Rescue Verification (Partial Verdict)

Apply the **minimal set of changes** required to flip the failing acceptance criteria in a pre-merge verification report from `met: false` to `met: true`. The pre-merge verifier returned `verdict: partial` for a module that is otherwise close to passing; your job is to close the gap without expanding scope.

## Variables

adw_id: $1
module_id: $2
verification_report_path: $3
max_criteria_to_fix: $4 if provided, otherwise treat as "no cap"

## CRITICAL CONSTRAINTS — DO NOT VIOLATE

- You are operating inside an existing module branch with a passing implementation. **Do not** rewrite working features, refactor unrelated code, or expand scope beyond what the failing criteria require.
- **Do not** delete or move passing implementation files unless a failing criterion explicitly requires it.
- **Do not** create new spec documents, planning docs, or summaries. Fix code only.
- **Do not** run long-form test suites unless a criterion's evidence specifically calls for it. A quick `npx tsc --noEmit` or `ruff check` on touched files is fine and recommended.
- **Do not** push the branch — the parent workflow does that after you return.
- **Do not** open a PR or comment on the issue.
- **Do not** call `git commit --amend`, `git reset --hard`, `git push --force`, or any history-rewriting command.
- Use only: Read, Glob, Grep, Edit, Write, Bash (for `git add`/`git commit`/typecheck/lint only).

## Instructions

### 1. Read the verification report

- Read `verification_report_path`. It is a JSON document with this shape:
  ```json
  {
    "overall_verdict": "partial",
    "modules": [{
      "id": "<module_id>",
      "verdict": "partial",
      "criteria_total": N,
      "criteria_met": M,
      "criteria_details": [
        { "criterion": "...", "met": false, "evidence": "..." },
        ...
      ],
      "implementation_files": [...],
      "gaps": ["...", ...],
      "notes": "..."
    }],
    "cross_module_issues": [{"issue": "...", "severity": "high|medium|low"}, ...]
  }
  ```
- Locate the entry whose `id == module_id`. Collect every `criteria_details[*]` where `met == false`. These are your work items.
- Also note `cross_module_issues` whose `modules` list contains `module_id` — these often duplicate or amplify a criterion gap.

### 2. Triage

For each failing criterion, classify it into ONE bucket:

- **trivial** — a missing import, an un-wired component, a stub directory, a hard-coded list to extend, a missing locale stub. Estimated change ≤ ~20 lines across ≤ 3 files.
- **moderate** — a missing function/endpoint that the rest of the criterion's evidence describes concretely. Estimated change ≤ ~150 lines, no new architecture.
- **structural** — requires SSR, an entirely new pipeline, a new package, framework migration, or invents architecture the report does not describe. **Skip** these.

Apply this rule: **fix every trivial, fix moderate when the evidence names files/symbols, skip structural.** If `max_criteria_to_fix` was provided and you have more than that many actionable items, prioritise the criteria that the report's `notes` field flags as "blocking" or that the `cross_module_issues` lists as `severity: high`.

### 3. Apply fixes

For each item you plan to fix:

1. **Re-read the evidence string in the criterion.** It usually names specific files, line numbers, and the missing element (e.g., `"router.tsx:120-134 still mounts <StorefrontPlaceholder />"`). Treat the evidence as the spec for the fix.
2. **Read the affected files** before editing.
3. **Make the smallest possible change** — one criterion may need only a single Edit. Do not refactor surrounding code.
4. **Validate locally** for the type of change you made:
   - Frontend TS/TSX edits → `npx tsc --noEmit` (or `npm run lint -- <files>`) in `app/frontend/`.
   - Backend Python edits → `make lint` for the touched files, or `python -m py_compile <file>` as a quick check.
   - JSON files → `python -c "import json; json.load(open('<path>'))"` to confirm valid JSON.
   - Locale stubs → no validation needed beyond JSON well-formedness.
5. **Commit each fix as a focused commit** with `git add <specific files>` and a message starting with `fix(<module-id>):` and describing which criterion it addresses. Use HEREDOC for the message to keep formatting clean.

### 4. Skip and explain

For each item classified as **structural** (or otherwise out of scope), do not change code. Record it in your final report (Section 5) under `skipped_criteria` with a one-line reason.

### 5. Report (REQUIRED)

After committing all fixes, write a JSON summary to stdout — and nothing else — with this exact shape:

```json
{
  "module_id": "<module_id>",
  "criteria_attempted": ["<criterion text 1>", ...],
  "criteria_fixed": ["<criterion text 1>", ...],
  "criteria_skipped": [
    {"criterion": "<text>", "reason": "structural — requires SSR pipeline"}
  ],
  "commits": ["<sha1>", "<sha2>"],
  "files_touched": ["app/frontend/src/...", ...],
  "follow_up_recommended": "<one short sentence or empty string>"
}
```

- Only commit hashes you actually created go in `commits`. Use `git rev-parse --short HEAD` after each commit to capture them.
- `files_touched` is a deduplicated list of relative paths.
- If you fixed nothing (e.g., all items were structural), `criteria_fixed` is `[]` and the report still gets emitted.

CRITICAL: stdout must contain ONLY the JSON object above. No prose, no markdown fences, no commentary.

## Tips

- Prefer Edit over Write for existing files.
- For routing/wiring fixes, the evidence usually tells you the exact lines to replace. Mirror existing nearby lazy-import patterns rather than inventing new ones.
- For "stub directory missing" criteria (e.g., locale `af`/`zu` directories), an empty `{}` JSON file per namespace is sufficient — the criterion explicitly says "present and empty."
- For "test coverage missing" criteria, **skip** unless the evidence names a specific small test the verifier could not find. Bulk test authoring is not an auto-rescue scope.
- For "Lighthouse / bundle budget not asserted" criteria, **skip** unless the fix is a 1–3 line config edit named in the evidence.
- Never edit `package.json` / `pyproject.toml` / `requirements.txt` unless a criterion explicitly requires a new dependency named in the evidence.
- If `git diff --stat HEAD~1` shows zero changes after your work, do not create an empty commit; emit the JSON report with `criteria_fixed: []`.
