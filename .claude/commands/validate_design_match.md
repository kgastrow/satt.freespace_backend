# Validate Design Match

Compare a UI module's built output against the design-handoff prototype screens it was meant to reproduce. Produces a per-screen match score; gates at 0.8.

This skill mirrors the scoring contract of `/rescue_validate_visual` but compares against a design handoff (prototype HTML/JSX) instead of a running source project. Reuse this skill any time a module's plan contains `design_references`.

## Arguments

- `$1` — ADW ID
- `$2` — Path to the module's spec / plan file (contains `design_references` block)
- `$3` — (Optional) Agent name for output dir (default: `design_validator`)

## When to skip

If the spec at `$2` contains no `## Design References` section and no `design_references` array, **skip this skill entirely** and exit with a "no design refs — gate is a no-op" message. The greenfield workflow runs the same review pipeline whether or not a design handoff is in scope; this gate only activates when refs are present.

## Instructions

### 1. Load design references from the spec

Read the spec file at `$2`. Extract the design_references list — each entry tells you:
- `screen_id` / `screen_name`
- `prototype_file` (path to JSX/HTML in `specs/design_handoff*/src/`)
- `prototype_component` (named export or DOM id)
- `surface` and `theme`

Also read `ai_docs/frontend/context/design_system.md` to get the token reference — you'll use it to identify token violations in §4.

### 2. Capture prototype screenshots

The prototype bundle includes a runnable HTML file (typically `specs/design_handoff*/Legacy Sports.html` or `index.html` — discover it by listing the handoff dir's top-level `.html` files). Open it in a headless browser:

```bash
# Use the existing screenshot infra
# (look for adws/review_screenshot_runner.py or similar in the codebase)
```

Render each referenced `prototype_component` at the surface's natural viewport:
- `client-pwa-instore` / `client-pwa-online` → 390×844 (iPhone 14 equivalent)
- `management-centre` → 1440×900
- `public-web` → 1440×900 (also capture 390 width for responsive verification)

Save to `agents/{adw_id}/{agent_name}/screenshots/prototype/<screen_id>.png`.

If the prototype HTML can't be rendered (CDN unreachable, parse failure), fall back to embedding the prototype JSX in a vanilla React harness inline. If even that fails, note the limitation in the report and proceed with **token + structural analysis only** (no pixel comparison).

### 3. Capture built-app screenshots

Use `/prepare_app` to start backend + frontend on the worktree's allocated ports (read from `.ports.env`). Wait for health checks to pass.

Navigate to the route that delivers each referenced screen. The route mapping comes from the module's plan (look for the page file path and the router config). Capture at the same viewport as the prototype.

Save to `agents/{adw_id}/{agent_name}/screenshots/built/<screen_id>.png`.

### 4. Score per screen

For each `(prototype, built)` pair, score on three axes — same contract as `/rescue_validate_visual`:

```
layout_score      = assess_layout_similarity()       # 0-1
                    (overall structure, region order, viewport-relative positioning)

style_score       = assess_style_consistency()       # 0-1
                    (color tokens used, typography family + size + weight + italic,
                     spacing rhythm, radii, shadow weight)

component_score   = assess_component_fidelity()      # 0-1
                    (CTAs use slashed/hex shape, chips use parallelogram shape,
                     hero gradient present, signature animations present,
                     reserved tokens not used as general accents)

overall = (layout_score + style_score + component_score) / 3

status:
  >= 0.8  excellent
  >= 0.6  good
  >= 0.4  acceptable
  <  0.4  poor
```

**Differentiator vs. rescue_validate_visual:** the comparison target is a *design prototype*, not a running source project. Implementations will use a different component library than the prototype (real shadcn vs. prototype's vanilla React with CDN Babel). Treat the following as **acceptable differences** that should NOT drag scores down:
- Real shadcn components instead of inline-styled prototype divs
- Real router URLs / link behavior
- Real form validation feedback
- Real loading states / skeletons

Treat the following as **score-dragging deviations**:
- Wrong palette (e.g. plain blue button instead of `--ls-blue` hex CTA)
- Missing display font (Inter everywhere instead of Saira Condensed for hero copy)
- Missing shape language (rounded pill button where hex slash was specified)
- Reserved token misuse (gold used as a general accent)
- Missing signature animations (scan-laser sweep absent)
- Wrong theme (light surfaces where dark was specified)

### 5. Identify differences

For each screen, list:
- **Blockers** (must-fix before merge): wrong palette, missing display font, missing brand shape on primary CTA, reserved-token misuse, wrong theme.
- **Major** (should-fix): missing signature animation, significantly wrong spacing rhythm, wrong type scale on hero copy.
- **Minor** (note only): small spacing nudges, alternative-but-equivalent component choices.

## Output

Write a JSON report to `agents/{adw_id}/{agent_name}/match_report.json`:

```json
{
  "timestamp": "2026-05-16T10:30:00Z",
  "module_id": "self-scan-checkout",
  "design_handoff_path": "specs/design_handoff_legacy_sports",
  "overall_match_percent": 84.5,
  "gate_status": "pass",
  "screens": [
    {
      "screen_id": "screen-store-entry",
      "screen_name": "Store entry",
      "prototype_screenshot": "agents/<adw_id>/design_validator/screenshots/prototype/screen-store-entry.png",
      "built_screenshot": "agents/<adw_id>/design_validator/screenshots/built/screen-store-entry.png",
      "scores": {
        "layout": 0.92,
        "style": 0.85,
        "components": 0.78,
        "overall": 0.85
      },
      "status": "excellent",
      "differences": [
        {
          "severity": "major",
          "type": "components",
          "description": "Primary CTA uses rounded-md border instead of hex clip-path slash. Apply .ls-cta-hex utility from design_system.md."
        },
        {
          "severity": "minor",
          "type": "style",
          "description": "Hero card gradient angle is 145deg instead of specified 160deg."
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

Also write a markdown report to `agents/{adw_id}/{agent_name}/match_report.md` summarizing the above for human reading.

### Gate logic

The gate **fails** if:
- Any screen scores `< 0.6`, OR
- The report contains any `severity: "blocker"` difference, OR
- The overall_match_percent is below 80%.

When the gate fails, emit the report's blocker and major issues as `ReviewIssue` objects (severity `blocker` for blockers, `non-blocker` for majors) so the existing `adw_review_iso.py` resolution loop can pick them up.

When the gate passes, emit a success message and exit 0.

Print to stdout:

```
=== DESIGN MATCH VALIDATION ===

Module: self-scan-checkout
Overall match: 84.5%
Gate: PASS

Screens:
  - Store entry: 85% (excellent)
  - Scan loop: 88% (excellent)
  - Item confirm: 76% (good)
  - Exit QR: 89% (excellent)

Major issues to address (non-blocking):
  - Store entry: CTA missing hex clip-path
  - Scan loop: laser animation missing
  - Item confirm: gold used as general accent (reserved token)

Recommendation: <recommendation>
```

## Validation

- Prototype screenshots exist for every referenced screen (or fallback documented).
- Built-app screenshots exist for every referenced screen.
- Match report JSON is valid and contains every screen.
- Gate verdict is unambiguous (pass / fail).
- Blocker / major differences are clearly labeled and reference design_system.md tokens by name.

$ARGUMENTS
