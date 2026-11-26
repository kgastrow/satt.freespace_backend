# Review Security

Follow the `Instructions` below to **review API endpoint security** across the application using a parallelized subagent approach. This command analyzes all API endpoints, understands their context and usage patterns, and compiles a comprehensive security report.

**IMPORTANT: This review MUST be exhaustive. You are required to:**
1. Build security context (auth architecture, tenant model, data models)
2. List ALL files in `app/backend/src/api/` using Glob
3. Spawn a subagent for EACH API file to analyze in parallel
4. Consolidate ALL findings into the final report
5. Do NOT skip any files or endpoints

## Variables

adw_id: $1 if provided, otherwise use timestamp
agent_name: $2 if provided, otherwise use 'security_reviewer'

## Instructions

### Phase 1: Build Security Context

Before spawning subagents, the main agent MUST build understanding of the application's security architecture. This context will be passed to each subagent.

#### 1.1 Authentication & Authorization Architecture
- Read auth-related code in `app/backend/src/auth/`
- Identify authentication mechanisms (JWT, sessions, API keys)
- Understand role-based access control (RBAC) implementation
- Map permission levels and scopes
- Document the auth dependency functions used in routes

#### 1.2 Multi-Tenancy Model
- Understand how `organization_id` is used for tenant isolation
- Identify which models are tenant-scoped vs global
- Check how tenant context is established and propagated
- Document the expected pattern for tenant-scoped queries

#### 1.3 Data Model Security Context
- Review models in `app/backend/src/models/`
- Identify sensitive data fields (PII, credentials, tokens)
- Understand relationships between entities
- List models that require special security attention

#### 1.4 Write Security Context Document

Write the gathered context to `security_review/context.md` with this structure:

```markdown
# Security Context

## Authentication Mechanisms
<summary of auth methods, dependencies, and patterns>

## Authorization / RBAC
<summary of permission levels and how they're enforced>

## Multi-Tenancy
<how organization_id filtering works, which models are tenant-scoped>

## Sensitive Data Models
<list of models with sensitive fields>

## Expected Security Patterns
<what correct security implementation looks like in this codebase>
```

### Phase 2: Enumerate and Dispatch Subagents

#### 2.1 List All API Files

```
Use Glob to find all Python files: app/backend/src/api/**/*.py
```

Create a list of ALL `.py` files found (exclude `__init__.py` unless it contains routes).

#### 2.2 Spawn Subagents in Parallel

For EACH API file found, spawn a subagent using the Task tool with `subagent_type: "general-purpose"`.

**CRITICAL: Spawn ALL subagents in a SINGLE message to run them in parallel.**

Each subagent should be given this prompt template (fill in the variables):

```
You are analyzing the API file `{file_path}` for security vulnerabilities.

## Security Context

{paste contents of security_review/context.md here}

## Your Task

1. Read the file `{file_path}` completely
2. Extract ALL endpoints (routes) defined in this file
3. For EACH endpoint, analyze for security issues
4. Write your findings to `security_review/findings/{filename}_findings.md`

## Analysis Checklist

For each endpoint, check:

### Authentication
- [ ] Is authentication required? (look for auth dependencies)
- [ ] Is the auth dependency correctly applied?

### Authorization
- [ ] Are permission checks in place?
- [ ] Can users access other users' data? (IDOR)
- [ ] Can regular users access admin functions?

### Tenant Isolation
- [ ] Does this endpoint access tenant-scoped data?
- [ ] Is `organization_id` filtering applied to all queries?
- [ ] Could a user access another organization's data?

### Input Validation
- [ ] Are all inputs validated with Pydantic models?
- [ ] Any raw SQL with user input? (SQL injection)
- [ ] Any shell commands with user input? (Command injection)
- [ ] Any file paths with user input? (Path traversal)

### Data Exposure
- [ ] Does the response include sensitive fields?
- [ ] Are passwords, tokens, or keys exposed?
- [ ] Is error handling leaking internal details?

### Rate Limiting & DoS
- [ ] Is this an auth endpoint without rate limiting?
- [ ] Are queries unbounded (no pagination)?

## Output Format

Write to `security_review/findings/{filename}_findings.md`:

```markdown
# Security Findings: {filename}

**File:** `{file_path}`
**Endpoints Found:** <count>

