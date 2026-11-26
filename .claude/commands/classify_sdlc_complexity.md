# Classify SDLC Complexity

Analyze a GitHub issue to determine if it requires single-phase or multi-phase SDLC.

## Input

$ARGUMENTS - JSON with issue number, title, body

## Classification Criteria

You are classifying a **feature** request. Analyze the issue to determine if it requires single-phase or multi-phase SDLC implementation.

### Multi-Phase Indicators

If ANY of the following apply, classify as **multi-phase**:

1. **Full-stack changes**: Both backend AND frontend work required
   - Backend: new API endpoints, database models, migrations, CRUD operations
   - Frontend: new components, pages, state management, API integration

2. **Authentication/Authorization features**:
   - Login, logout, session management
   - Role-based access control
   - Impersonation, SSO, OAuth
   - Permission systems

3. **Database model + API + UI for same feature**:
   - New entity with complete CRUD
   - Complex data relationships

4. **Multiple integration points**:
   - Third-party API integrations
   - Webhook implementations
   - Background job systems

5. **Keywords indicating complexity**:
   - "dashboard", "analytics", "reporting"
   - "impersonation", "audit", "logging"
   - "workflow", "pipeline", "integration"
   - "multi-tenant", "organization"

6. **Estimated scope**:
   - 10+ files to create or modify
   - 3+ new components/modules
   - Touches multiple domains (auth, billing, users, etc.)

### Single-Phase Indicators

Classify as **single-phase** when:

- UI-only changes (styling, layout, component tweaks)
- Backend-only API changes (single endpoint, minor logic)
- Simple additions without cross-cutting concerns
- Bug fixes that became features
- Documentation or configuration changes
- Single component or module scope

## Instructions

1. Read the issue title and body carefully
2. Look for indicators from the criteria above
3. When in doubt, prefer **single-phase** (conservative choice)
4. Provide brief reasoning for your decision

## Output Format

Respond ONLY with a JSON object in this exact format:

```json
{
  "complexity": "single-phase",
  "reasoning": "Brief 1-2 sentence explanation"
}
```

Valid values for `complexity`: `"single-phase"` or `"multi-phase"`

Do NOT include any text before or after the JSON.
