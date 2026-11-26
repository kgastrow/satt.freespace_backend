# Resolve Merge Conflict

A `git merge` in this repository has stopped with content conflicts. Your job is to resolve EVERY conflicted file safely so the merge can be completed, OR to abort cleanly if any conflict isn't auto-resolvable.

## Variables

adw_id: $1
branch_name: $2 — the branch being merged INTO main (the "theirs" side; main is "ours")
report_path: $3 — write your JSON report here

## CRITICAL CONSTRAINTS — DO NOT VIOLATE

- You are operating in the main repository root (NOT a worktree). `git status` shows the in-progress merge with conflicted files.
- DO NOT run `git merge --abort` — the caller will do that if you return failure. Premature abort leaves the system in a state the caller can't recover from.
- DO NOT run `git commit` — the caller will commit after verifying your resolution.
- DO NOT run `git push`, `git checkout`, `git reset`, or any branch-switching command. You ONLY edit files, stage them with `git add`, and validate.
- DO NOT skip validation. Files you resolve must compile / parse cleanly before you stage them.
- DO NOT invent code beyond what the two sides of the conflict require. If you can't decide between two versions, pick one verbatim — don't write a third synthesis.
- Use only: Read, Edit, Write, Bash (for `git show`, `git add`, syntax validation, and reading git state).

## Inputs you have

- `git status --porcelain` lists files marked `UU` (unmerged content), `AU`, `UA`, `DU`, `UD` (other unmerged states).
- For each conflicted file, the three versions are accessible via:
  - `git show :1:<path>` — the merge base (common ancestor)
  - `git show :2:<path>` — "ours" (the side already on the current branch, which is `main`)
  - `git show :3:<path>` — "theirs" (the side being merged in, i.e. the feature branch named in $2)
- The file in the working tree already contains conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).

## Process

### 1. Inventory

Run `git status --porcelain` and list every conflicted file. Categorize each per file path:

- **`/__init__.py` files, `response_codes.py`, similar config dicts/lists** → likely append-only registry conflicts
- **Markdown tables (`.md` with `|` rows)** → likely append-only documentation rows
- **JSON locale/config files** (e.g. `app/frontend/src/locales/*.json`) → likely additive key conflicts; see locale-parity rule below
- **`adminNav.ts`, `routes.ts`, similar TS config arrays** → likely additive entry conflicts
- **Actual `.py` / `.ts` / `.tsx` source files with function/class definitions** → could be append-only OR semantic conflict; need to inspect

### 2. Classify each conflict

For each file, read the three versions (`git show :1:`, `:2:`, `:3:`) and decide:

- **(A) Append-only**: both ours and theirs added DIFFERENT lines to the same context location. Neither modified an existing base line. Strategy: keep ALL lines from both sides; order is base lines first, then ours-additions, then theirs-additions (or any sensible order that compiles).
- **(B) Semantic duplicate**: ours and theirs added DIFFERENT code that does the SAME THING (same effect, possibly different wording, comments, or variable names). Strategy: pick whichever version is cleaner / more idiomatic; document why in your report.
- **(C) Logic divergence**: ours and theirs modified the SAME logic in DIFFERENT ways. Strategy: combine carefully ONLY if the combination is obviously safe (e.g., two independent guard clauses on different conditions). If in doubt, fall through to "unsafe" — don't guess.
- **(D) Unsafe / can't determine**: any conflict where you're uncertain. Report the file and stop — do not write a resolution. The caller will abort the merge.

### 3. Apply the resolution

Edit the file IN THE WORKING TREE to produce the resolved content:

