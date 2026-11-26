# Domain Context Documentation

Vertical, per-domain context maps (business purpose, entities, business rules, API & UI surface, workflows). These complement the horizontal technical docs in `ai_docs/backend/context/` and `ai_docs/frontend/context/`.

- **Technical context docs** (`backend/context/`, `frontend/context/`) describe *how the stack works* — auth, crud, models, multitenancy, i18n, etc. They cut across all features.
- **Domain context docs** (this directory) describe *what a business domain is* — e.g. Customer Management, Inspections, Billing — its data model, rules, and end-to-end workflows.

Generated and kept current by the `/document_domains` command:

- After a **greenfield** build, the orchestrator fans out one subagent per decomposed module to document every domain.
- During normal **SDLC** runs, the `--changed` mode updates only the domain(s) the change touched.

Each domain doc is registered in `.claude/commands/conditional_context.md` under **Domain Context** so future ADWs load the relevant map automatically.

| Domain | Doc | Audience | Purpose |
|--------|-----|----------|---------|
| _(none yet — populated by `/document_domains`)_ | | | |
