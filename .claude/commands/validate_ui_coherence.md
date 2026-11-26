# Validate UI Coherence

Screenshot-based visual quality gate for greenfield UI modules that have **no design handoff** to compare against. Where `/validate_design_match` scores a module against prototype screens, this command scores a module's built screens against the app's own design system and its sibling screens — catching incoherence, broken responsive layouts, and obvious visual defects. Runs at **both** mobile (390×844) and desktop (1440×900) viewports.

Use this gate for every UI-bearing module (`target_audience ∈ {end_user, admin, platform_admin}`) when the run has **no** design handoff. When a handoff IS present, use `/validate_design_match` instead — this command is the no-handoff equivalent.

## Arguments

- `$1` — ADW ID (worktree/run identifier, used for output dir)
- `$2` — Path to the module's plan file (lists the routes/pages this module delivers)
- `$3` — (Optional) Agent name for output dir (default: `ui_coherence_validator`)

## When to skip

If the module is `backend_only` or its plan delivers no user-facing routes, **skip entirely** and exit with a "no UI surface — gate is a no-op" message.

## Instructions

### 1. Identify the screens to capture

Read the plan at `$2`. Extract every route/page this module delivers (look for page file paths, router-config entries, and navigation placement). Build a capture list: one entry per distinct screen state worth verifying (list view, detail view, create/edit dialog open, empty state). Aim for the module's primary screens, not every permutation — 3–8 captures is typical.

Read `ai_docs/frontend/context/design_system.md` if it exists, otherwise `ai_docs/frontend/baseline_context.md`, to learn the app's token system, typography scale, spacing rhythm, and component conventions. These are your coherence reference.

### 2. Capture screenshots at both viewports

Start the worktree's app with `/prepare_app` (reads `.ports.env` for this worktree's ports) and wait for health checks to pass. Set up test auth with `/setup_test_auth` so authenticated routes render.

Use the existing headless capture utility `adws/review_screenshot_runner.py` (Playwright-based; takes a JSON capture definition with `application_url`, `auth` tokens, and a `captures` array — see its header for the schema). Run it **twice**, once per viewport, passing the viewport in each capture. Save to:
- `agents/{adw_id}/{agent_name}/screenshots/desktop/<screen_id>.png` (1440×900)
- `agents/{adw_id}/{agent_name}/screenshots/mobile/<screen_id>.png` (390×844)

If a screen fails to render (route 404s, blank page, JS error), that is itself a **blocker** finding — record it and continue capturing the rest.

Tear down test auth with `/teardown_test_auth` when done.

### 3. Score each screen

For each screen, view both the desktop and mobile screenshots and score on four axes (0–1):

```
design_system_score  = adherence to the app's own tokens, type scale, spacing,
                       and component conventions (from the design system doc)

layout_score         = is the layout sound and intentional at THIS viewport —
                       no overflow, no clipped content, no overlapping elements,
                       no content pushed off-screen, sensible use of space

responsive_score     = does the screen adapt correctly between viewports —
                       desktop is not a stretched phone layout, mobile is not a
                       squashed desktop; tables scroll or reflow, nav collapses,
                       touch targets are adequate, no horizontal body scroll on mobile

polish_score         = absence of obvious defects — broken images, unstyled
                       flashes, raw i18n keys shown instead of translated text,
                       placeholder/lorem text, misaligned controls, inconsistent
                       button/dialog/empty-state treatment vs sibling screens

overall = (design_system_score + layout_score + responsive_score + polish_score) / 4

status:
  >= 0.8  excellent
  >= 0.6  good
  >= 0.4  acceptable
  <  0.4  poor
```

Score each viewport's contribution honestly: a screen that looks perfect on desktop but breaks on mobile (or vice-versa) must NOT score above `acceptable` — responsive parity is mandatory for this template.

### 4. Classify findings

For each screen list:
- **Blockers** (must-fix before merge): screen fails to render; content clipped/overflowing/overlapping at either viewport; horizontal body scroll on mobile; raw i18n keys visible; desktop-only layout that is unusable on mobile (or vice-versa); wholesale disregard of the design system.
- **Major** (should-fix): inconsistent component treatment vs sibling screens, wrong type scale, poor spacing rhythm, awkward-but-usable responsive behavior.
- **Minor** (note only): small spacing nudges, subjective polish.

## Output

Write a JSON report to `agents/{adw_id}/{agent_name}/coherence_report.json`:

```json
{
  "timestamp": "2026-07-08T10:30:00Z",
  "module_id": "customer-management",
  "overall_score_percent": 82.0,
  "gate_status": "pass",
  "viewports_tested": ["desktop", "mobile"],
  "screens": [
    {
      "screen_id": "customer-list",
      "route": "/customers",
      "desktop_screenshot": "agents/<adw_id>/ui_coherence_validator/screenshots/desktop/customer-list.png",
      "mobile_screenshot": "agents/<adw_id>/ui_coherence_validator/screenshots/mobile/customer-list.png",
      "scores": {
        "design_system": 0.88,
        "layout": 0.85,
        "responsive": 0.80,
        "polish": 0.82,
        "overall": 0.84
      },
      "status": "excellent",
      "findings": [
        {
          "severity": "major",
          "type": "responsive",
          "description": "On mobile the action column crowds the row; move row actions into an overflow menu below 640px."
        }
      ]
    }
  ],
  "summary": {
    "screens_compared": 4,
    "excellent": 2,
    "good": 1,
    "acceptable": 1,
    "poor": 0,
    "blocker_count": 0,
    "major_count": 3
  },
  "recommendation": "Merge with major-severity follow-ups, or request a patch to address the 3 major issues."
}
```

Also write a markdown summary to `agents/{adw_id}/{agent_name}/coherence_report.md`.

### Gate logic

The gate **fails** if:
- Any screen scores `< 0.6` at either viewport, OR
- The report contains any `severity: "blocker"` finding, OR
- `overall_score_percent` is below 75%.

When the gate fails, emit the blocker and major findings as `ReviewIssue` objects (severity `blocker` for blockers, `non-blocker` for majors) so the orchestrator's resolution loop can pick them up. When it passes, emit a success message.

Print to stdout:

```
=== UI COHERENCE VALIDATION ===

Module: customer-management
Overall: 82.0%   Gate: PASS
Viewports: desktop (1440×900), mobile (390×844)

Screens:
  - Customer list:   84% (excellent)
  - Customer detail: 81% (excellent)
  - Create dialog:   78% (good)
  - Empty state:     72% (acceptable)

Issues to address:
  - Customer list (major): mobile action column crowding
  - Empty state (major): empty-state copy not using i18n

Recommendation: <recommendation>
```

## Validation

- Screenshots exist for every screen at BOTH viewports (or a render-failure blocker is recorded).
- Report JSON is valid and contains every screen with both-viewport scores.
- Gate verdict is unambiguous (pass / fail).
- Every blocker/major finding names the screen, the viewport, and the concrete fix.

$ARGUMENTS