## Endpoints Analyzed

| Method | Path | Auth | Tenant-Scoped | Status |
|--------|------|------|---------------|--------|
| GET | /path | Yes | Yes | Issues Found |

## Vulnerabilities

### VULN-{filename}-001: <Title>

**Severity:** critical|high|medium|low|info
**Endpoint:** `METHOD /path`
**Line:** <line number>
**CWE:** CWE-XXX

**Description:**
<what the vulnerability is>

**Impact:**
<what an attacker could do>

**Code:**
```python
<vulnerable code snippet>
```

**Remediation:**
```python
<fixed code>
```

---

(repeat for each vulnerability)

## Summary

- Endpoints analyzed: X
- Critical: X
- High: X
- Medium: X
- Low: X
- Info: X
```
```

#### 2.3 Verify All Subagents Complete

After spawning all subagents, wait for ALL to complete. Verify that a findings file exists for EVERY API file.

### Phase 3: Cross-Cutting Analysis

After subagents complete, the main agent should analyze cross-cutting concerns:

#### 3.1 CORS Configuration
- Check CORS settings in app configuration
- Identify overly permissive origins

#### 3.2 Security Headers
- Check for missing security headers (CSP, HSTS, X-Frame-Options)

#### 3.3 Secrets Management
- Hardcoded credentials or API keys
- Secrets in logs or error messages

#### 3.4 Cryptography
- Weak hashing algorithms
- Missing encryption for sensitive data

Write cross-cutting findings to `security_review/findings/cross_cutting_findings.md`

### Phase 4: Consolidate Final Report

Read ALL findings files from `security_review/findings/` and consolidate into the final report at `security_review/APIs.md`.

**Severity Levels:**
- `critical`: Actively exploitable, immediate remediation required
- `high`: Significant security risk, fix within current sprint
- `medium`: Moderate risk, should be addressed soon
- `low`: Minor security concern, fix when convenient
- `info`: Security observation, not necessarily a vulnerability

### Output Format

Write the final consolidated report to `security_review/APIs.md`:

