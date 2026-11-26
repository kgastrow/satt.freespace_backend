---
name: adw-implementer-hard
description: Same job as adw-implementer, on the strongest model. Use for packages that are hard to get right - tricky concurrency, security, migrations of existing data, cross-cutting refactors, or a fix the regular implementer already failed at.
tools: Read, Edit, Write, Glob, Grep, Bash, TodoWrite
disallowedTools: Agent, Task
model_env: ADW_ORCH_HARD_MODEL
model: claude-opus-5-5
---
@include adw-implementer.md
