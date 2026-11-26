# ADW Workflow Extraction

Extract ADW workflow information from the text below and return a JSON response.

## Instructions

- Look for ADW workflow commands in the text (e.g., `/adw_plan_iso`, `/adw_build_iso`, `/adw_test_iso`, `/adw_smoke_iso`, `/adw_review_iso`, `/adw_document_iso`, `/adw_patch_iso`, `/adw_plan_build_iso`, `/adw_plan_build_test_iso`, `/adw_plan_build_test_review_iso`, `/adw_sdlc_iso`, `/adw_sdlc_ZTE_iso`, `/adw_multi_phase_sdlc_iso`, `/adw_implementation_consistency_iso`)
- Also recognize commands without the `_iso` suffix and automatically add it (e.g., `/adw_plan` → `/adw_plan_iso`)
- Also recognize variations like `adw_plan_build`, `adw plan build`, `/adw plan then build`, etc. and map to the correct command
- Look for ADW IDs (format: YYYYMMDDHHMMSS-<8-char-uuid>, e.g., 20260107143052-a1b2c3d4, often after "adw_id:" or "ADW ID:" or similar)
- Look for model set specification: "model_set base", "model_set heavy", or "model_set superheavy" (case insensitive)
  - Default to "base" if no model_set is specified
  - Also recognize variations like "model set: heavy", "modelset superheavy", etc.
  - "heavy" pins opus to claude-opus-4-6; "superheavy" pins opus to claude-opus-4-7 (latest, most expensive)
- Return a JSON object with the extracted information
- If no ADW workflow is found, return empty JSON: `{}`
- IMPORTANT: DO NOT RUN the `adw_sdlc_ZTE_iso` workflows unless `ZTE` is EXPLICITLY uppercased. This is a dangerous workflow and it needs to be absolutely clear when we're running it. If zte is not capitalized, then run the non zte version `/adw_sdlc_iso`.

## Valid ADW Commands

- `/adw_plan_iso` - Planning only
- `/adw_build_iso` - Building only (requires adw_id)
- `/adw_test_iso` - Testing only (requires adw_id)
- `/adw_smoke_iso` - Smoke test only (requires adw_id, requires Chrome)
- `/adw_review_iso` - Review only (requires adw_id)
- `/adw_document_iso` - Documentation only (requires adw_id)
- `/adw_ship_iso` - Ship/approve and merge PR (requires adw_id)
- `/adw_patch_iso` - Direct patch from issue
- `/adw_plan_build_iso` - Plan + Build
- `/adw_plan_build_test_iso` - Plan + Build + Test
- `/adw_plan_build_review_iso` - Plan + Build + Review (skips test)
- `/adw_plan_build_document_iso` - Plan + Build + Document (skips test and review)
- `/adw_plan_build_test_review_iso` - Plan + Build + Test + Review
- `/adw_sdlc_iso` - Complete SDLC: Plan + Build + Test + Smoke + Review + Document
- `/adw_sdlc_router_iso` - Intelligent SDLC router that auto-selects single-phase or multi-phase based on issue complexity. Use this when you want automatic routing.
- `/adw_sdlc_zte_iso` - Zero Touch Execution: Complete SDLC + auto-merge to production. Note: as per instructions, 'ZTE' must be capitalized. Do not run this if 'zte' is not capitalized.
- `/adw_multi_phase_sdlc_iso` - Multi-phase SDLC for large features that exceed single-agent context limits. Breaks work into phases, each running build -> test -> review -> commit.
- `/adw_implementation_consistency_iso` - Parallel code review against context documentation. Reviews implementation consistency, pattern violations, antipatterns, dead code, and documentation drift.

## Response Format

Respond ONLY with a JSON object in this format:
```json
{
  "adw_slash_command": "/adw_plan",
  "adw_id": "20260107143052-a1b2c3d4",
  "model_set": "base"
}
```

Fields:
- `adw_slash_command`: The ADW command found (include the slash)
- `adw_id`: The ADW ID if found (format: YYYYMMDDHHMMSS-<8-char-uuid>)
- `model_set`: The model set to use ("base", "heavy", or "superheavy"), defaults to "base" if not specified

If only some fields are found, include only those fields.
If nothing is found, return: `{}`
IMPORTANT: Always include `model_set` with value "base" if no model_set is explicitly mentioned in the text.

## Text to Analyze

$ARGUMENTS