```markdown
# API Security Review

**Review Date:** <date>
**API Files Reviewed:** <count>
**Endpoints Analyzed:** <count>
**Security Score:** <0-100>

## Executive Summary

<3-5 sentence overview of security posture and critical findings>

---

## Vulnerability Summary

| ID | Severity | Title | Endpoint | File | CWE |
|----|----------|-------|----------|------|-----|
| VULN-001 | :red_circle: Critical | SQL Injection in search | `GET /api/users/search` | `users.py:45` | CWE-89 |
| VULN-002 | :red_circle: Critical | Missing tenant isolation | `GET /api/reports` | `reports.py:23` | CWE-284 |
| VULN-003 | :orange_circle: High | IDOR on user profile | `GET /api/users/{id}` | `users.py:67` | CWE-639 |
| VULN-004 | :yellow_circle: Medium | No rate limiting | `POST /api/auth/login` | `auth.py:12` | CWE-307 |

**Totals:** :red_circle: X Critical | :orange_circle: X High | :yellow_circle: X Medium | :blue_circle: X Low | :white_circle: X Info

---

## Files Reviewed

All API files in `app/backend/src/api/` were inspected:

| File | Endpoints | Vulnerabilities | Status |
|------|-----------|-----------------|--------|
| `users.py` | 5 | 2 | :orange_circle: |
| `auth.py` | 3 | 1 | :yellow_circle: |
| `health.py` | 1 | 0 | :white_circle: |

**Total Files:** <count>
**Total Endpoints:** <count>

---

## Authentication & Authorization Architecture

<Brief description of auth mechanisms and any architectural concerns>

---

## Endpoint Inventory

| Method | Path | Auth Required | Permissions | Sensitivity |
|--------|------|---------------|-------------|-------------|
| GET | /api/v1/users | Yes | authenticated | high |
| POST | /api/v1/auth/login | No | public | critical |

---

## Critical Vulnerabilities

### VULN-001: <Title>

**Severity:** critical
**Endpoint:** `METHOD /path`
**File:** `path/to/file.py:line`
**CWE:** CWE-XXX (if applicable)

**Description:**
What the vulnerability is and how it can be exploited.

**Impact:**
What an attacker could achieve by exploiting this.

**Remediation:**
```python
# Code fix suggestion
```

---

## High Severity Issues

### VULN-002: <Title>

<Same format as critical>

---

## Medium Severity Issues

<Same format>

---

## Low Severity Issues

<Same format>

---

## Cross-Cutting Security Concerns

### CORS Configuration
<findings>

### Security Headers
<findings>

### Secrets Management
<findings>

---

## Security Observations

| Category | Observation | Recommendation |
|----------|-------------|----------------|
| Logging | No audit trail for user deletions | Add audit logging |

---

## Endpoint Security Matrix

| Endpoint | Auth | AuthZ | Input Val | Tenant Iso | Rate Limit | Status |
|----------|------|-------|-----------|------------|------------|--------|
| `GET /users` | pass | pass | warn | pass | fail | review |
| `POST /login` | N/A | N/A | pass | N/A | pass | pass |

Legend: pass, warn, fail, review, N/A

---

## Remediation Priority

### Immediate (This Sprint)

- [ ] **[VULN-001]** Fix SQL injection in user search - `app/backend/src/api/users.py`
- [ ] **[VULN-002]** Add tenant isolation to reports endpoint - `app/backend/src/api/reports.py`

### Short Term (Next 2 Sprints)

- [ ] **[VULN-003]** Implement rate limiting on auth endpoints
- [ ] **[VULN-004]** Add input validation to file upload

### Long Term (Backlog)

- [ ] **[OBS-001]** Enhance audit logging coverage
- [ ] **[OBS-002]** Implement security headers middleware

---

## Appendix: Security Checklist

### Per-Endpoint Checklist
- [ ] Authentication required (if not public)
- [ ] Authorization/permission check
- [ ] Organization ID filtering (if tenant-scoped)
- [ ] Input validation with Pydantic
- [ ] No sensitive data in response (unless necessary)
- [ ] Appropriate error handling (no stack traces)
- [ ] Rate limiting (if applicable)
- [ ] Audit logging (for sensitive operations)

### OWASP Top 10 Coverage
- [ ] A01:2021 - Broken Access Control
- [ ] A02:2021 - Cryptographic Failures
- [ ] A03:2021 - Injection
- [ ] A04:2021 - Insecure Design
- [ ] A05:2021 - Security Misconfiguration
- [ ] A06:2021 - Vulnerable Components
- [ ] A07:2021 - Auth Failures
- [ ] A08:2021 - Data Integrity Failures
- [ ] A09:2021 - Logging Failures
- [ ] A10:2021 - SSRF
```

**Notes:**
- Omit any section that has no findings
- Use severity emoji prefix: :red_circle: critical, :orange_circle: high, :yellow_circle: medium, :blue_circle: low, :white_circle: pass
- Renumber all vulnerabilities sequentially in the final report (VULN-001, VULN-002, etc.)
- Include CWE references where applicable
- Provide concrete, actionable remediation steps

---

## Review Guidelines

### Critical Rules to Always Check

1. **Tenant Isolation**: Every query on tenant-scoped data MUST filter by `organization_id`
2. **Authentication**: All non-public endpoints MUST verify authentication
3. **Authorization**: Permission checks MUST happen before data access
4. **Input Validation**: All user input MUST be validated before use
5. **No Sensitive Data Exposure**: Passwords, tokens, keys MUST NOT appear in responses or logs

### Security Antipatterns to Flag

- Raw SQL queries with string interpolation
- `eval()`, `exec()`, or dynamic code execution
- Hardcoded secrets or credentials
- Disabled security features (even temporarily)
- Overly permissive CORS (`*` origins)
- Missing `await` on async security checks
- Trust of client-provided IDs without verification
- Using user input in file paths without sanitization

### What to Ignore

- Test files (may contain intentional vulnerabilities for testing)
- Migration files (schema only, no runtime code)
- Development-only configurations (if clearly separated)
- Third-party/vendor code (report separately if vulnerable)

### Output Notes

- Be thorough but prioritize exploitable vulnerabilities
- Provide proof-of-concept attack scenarios for critical issues
- Include specific file paths and line numbers
- Calculate security_score based on: (endpoints without issues / total endpoints) * 100
- Consider both the likelihood and impact of each vulnerability
