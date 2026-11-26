# Evaluate Feasibility

Final feasibility assessment before execution begins.

## Arguments
- `$1` - ADW ID

## Input Files
- `discovery/discovery_summary.md`
- `triage/backend_classification.json`
- `triage/component_scores.json`
- `triage/task_graph.json`
- `triage/ui_rescue_plan.md`

## Instructions

Perform final feasibility check before committing to execution.

### 1. Resource Assessment

Calculate total effort:
- Sum estimated hours from all tasks
- Add 20% buffer for unexpected issues
- Compare against typical rescue timelines

### 2. Risk Assessment

Evaluate key risks:

**Technical Risks:**
- Components marked MANUAL (high effort, uncertain outcome)
- External integrations without documentation
- Complex animations or custom libraries

**Scope Risks:**
- Feature count vs estimated hours
- Missing requirements in source
- Untestable features

**Quality Risks:**
- CSS chaos files (styling consistency)
- State chaos (data flow complexity)
- Missing tests in source

### 3. Go/No-Go Criteria

**PASS if:**
- Total hours < 80 (reasonable for rescue)
- MANUAL tier components < 30% of total
- No critical blockers identified
- At least 70% of features are complete in source

**FAIL if:**
- Total hours > 120 (better to rewrite)
- MANUAL tier components > 50%
- Critical external integrations undocumented
- Enterprise complexity detected

### 4. Scope Reduction Recommendations

If borderline, suggest scope reductions:
- Features to defer to phase 2
- Components to skip (use template defaults)
- Integrations to postpone

## Output

Create `triage/feasibility_report.json`:

```json
{
  "assessment": "PASS",
  "confidence": 0.85,
  "summary": "Project is feasible for rescue with moderate effort",
  "effort": {
    "estimated_hours": 45,
    "with_buffer": 54,
    "hours_by_phase": {
      "backend": 20,
      "frontend": 25,
      "integration": 9
    }
  },
  "risks": [
    {
      "category": "technical",
      "severity": "medium",
      "description": "DataTable component uses custom virtualization",
      "mitigation": "Consider using template DataTable instead"
    },
    {
      "category": "scope",
      "severity": "low",
      "description": "Stripe integration not documented",
      "mitigation": "Defer to phase 2"
    }
  ],
  "blockers": [],
  "go_no_go": {
    "total_hours_ok": true,
    "manual_ratio_ok": true,
    "no_critical_blockers": true,
    "feature_completeness_ok": true,
    "final_verdict": "GO"
  },
  "scope_recommendations": {
    "defer_features": ["Payment processing", "Analytics dashboard"],
    "skip_components": ["AdvancedCharts"],
    "use_template_defaults": ["DataTable", "RichTextEditor"]
  },
  "success_probability": {
    "percent": 85,
    "factors": [
      "+20%: Clean styling (mostly Tailwind)",
      "+15%: Simple state management",
      "-10%: 3 MANUAL components",
      "-5%: Undocumented Stripe integration"
    ]
  }
}
```

Also output human-readable summary to stdout:

```
=== FEASIBILITY ASSESSMENT ===

Verdict: PASS (85% confidence)

Effort: 45 hours (54 with buffer)
  - Backend: 20h
  - Frontend: 25h
  - Integration: 9h

Risks: 2 identified (0 critical)

Recommendations:
  - Defer: Payment processing, Analytics
  - Use template: DataTable, RichTextEditor

Ready for triage checkpoint.
```

## Validation

- File exists and is valid JSON
- assessment is one of: PASS, PASS_WITH_CAUTION, FAIL
- All risk items have category, severity, description
- go_no_go has all required criteria
- success_probability is between 0-100

$ARGUMENTS
