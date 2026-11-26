# Orchestrated SDLC (`adw_orchestrated_sdlc_iso.py`)

A faster SDLC workflow, and the default one: the SDLC router and the Ore trigger send every issue here
(`ADW_ORCHESTRATED=0` / `ORE_WORKFLOW=router` bring back the classic pipelines). The fixed pipelines
(plan > build > test > review > ...) are replaced by one orchestrator agent. It decides the workflow for each
issue and runs the work through subagents, in parallel where it can.

```bash
uv run adws/adw_orchestrated_sdlc_iso.py <issue-number> [adw-id] [--fresh] [--dry-run]
```

## How it works

1. **Setup is done by script, not by an LLM** (step `setup`):
   - It takes a **workflow slot** from the machine-wide resource registry (see below); the Ore trigger has
     usually taken it already. Started by hand with none free, it waits ("Waiting for a free slot").
   - The script fetches the issue and classifies it. The router's decision is used when it routed here;
     otherwise one tool-less Haiku call gives the type and the branch slug.
   - It creates the worktree under `trees/<adw_id>` from `origin/main`.
   - It **leases** a port pair and a Redis database from the registry, held while the workflow runs, so no two
     ADWs on the machine (in any codebase) get the same ones. None free: it exits with code 75 and the Ore
     trigger puts the issue back in the queue.
   - It creates the isolated Postgres database and writes `.ports.env`, the `.env` files and `config.json`
     with the leased ports and Redis database (`adw_modules/env_setup.py`). `app/frontend/.env` is copied from
     the main checkout (it is gitignored) without its backend URLs, so the frontend and its tests get the
     build-time settings such as `VITE_ORG_SLUG`.
   - It installs the dependencies. `app/backend/.venv` and `app/frontend/node_modules` are cloned from the
     main checkout: APFS `cp -c -R` on macOS, so the copy is near instant. The cloned venv is relocated and
     checked, then synced with `uv pip install -r requirements.txt`. `npm ci` runs only when
     `package-lock.json` differs from the main checkout.
   - It runs the migrations (`alembic upgrade head`) and starts the app with `scripts/start.sh`, which also
     generates the API types. The script polls for the app to come up; it doesn't use fixed sleeps.
