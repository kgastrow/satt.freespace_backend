# Greenfield Verification - Final Implementation Check

Verify that a completed greenfield implementation satisfies the original decomposition requirements. This command inspects the codebase against each module's acceptance criteria and produces a structured pass/fail report.

## Variables
decomposition_file: $1
output_file: $2

## Instructions

### Overview

You are performing a final verification of a greenfield project implementation. All modules have been individually implemented and merged to main through the SDLC workflow. Your job is to verify that:

1. Each module's acceptance criteria are satisfied in the codebase
2. Cross-module integration is sound (modules that depend on each other actually work together)
3. No critical gaps exist between the specification and the implementation

### Verification Process

For each module in the decomposition:

1. **Locate Implementation**: Use Glob and Grep to find files related to this module (models, routes, services, components, tests, migrations, etc.)
2. **Check Acceptance Criteria**: For each acceptance criterion, search for evidence that it has been implemented:
   - Look for relevant code (functions, classes, routes, components)
   - Check for test coverage of the criterion
   - Verify database models/migrations if applicable
   - Check API endpoints if applicable
   - Look for frontend components/pages if applicable
3. **Assess Completeness**: Determine what percentage of acceptance criteria have evidence of implementation

### Cross-Module Integration Checks

After verifying individual modules, check cross-module integration:

1. **Dependency Wiring**: For modules with dependencies, verify imports/references exist between them
2. **API Contracts**: If module A provides an API that module B consumes, verify the contract matches
3. **Data Flow**: Check that data models referenced across modules are consistent
4. **Route Registration**: Verify all API routers are registered in the application
5. **Frontend Integration**: Check that frontend routes and navigation include all implemented features

### Verdict Rules

**Per-module verdict:**
- `pass`: All acceptance criteria have evidence of implementation
- `partial`: >= 50% of acceptance criteria have evidence
- `fail`: < 50% of acceptance criteria have evidence

**Overall verdict:**
- `pass`: All modules pass
- `partial`: >= 80% of modules pass or partial, AND at most 1 module fails
- `fail`: Otherwise (more than 1 fail, or < 80% pass/partial)

### Important Notes

- You are verifying evidence of implementation, not running tests. Look for code that implements the criteria.
- Be thorough but pragmatic. A criterion like "Users can log in" is satisfied if there's a login endpoint, auth middleware, and login form.
- If a criterion is ambiguous, look for a reasonable implementation and mark it as met.
- Do NOT modify any code. This is a read-only verification.

## Decomposition Content

**IMPORTANT**: Read the decomposition JSON from the file at `{decomposition_file}` using the Read tool before proceeding. This file contains the module decomposition to verify against.

## Output Format

Write a JSON report (no markdown code blocks, raw JSON only) to the output file with this structure:

```json
{
  "verification_timestamp": "2026-01-15T10:30:00Z",
  "overall_verdict": "pass",
  "summary": "Brief 2-3 sentence summary of verification results",
  "modules": [
    {
      "id": "auth-core",
      "name": "Authentication & Authorization",
      "verdict": "pass",
      "criteria_total": 4,
      "criteria_met": 4,
      "criteria_details": [
        {
          "criterion": "Users can register with email/password",
          "met": true,
          "evidence": "Registration endpoint at src/api/v1/auth.py:45, RegisterSchema validates email/password"
        },
        {
          "criterion": "Role-based permissions enforced on all endpoints",
          "met": true,
          "evidence": "Permission middleware in src/middleware/auth.py, applied via dependency injection"
        }
      ],
      "implementation_files": [
        "src/api/v1/auth.py",
        "src/models/user.py",
        "src/middleware/auth.py"
      ],
      "notes": ""
    }
  ],
  "cross_module_issues": [
    {
      "modules": ["invoicing", "customer-mgmt"],
      "issue": "Invoice creation references customer model but import path is incorrect",
      "severity": "high"
    }
  ],
  "gaps": [
    "No E2E tests found for the banking integration module"
  ]
}
```

## Output

Write the JSON report to the file: `{output_file}`

Use the Write tool to create this file. The file must contain valid JSON matching the schema above -- no markdown, no code blocks, no surrounding text. Raw JSON only.