- Remove ALL conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`).
- Write the chosen merged content.
- Match the file's existing indentation, quote style, trailing newlines.
- For Python imports: keep alphabetical order if the existing imports are alphabetical; otherwise append.
- For dict entries / list items: if a natural ordering exists (alphabetical by key, ID order), preserve it; otherwise append theirs after ours.
- For markdown tables: keep header rows where they were, then the union of body rows.

### 4. Validate per file type

Before staging, verify the resolved file is syntactically / structurally clean:

- `.py` → `python -m py_compile <file>` (use the project's `.venv` python if available, else system python; either is fine for syntax check)
- `.ts` / `.tsx` / `.js` / `.jsx` → skip full typecheck (too slow); spot-check: file ends with a trailing newline, no leftover conflict markers, balanced braces (rely on `grep -c '<<<<<<<'` returning 0).
- `.json` → `python -c "import json,sys; json.load(open('<file>'))"`
- `.md` / other text → just check `grep -c '<<<<<<<'` returns 0.

If validation fails: report the file as unsafe and stop. Do not stage broken files.

### 5. Stage

`git add <file>` for each resolved file. Do NOT stage files you couldn't resolve.

### 6. Final check

Run `git status --porcelain` again. There should be zero files in any unmerged state (`UU`, `AU`, `UA`, `DU`, `UD`). If anything is still unmerged, your resolution is incomplete — DO NOT report success.

### 7. Report (REQUIRED)

Write a JSON document to `report_path` with this exact shape:

```json
{
  "branch": "<branch_name>",
  "resolved": [
    {"file": "app/backend/src/api/v1/__init__.py", "strategy": "append-only-union", "note": "Both sides added different include_router lines for disjoint URL prefixes."},
    {"file": "app/backend/src/api/admin_orders.py", "strategy": "semantic-duplicate-pick-main", "note": "Both branches added an else: clause for the same 'no gateway payment intent' case with identical effect. Kept main's wording which is more concise."}
  ],
  "skipped": [
    {"file": "<path>", "reason": "Logic divergence in <function_name>; both sides modified the same code path with incompatible semantics."}
  ],
  "validation": {
    "py_compile_pass": true,
    "json_parse_pass": true,
    "no_conflict_markers": true
  },
  "outcome": "all_resolved" | "partial" | "all_unsafe"
}
```

- `outcome: "all_resolved"` ONLY when `skipped` is empty AND every file in `resolved` validated.
- `outcome: "partial"` when some resolved successfully but others were skipped as unsafe.
- `outcome: "all_unsafe"` when nothing was resolved.

Stdout after writing the file: print ONLY the absolute path of the report file. No prose.

## Tips

- The `grep -c '<<<<<<<'` trick is your sanity check — a clean file should always return 0.
- Don't over-think append-only conflicts: if both sides only ADDED lines (compared to base), union them.
- For semantic duplicates, prefer the version that's already on main (`:2:` "ours") when the two are functionally equivalent — main has more reviewer-eyeballs on it.
- If you're tempted to write a "synthesis" of two conflicting versions, that's a signal to mark it unsafe and skip.
- For `__init__.py` files, after concatenating both sides' imports/registrations, verify there are no DUPLICATE identifiers (`from .foo import X` appearing twice). If so, dedupe.
- `git show :2:<file>` may fail if the file was deleted on main side; in that case the conflict is "modify/delete" and you need different handling — typically pick the version that retains the file (since the other side deleted it). Document in the report.
- **i18n locale-parity rule**: this codebase (CLAUDE.md rule 8) requires every user-facing string to exist in ALL locale files (e.g. `en.json`, plus any others under `app/frontend/src/locales/`). If a conflict in one locale forces you to pick one side, check the OTHER locale files for keys that the picked side adds — and either pick the equivalent side everywhere or mark the conflict unsafe. A merge that lands new translation keys in `en.json` but not `fr.json` will silently break i18n; never let that happen. When in doubt about locale parity, mark unsafe and skip.
- For FastAPI router registrations (`v1_router.include_router(...)`): in addition to deduping identifiers, scan both sides for `include_router(..., prefix="/foo")` calls and reject the resolution if both sides declare the same prefix — that's a runtime path collision FastAPI will reject at startup but `py_compile` will pass. Mark unsafe in this case.