2. **One orchestrator session** (`claude -p --input-format stream-json`, Opus 5.5) runs in the worktree. Its
   prompt is `adws/orchestrator/orchestrator_prompt.md`, sent as the first message on stdin; stdin stays open so
   Ore's messages can be injected later (see [Messages from Ore](#messages-from-ore)):
   - **Plan.** The orchestrator writes a real plan before any work starts: approach, packages (files, the
     subagent, dependencies), test plan, risks and assumptions. It commits it as
     `specs/orchestrated/issue-<n>-<adw_id>.md`, posts it on the issue (`adw_report.py comment --file`) and
     records the packages (`adw_report.py plan`), which marks step `plan` done.
   - **Work.** Every package whose dependencies are done is launched in the same message (several Agent
     calls). Subagents run **in the background**: the Agent call returns at once, the orchestrator's turn may
     end, and each report arrives as a new message when the subagent finishes, so the packages run in
     parallel. Subagents implement their package and run only the tests for the code they touched, using
     `adw_run_suites.py targeted`. That command fails when no tests are collected.
   - **Checks on the changed code** (step `integrate`, labelled "Checks"). The orchestrator runs
     `adw_run_suites.py changed`, not the full suites: the frontend build when frontend files changed, ruff and
     eslint on the changed files, the backend tests that import a changed module plus the changed test files,
     and `vitest related` for the changed frontend files. It fixes failures, or delegates them, until these are
     green, and runs them again after review fixes.
   - **Screens.** When the change touches the frontend, the orchestrator launches an `adw-ui-checker` after the
     checks are green: it signs in the way the repo's Playwright e2e tests do, opens the affected routes on the
     worktree's running app at a desktop and a mobile viewport, saves screenshots in
     `agents/<adw_id>/screens/` (outside the repo) and reports anything visibly broken. The orchestrator uploads
     them (`adw_report.py image`, see [Screenshots](#screenshots)), comments them on the issue and puts them in
     the PR body; Ore shows them on the part. Visible problems caused by the change are fixed first.
     Backend-only changes skip the step (`screens` skipped).
   - **Review (mandatory).** The orchestrator launches a new `adw-reviewer` each round: fresh context, Opus,
     read-only. The reviewer checks the full diff against the issue. If it reports blockers, the
     orchestrator fixes them, reruns the checks and starts a new reviewer. This repeats until a reviewer
     passes, for at most `ADW_ORCH_MAX_REVIEW_ROUNDS` rounds. If no round passes, the run fails and lists the
     open blockers.
   - **Full check, once, at the end** (step `check`). With the review passed and the docs committed, the
     orchestrator runs `adw_report.py check`. In an Ore run the full suites run once for the whole batch (see
     [The full check](#the-full-check-once-per-batch)); outside one, the command runs `adw_run_suites.py full` on
     the branch. Failures the branch caused are fixed and checked again, at most `ADW_ORCH_MAX_CHECK_ROUNDS`
     times. Failures already on main, or that only appear with the other branches merged and lie outside the
     branch's files, go in the PR.
   - **Docs and PR.** The orchestrator makes small doc updates before the full check, then runs `adw_report.py pr`. That
     command pushes the branch, opens the PR (or finds the open one), comments the link on the issue and
     records step `pr`.
3. **The script checks the result.** It needs a review that passed and a PR. If the session ended after a
   passing review but before the PR, the script opens the PR itself. Steps that a dead session left running
   are marked failed.

## Subagents

The subagents are defined in `adws/orchestrator/subagents/*.md` and passed to the CLI with `--agents`.
`--agents` is used instead of `.claude/agents/` because the worktree is created from `origin/main`, which
may not have those files yet. Tool limits are enforced by the CLI, not by the prompts:

| Agent | Tools | Model (env) |
|---|---|---|
| `adw-implementer` | Read, Edit, Write, Glob, Grep, Bash, TodoWrite | `claude-sonnet-5-5` (`ADW_ORCH_IMPL_MODEL`) |
| `adw-implementer-hard` | same | `claude-opus-5-5` (`ADW_ORCH_HARD_MODEL`) |
| `adw-investigator` | Read, Grep, Glob, read-only Bash | `claude-haiku-5-5` (`ADW_ORCH_INVESTIGATE_MODEL`) |
| `adw-reviewer` | Read, Grep, Glob, read-only Bash | `claude-opus-5-5` (`ADW_ORCH_REVIEW_MODEL`) |
| `adw-ui-checker` | Bash, Read, Glob, Grep (no Edit/Write) | `claude-sonnet-5-5` (`ADW_ORCH_UI_MODEL`) |

None of the subagents can launch further agents. On the read-only agents and `adw-ui-checker`, Edit and Write
are disallowed (the UI checker needs Bash for Playwright and writes only its screenshot folder).
Their Bash calls go through `adws/orchestrator/readonly_guard.py`, a PreToolUse hook that blocks anything
except read-only commands. The hook is set both on the agent and in the session, keyed on the agent type.

## Progress (what Ore draws)

Everything is recorded in `agents/<adw_id>/steps.jsonl` (`adw_modules/steps.py`). The top-level steps are
`route`, `setup`, `plan`, `work`, `integrate` (the checks on the changed code), `screens`, `review`, `docs`,
`check` (the full check) and `pr`.

- Work packages are children of `work`, labelled with the package name, and are listed as pending once
  they are planned.
- Each review round is an attempt on `review` (`Round 1: 2 blockers: ...`, then `Round 2: passed`).
- A run of the checks after a failed one is a new attempt on `integrate`; a full check after a failed one is a
  new attempt on `check`. While a workflow waits for the batch's full check, step `check` says what for
  ("Waiting for #42 to finish", "Running the full suites: ...").

Milestones are posted as `[ADW-AGENTS]` issue comments, which also feed Ore's log. The final comment,
"Orchestrated SDLC workflow completed: <PR URL>", marks the workflow done for the trigger.

The orchestrator reports through two scripts. Run either with `--help` for details.

- `uv run adws/adw_report.py step|plan|comment|pr|reply|ask|wait|image|check|result ...`
- `uv run adws/adw_run_suites.py changed|full|targeted ...`

## Merging from Ore, and the workflow report

When an orchestrated workflow finishes, the orchestrator writes a report of the work (`## Summary`, `## Decisions`,
`## Not done`, `## Pending`, `## Caveats`) with `adw_report.py result --report-file`. It's kept as
`agents/<adw_id>/report.md`, posted on the PR as "Workflow report", and shown in Ore on the workflow's page.

Ore's **Merge** button starts the Ore trigger with `--ore-merge <n>` (or run `uv run adws/adw_merge_iso.py <n>`):
when the PR conflicts with main, main is merged into its branch (in the workflow's own worktree when it's still
there and clean, else `trees/merge-pr-<n>`) and Claude (`ADW_MERGE_MODEL`, default `claude-opus-5-5`) resolves the
conflicts using the issue, the PR and the workflow report; it writes notes (what it kept from each side and why),
or stops with `CANNOT_RESOLVE` when a person has to decide. The merge commit is pushed (never forced), the notes go
on the PR, the PR's checks are waited for (`ADW_MERGE_CHECKS_MIN`, default 30), and it's merged with the
repository's method. Failing checks stop it. Then the main checkout (where the trigger and the workflows run
from) is fast-forwarded to the merged branch, but only when it is on that branch with no local changes; otherwise
the step is skipped with the reason. When the merge changed `adws/`, restart Ore so the trigger uses the new
scripts. Files: `agents/merges/pr-<n>/`.

## Follow-ups

A finished workflow can be asked for more from Ore ("Follow up" on its page, e.g. one of the report's caveats):
the same ADW continues, in the same worktree and branch, and the same pull request updates. The Ore trigger queues
it again (message mode `follow_up`; Ore restarts a finished run with `--resume <run-dir> --follow-up <request>`),
writes the request to `agents/<adw_id>/followup.json` and starts `adw_orchestrated_sdlc_iso.py <issue> <adw_id>
--follow-up`. That records a new round of steps (`steps.new_round`: everything but route and setup starts again),
leases resources and starts the app again, and resumes the orchestrator's session with the request as its next
instruction: a short plan, the work, checks, review, docs and a push, then an updated workflow report with a
`## Follow-up <n>` section, posted on the PR as "Workflow report (updated)". The full check is the orchestrator's
call in a follow-up: it runs it when the round's changes reach beyond what the checks on the changed code cover
(shared code, models or migrations, APIs, config, dependencies, many files, or a fix for the last full check's
failures), and otherwise records step `check` as skipped, saying why in the step's note and the report. It needs the worktree
and the orchestrator session (gone after Delete); a workflow still running gets a follow-up as a change instead.

## The full check, once per batch

Running the full suites in every workflow, in every round, made a batch slow: four workflows each running the
full build, pytest, vitest and lint at once on one Mac, each with a fraction of the cores, each finding the same
failures that were already on main and trying to fix them. Now the workflows check only their changed code while
they work, and the full suites run once at the end, for all of them together:

1. A workflow that is done (review passed, docs committed) runs `adw_report.py check`. That writes
   `{"type": "check", "n", "sha", "branch"}` to its outbox and waits (55 minutes per call; the orchestrator calls
   it again while it waits). The time spent waiting doesn't count against `ADW_ORCH_TIMEOUT_MIN`.
2. The Ore trigger collects the requests. Once every running orchestrated workflow of the run has asked, or the
   first has waited `ORE_CHECK_MAX_WAIT_MIN` (default 30), it starts `adw_batch_check.py` in the background with
   the waiting branches (`agents/ore/<run-id>/checks/<n>/request.json`).
3. The check (`adw_modules/batch_check.py`) works in a throwaway worktree, `trees/check-<run-id>`, detached at
   origin/main. It merges each branch's commit (issue order, `--no-ff`); a branch that conflicts with an earlier
   one is left out and told which files and branches. It installs the dependencies (cloned from the main checkout),
   copies the config files and generates the API types from the merged backend's `openapi()` without starting
   it. Then it runs the full suites in a machine-wide full-suite slot with most of the cores (`ADW_CHECK_WORKERS`,
   default 3/4 of them) and longer timeouts (`ADW_CHECK_TIMEOUT_SCALE`, default 1.5). The backend tests need
   no database or Redis lease: they use an in-memory database and fake Redis.
4. When something fails, it finds the cause. It reruns just the failing items on origin/main: test ids, test
   files, tsc errors and lint findings, matched by file and code rather than line number. Those that fail there
   are `preexisting`. The rest it reruns on each branch alone: those are `yours` for the branches where they
   fail. What fails only with the branches merged together is `combined` and goes to every merged branch. A suite
   that stopped without naming failures (a timeout, a crash) is `unknown`.
5. `result.json` and a `report-<adw_id>.md` per branch (the failures with their output) go to the check's folder.
   The trigger puts each workflow's part in its inbox (`{"type": "check_result", "n", "status": "green|failed|
   conflict|error", "yours", "combined", "preexisting", "unknown", "report"}`) and records step `check`.
   `adw_report.py check` prints it. The workflow fixes what is `yours` and asks again (a new commit, a new check,
   together with whichever workflows are waiting then), or goes on to the PR when it is green. A branch that
   conflicted asks again and is checked on its own straight away. If the check couldn't run at all, `check`
   runs the full suites on the branch instead.

Deleting the run in Ore stops a running check and removes its worktree with the rest.

## Messages from Ore

Ore can message a running part (or the whole run): **ask** (a question, answered without stopping), **amend**
(take this into account from now on), **pause** (stop at the next safe point) and **resume**. The path:

1. Ore sends `{"type": "message", "id", "part", "text", "mode"}` on the trigger's stdin. The trigger says it
   takes messages (`"accepts": ["message"]` in every status) and reads stdin in a thread, so a message can
   arrive at any time, also while one of its own questions is open.
2. The trigger appends it to `agents/<adw_id>/inbox.jsonl` of the part's workflow, or of every running workflow
   for part null. A workflow still queued gets it when it starts; a finished one gets a reply saying so.
3. The workflow tails its inbox and injects each message into the orchestrator session as a stream-json user
   message with `priority: "next"`, so it arrives at the orchestrator's next tool boundary:
   `[Message from Konrad (ask), id m1]: How far are you?` plus what to do for the mode: answer with
   `adw_report.py reply <id> "..."` and continue (ask); adjust the plan, re-brief the packages it affects,
   acknowledge (amend); finish or let the running subagents report, commit work in progress, acknowledge, then
   run `adw_report.py wait`, which blocks until a resume or amend message (pause); continue (resume).
   Subagents can't be messaged: the orchestrator relays what matters in their next brief.
4. `adw_report.py reply` appends to `agents/<adw_id>/outbox.jsonl`; the trigger tails the outboxes and sends
   `{"type": "reply", "to", "part", "text"}` to Ore, shown under the message.

The orchestrator can ask the user too, sparingly: `adw_report.py ask "<question>" [--options a,b]` writes the
question to the outbox and blocks until the answer, up to 55 minutes per call; the question stays open, so the
orchestrator runs `ask --wait <n>` again, and the time waiting doesn't count against `ADW_ORCH_TIMEOUT_MIN`
(`ADW_ASK_TIMEOUT_MIN` makes it give up after that long instead). The trigger asks it in Ore as an
`input_request` with id `ask-<issue>-<n>` (a choice when there are options, else text), one open at a time per
run (others queue), and shows the part as `input`. The answer goes back through the inbox and `ask` prints it.
Only when it gives up (`ADW_ASK_TIMEOUT_MIN`) does `ask` tell the orchestrator to decide itself and note the
assumption; a late answer still reaches it as a message. `ask` and `wait` block longer than Claude Code's default Bash limit, so the
session runs with `BASH_MAX_TIMEOUT_MS=3900000` and the prompt says to call them with a 3600000 ms timeout.

While a workflow is paused, the time doesn't count against `ADW_ORCH_TIMEOUT_MIN`. The files are described in
`adw_modules/messages.py`.

## Usage and limits

The workflow reads the orchestrator's stream: each `result` message's `total_cost_usd` and `modelUsage`
(cumulative per claude process, including the subagents; a resumed session is a new process, so the processes
are summed) and every `rate_limit_event`. It keeps `agents/<adw_id>/usage.json`:
`{cost_usd, input_tokens (incl. cache writes), output_tokens, cache_read_tokens, models: {model: {cost_usd,
input_tokens, output_tokens}}, limit: {status, kind, resets_at, used_percent}, waiting_until}`. The trigger
sends it as each part's `usage`, and the sum (plus the clarification turns) as the run's. Claude Code 2.1 sends,
for example:

```json
{"type": "rate_limit_event", "rate_limit_info": {"status": "allowed", "resetsAt": 1794214800,
 "rateLimitType": "seven_day", "overageStatus": "allowed", "isUsingOverage": false,
 "unifiedWindows": {"seven_day": {"utilization": 0.31, "resetsAt": 1794214800, "status": "allowed"}}}}
```

which becomes `limit: {"status": "allowed", "kind": "seven_day", "resets_at": "2026-11-…", "used_percent": 31}`.

When the session stops on a usage limit (an error result that `agent._classify_transient_error` recognises), the
workflow waits until the limit's reset time (from the latest rate-limit event, plus a minute; 15 minutes when
there is none, e.g. an API overload), comments "Claude usage limit reached until HH:MM", writes `waiting_until`
(the part shows "Claude usage limit reached until HH:MM"), answers messages meanwhile that the orchestrator gets
them when it continues, and then resumes the session. At most `ADW_ORCH_MAX_LIMIT_WAITS` waits; a reset more
than `ADW_ORCH_MAX_LIMIT_WAIT_HOURS` away fails the workflow (Resume continues it later).

Every `rate_limit_event` any ADW claude process sees (the orchestrator's stream, the classic agents' output,
the trigger's own clarification turns) also goes machine-wide into `~/.adw/usage.json`: the latest figure per
window (`five_hour`, `seven_day`, ...), with `as_of`. Ore's Home page shows it through the `machine` query
(below).

## Screenshots

`adw_report.py image "<label>" <png>` uploads a screenshot and records it in `agents/<adw_id>/images.jsonl`
(shown in Ore as the part's `images`); `adw_report.py pr` adds a `## Screenshots` section with any the PR body
doesn't show yet. Uploads (`adw_modules/image_upload.py`):

- **Cloudflare R2**, when `CLOUDFLARE_*` is set in `.env` (the uploader the old smoke test and review used): a
  public URL every viewer can load, Ore included.
- Otherwise a commit on the repo's **`adw-screenshots` branch** (`ADW_SCREENSHOT_BRANCH`), an orphan branch
  that only holds screenshots (`<adw_id>/<file>.png`), pushed with the repo's own git credentials; the URL is
  `https://github.com/<owner>/<repo>/raw/adw-screenshots/<adw_id>/<file>.png`. GitHub comments and PRs show it
  to anyone with access to the repo; for a private repo Ore can only show the link (the image needs a GitHub
  sign-in). GitHub's comment attachments have no API, so they can't be used.

## Using it (the default)

- **From Ore:** `trigger_ore.py` starts `adw_orchestrated_sdlc_iso.py` for each issue (`ORE_WORKFLOW=router`
  starts the SDLC router instead). Resume and `--cleanup` work as before: cleanup removes the worktree, local
  branch, databases and resource leases of every ADW the run started. With `--dry-run`, each workflow
  simulates an orchestrated run, including parallel packages and a failed review round.
- **Rehearsal without Claude or GitHub:** `trigger_ore.py <items> --simulate` (or `--simulate` alone, with
  three sample items; in Ore, put `--simulate` in the workspace's extra arguments). It asks one canned round of
  questions and the group review in Ore, "creates" fake issues and runs simulated orchestrated workflows (about
  3 minutes: parallel packages, checks on the changed code that fail once then pass, a review round with blockers
  then a passing one, the full check, a PR link), sending the same stages, parts and steps as a real run, plus checkpoint and cleanup.
  It also exercises the newer protocol: it accepts messages (a simulated orchestrator answers asks and amends
  through the real inbox/outbox files, and pause stops its clock until resume), posts a plan comment, asks the
  user one question after the plan (`ask-<issue>-1`), shows a `screens` step with two placeholder screenshots
  (placehold.co) and sends usage numbers. `adws/adw_tests/ore_harness.py --messages -- adws/adw_triggers/
  trigger_ore.py --simulate` runs it the way Ore does, answering and messaging automatically.
  The workflows lease real slots, ports and Redis databases from the registry (and give them back), but no
  worktree or app is started. `ORE_SIM_SPEED=10` makes it 10 times faster.
- **Through the router:** `adw_sdlc_router_iso.py` routes every issue here, recording the route as
  "Orchestrated SDLC", unless `ADW_ORCHESTRATED=0`.
- **Directly:** `uv run adws/adw_orchestrated_sdlc_iso.py 123`.
- **Offline:** `uv run adws/adw_orchestrated_sdlc_iso.py 123 --dry-run` records a simulated run (steps and
  local progress comments). It doesn't call Claude or GitHub or create a worktree.

## Machine-wide resources (all codebases on one machine)

Several codebases (and several Ore runs) share one machine, so ports, Redis databases and CPU are handed out
by one registry for the whole machine, `~/.adw/resources.json` (`ADW_SHARED_DIR` moves the folder), guarded by
an `fcntl` lock: `adw_modules/resources.py`.

- **Leases**, keyed by `adw_id`: the codebase (repo root and name), pid / process group, host, created and
  heartbeat times, and what is held: a backend + frontend port pair from `ADW_BACKEND_PORTS` /
  `ADW_FRONTEND_PORTS` (9100-9199 / 9200-9299; ports any process listens on are skipped), a Redis database from
  `ADW_REDIS_DBS` (2-14 and 30-164, clamped to the server's `databases`; 0-1 belong to the main app and 15-29 to
  the Playwright e2e runs), and the isolated Postgres database name.
- **Slots**: `workflow` (`ADW_MAX_WORKFLOWS`, default 4: full suites saturate a 10-core Mac) and `full_suite`
  (`ADW_MAX_FULL_SUITES`, default 2).
- **Reclaiming**: a lease or slot whose pid is dead on this host, or whose heartbeat is older than
  `ADW_LEASE_TTL_HOURS` (24), is reclaimed automatically on the next access. The classic workflows' leases
  live as long as their worktree. The orchestrated workflow releases its lease and slot when it finishes,
  fails or gets SIGTERM; the trigger releases them when a workflow ends and on `--cleanup`.
- **Waiting**: a workflow the Ore trigger has queued for a slot is noted in the registry's `waiting` (only for
  display; dropped when it gets its slot, when the trigger is gone, or after 15 minutes without a refresh).
- **Inspect**: `uv run adws/adw_resources.py status` (all codebases), `release <adw_id>`, `gc`.
- Limits and pools can be set for the whole machine in `~/.adw/config.json`
  (`{"max_workflows": 5, "max_full_suites": 2, ...}`); the environment wins.
- `ADW_RESOURCES=static` brings back the old static split (`ADW_CODEBASE_INDEX` / `ADW_MAX_CODEBASES` slice
  9100-9114 / 9200-9214 and Redis 2-14 between codebases). The codebase index still names the Postgres
  databases and the e2e ports / Redis database in either mode.

Allocation is deterministic code, never the orchestrator agent's job: the registry is the one thing shared
across codebases, so it has to be consistent and locked; the agent only gets the ports its setup leased.

Redis is isolated by database index, not by key prefix: the app has no key prefix setting (cache, rate
limiter, ARQ and pub/sub use fixed names). Pub/sub channels are server-wide in Redis whatever the database.

## Ore's queries (Home page)

Ore's Home page asks the workspace script for data instead of starting a run. Every status the trigger sends says
`"queries": ["machine", "prs", "merge"]`; Ore then runs the trigger on its own, the same way it starts a run,
with `--ore-query <name> [args]` (environment `ORE_QUERY`, `ORE_PROTOCOL`, `ORE_WORKSPACE`, no stdin). It prints
one line, `{"type": "answer", "query": "<name>", "data": {...}}`, and exits 0, or `{"type": "error", "message":
"..."}` and exits 1. A query never starts a workflow or calls Claude, and takes a few seconds.

- `machine`: this machine's name, host, OS and a CPU estimate (load average per core); workflow and full-suite
  slots in use; every codebase's leases (project, workflow `#<issue> <title>`, adw_id, ports, Redis database,
  since); the workflows waiting for a slot; free port pairs and Redis databases; the config file; and the Claude
  usage windows from `~/.adw/usage.json` (`used_percent`, `resets_at`; a window whose reset has passed shows 0%),
  with the plan from Claude Code's login (`~/.claude.json`).
- `prs`: this repo's pull requests made by ADWs (branch `<type>-issue-<n>-adw-<id>-...`, or `ADW ID:` in the
  body), the open ones and those merged or closed in the last 14 days: number, title, url, issue, branch, adw_id,
  checks (passing / failing / pending / none), review (approved / requested / changes / none), state, merged_at,
  mergeable. Two `gh pr list` calls.
- `merge <n>`: merges ADW pull request n when it is open, with the repo's method (squash when allowed, else merge,
  else rebase), and deletes the branch on GitHub. A worktree still on this machine is left alone.

## Robustness

- **Wall-clock limit.** `ADW_ORCH_TIMEOUT_MIN` (default 240) caps the orchestrator session. When it runs
  out, the session's whole process group is killed. SIGTERM to the workflow also stops the session.
- **Usage limits and API overload.** See [Usage and limits](#usage-and-limits): the script waits until the
  limit resets (or 15 minutes) and resumes the same session, at most `ADW_ORCH_MAX_LIMIT_WAITS` times.
- **A turn that ends early.** Subagents run in the background, so the orchestrator's turn can end while they
  work; the CLI starts a new turn when they report. The script tracks running tasks (`task_started` /
  `task_notification` / `background_tasks_changed` events). If a turn ends without a result and nothing is
  running, it nudges the session ("continue, or report the result") after `ADW_ORCH_NUDGE_SECONDS`, at most 3
  times in a row.
- **The result.** The orchestrator finishes with `adw_report.py result <pr_opened|failed|dropped> --summary ...`
  (`dropped`: deliberately nothing to change, e.g. the user dropped the request; the workflow ends without a PR and
  without failing) (or
  `--json '<object>'`), which checks it against `RESULT_SCHEMA` (`adw_modules/messages.py`) and writes
  `agents/<adw_id>/result.json` atomically. The session ends when that file exists and no background task is
  running. A result written while subagents still run is removed, and the orchestrator gets a message naming them:
  wait (end the turn; their reports start a new one), then report again. `--force` gives up without waiting. Every
  session, fresh or resumed, starts with any old `result.json` removed. The session is NOT started with
  `--json-schema`: with it the CLI injects `[structured-output-enforce] You MUST call the StructuredOutput tool`
  at the end of every turn, also a turn that ends while subagents still run, and the orchestrator obeyed with a
  "failed" result (OneFan #37).
- **Resume.** The session id is saved in the ADW state (`orchestrator_session_id`). Rerunning with the same
  `adw_id` skips worktree creation, leases again (keeping the old ports when they're free), restarts the app
  and continues the session with `claude --resume <session>` and `CLAUDE_CODE_RESUME_INTERRUPTED_TURN=1`. The
  first message tells it it was interrupted: check `git status` / `git log`, the steps it reported and which
  subagents finished, relaunch only unfinished packages (telling them to continue from the files already
  changed), and carry on. Pass `--fresh` to start a new session on the same worktree. If the last session gave a
  StructuredOutput "failed" while its subagents still ran (the old `--json-schema` flow), the message also says
  that result was forced by a bug, and to continue planning from what the investigations found.
- **Resume from Ore.** The trigger's Resume (`--resume <run-dir>`) requeues a failed orchestrated workflow with
  the **same** `adw_id` when its worktree still exists and its state has `orchestrator_session_id`: no cleanup,
  the slot is taken again for that `adw_id`, and the workflow continues as above. Workflows whose process died
  while Ore was closed (still "running" in the run's state) are treated the same way. A workflow that failed in
  setup (no worktree or no session yet) starts over with a fresh ADW, as before.
- **When it fails.** The script marks the steps that were left running as failed, stops the dev servers and
  releases its lease and slot. It keeps the worktree and database so a rerun can resume (which leases again,
  keeping the old ports when they're free).

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `ADW_ORCH_MODEL` | `claude-opus-5-5` | orchestrator |
| `ADW_ORCH_IMPL_MODEL` | `claude-sonnet-5-5` | `adw-implementer` |
| `ADW_ORCH_HARD_MODEL` | `claude-opus-5-5` | `adw-implementer-hard` |
| `ADW_ORCH_REVIEW_MODEL` | `claude-opus-5-5` | `adw-reviewer` |
| `ADW_ORCH_INVESTIGATE_MODEL` | `claude-haiku-5-5` | `adw-investigator` |
| `ADW_ORCH_UI_MODEL` | `claude-sonnet-5-5` | `adw-ui-checker` |
| `ADW_ORCH_FAST_MODEL` | `claude-haiku-5-5` | issue classification and branch slug |
| `ADW_ORCH_EFFORT` | (CLI default) | `--effort` for the orchestrator |
| `ADW_ORCH_TIMEOUT_MIN` | `240` | hard limit per orchestrator session |
| `ADW_ORCH_MAX_REVIEW_ROUNDS` | `4` | review rounds before the run fails |
| `ADW_ORCH_MAX_CHECK_ROUNDS` | `3` | full checks that find failures of the branch before the run fails |
| `ADW_ORCH_MAX_LIMIT_WAITS` | `8` | waits on usage limits / overload before failing |
| `ADW_ORCH_MAX_LIMIT_WAIT_HOURS` | `12` | a usage limit resetting later than this fails the workflow |
| `ADW_ORCH_NUDGE_SECONDS` | `45` | idle time (turn over, nothing running, no result) before a nudge |
| `ADW_ASK_TIMEOUT_MIN` | `0` | give up on a question after this long and decide (0: wait for the answer) |
| `ADW_SCREENSHOT_BRANCH` | `adw-screenshots` | the branch screenshots go to without R2 |
| `BASH_MAX_TIMEOUT_MS` | `3900000` | set for the orchestrator session, so `ask` / `wait` / `check` can block |
| `ADW_ORCH_TEST_WORKERS` | `max(2, cores // running ADWs)` | test workers for `changed` and `full` in a worktree |
| `ADW_CHECK_WORKERS` | 3/4 of the cores | test workers for the batch's full check |
| `ADW_CHECK_TIMEOUT_SCALE` | `1.5` | the batch's full check: suite timeouts times this |
| `ORE_CHECK_MAX_WAIT_MIN` | `30` | how long a workflow waits for the others before the full check runs without them |
| `ADW_CHECK_LOCAL` | unset | `1`: `adw_report.py check` runs the full suites on the branch, even in an Ore run |
| `ADW_MAX_FULL_SUITES` | `2` | full-suite runs at once on this machine (all codebases) |
| `ADW_MAX_WORKFLOWS` | `4` | workflows at once on this machine (all codebases, all Ore runs) |
| `ADW_BACKEND_PORTS` / `ADW_FRONTEND_PORTS` | `9100-9199` / `9200-9299` | the machine's port pool |
| `ADW_REDIS_DBS` | `2-14,30-164` | the machine's Redis database pool |
| `ADW_LEASE_TTL_HOURS` | `24` | a lease without heartbeat for this long is reclaimed |
| `ADW_SHARED_DIR` | `~/.adw` | where the registry lives |
| `ADW_RESOURCES` | `registry` | `static`: the old per-codebase slices |
| `ADW_ORCH_KEEP_APP` | unset | `1` keeps the dev servers running after the run |
| `ADW_ORCH_DRY_DELAY` | `0.5` | seconds between simulated events with `--dry-run` |
| `ORE_WORKFLOW` | `orchestrated` | `router`: the Ore trigger starts the SDLC router instead |
| `ADW_ORCHESTRATED` | on | `0`: the SDLC router routes to the classic workflows instead |
| `ORE_SIM_SPEED` | `1` | time factor of `trigger_ore.py --simulate` |

Workflows only get a short list of variables (`adw_modules/utils.py` `get_safe_subprocess_env`: the Claude and
GitHub credentials, the system's basics and the settings above). `ADW_PASS_ENV` names more, comma or space
separated: what the app needs to start in a worktree that isn't in a file there, e.g. a key it refuses to boot
without (`ADW_PASS_ENV=FILE_ENCRYPTION_KEYS`). It can go in the repo's `.env`; the values themselves belong in
the environment the trigger starts in (e.g. `~/.zshenv` for a trigger Ore starts over SSH on a Mac).

Files written per run go to `agents/<adw_id>/orchestrator/`:

- `prompt.md` and `agents.json`: what the session got.
- `raw_output-*.jsonl`: the stream-json transcript, with subagent messages marked by `parent_tool_use_id` (the
  injected messages show as replayed user messages, `isReplay: true`, where the session took them).
- `plan.json`, `pr_body.md`, `pr_url.txt`, `app_start.log` and `inbox.offset` (how much of the inbox it
  forwarded).

And in `agents/<adw_id>/`: `inbox.jsonl`, `outbox.jsonl`, `usage.json`, `images.jsonl`, `result.json` and
`screens/`.

Suite logs go to `agents/<adw_id>/suites/`; the batch's full checks keep theirs in
`agents/ore/<run-id>/checks/<n>/` (request, status, result, reports, `suites/`, `check.log`).

## What Claude Code does (checked with claude 2.1.318)

- **Streaming input.** `claude -p --input-format stream-json --output-format stream-json --verbose` reads one
  JSON object per line: `{"type": "user", "message": {"role": "user", "content": "..."}, "priority": "next"}`.
  `priority` is optional: `next` delivers the message at the next tool boundary of the running turn (a message
  sent during a 15 s Bash call was taken right after the tool result, in the same turn); `later` waits until
  the turn ends (a separate turn follows); `now` interrupts the turn (an empty result, then a new turn). Each
  turn ends with a `result`; the session stays open for more input. Closing stdin ends the session cleanly
  (exit 0) once running background work has finished. `--replay-user-messages` echoes each taken message
  (`isReplay: true`).
- **Parallel subagents.** Several Agent calls in one message start background tasks ("Async agent launched");
  two Haiku subagents each running `sleep 20` ran at the same time (both 13:43:25 to 13:43:45), and the parent's
  turn ended before they finished. No `background: true` setting is needed.
- **Structured output.** With `--json-schema`, the CLI injects `[structured-output-enforce] You MUST call the
  StructuredOutput tool to complete this request` whenever a turn ends without it, again after every later turn,
  also when the turn ended only because background subagents are working. That is why the orchestrator doesn't
  use it. Without it (checked with claude 2.1.318 and Haiku): the model launched a background Agent, ended its turn
  (a `result`, `end_turn`), and when the agent finished (`task_notification`, `background_tasks_changed` with an
  empty list) the CLI started a new turn with its report; no enforcement. A session created with `--json-schema`
  resumes fine without it (`--resume`, streaming input): no StructuredOutput demanded, the context is kept.
- **Bash limits.** With `BASH_MAX_TIMEOUT_MS=1500000` a foreground Bash call with `timeout: 1200000` ran 11
  minutes. A foreground `sleep 30` is refused by the CLI (it suggests running it in the background); a Python
  process that blocks (like `adw_report.py ask`) is fine.
