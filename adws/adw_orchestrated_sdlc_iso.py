#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW Orchestrated SDLC Iso - one orchestrator agent plans the work and runs it with parallel subagents.

Usage: uv run adw_orchestrated_sdlc_iso.py <issue-number> [adw-id] [--fresh] [--dry-run]

1. Setup, by script (no LLM): a workflow slot and a lease from the machine-wide resource registry (ports and
   a Redis database, shared by every codebase on this machine: adw_modules/resources.py), state, issue,
   classification and branch slug (one small model call, or the router's decision), worktree, isolated
   database, dependencies (cloned from the main checkout when possible), migrations, app start and API types.
   Allocation is deterministic code, never the orchestrator's job; the agent only gets the ports it was given.
   No free port pair or Redis database: exit code 75 (EX_TEMPFAIL), which the Ore trigger re-queues.
2. One orchestrator Claude Code session (Opus) in the worktree decides the workflow: writes the plan (committed and
   posted on the issue), runs independent work packages in parallel through background subagents
   (adws/orchestrator/subagents/*.md), checks the changed code (adw_run_suites.py changed), takes screenshots of
   changed screens (adw-ui-checker), iterates an independent read-only review until it passes, updates docs, asks
   for the full check (adw_report.py check: in an Ore run the full suites run once for the whole batch, see
   adw_modules/batch_check.py; time spent waiting for it doesn't count against ADW_ORCH_TIMEOUT_MIN), commits and
   opens the PR (adw_report.py pr). It reports steps and comments through
   adw_report.py, so Ore draws the run live, and finishes with `adw_report.py result` (agents/<adw_id>/result.json):
   the session ends on that once no subagent or background command is running. No --json-schema: with it the CLI
   demands a structured result at the end of every turn, also a turn that ends while subagents still work. The session takes stream-json on stdin: Ore's messages
   (agents/<adw_id>/inbox.jsonl, written by the Ore trigger) are injected as they arrive, and its usage and
   rate-limit events go to agents/<adw_id>/usage.json.
3. The script checks the result (review passed, PR exists), opens the PR itself if the session got that far
   but didn't, and fails the steps a dead session left running.

Rerunning with the same adw-id resumes: setup is skipped when the worktree exists, and the orchestrator
session continues (`claude --resume <session>` with CLAUDE_CODE_RESUME_INTERRUPTED_TURN=1, told to check what
finished and relaunch only unfinished packages) unless --fresh. The Ore trigger's Resume does this.
--follow-up (the Ore trigger's Follow up on a finished workflow): the same ADW, worktree, branch and PR, the
orchestrator session resumed with the request in agents/<adw_id>/followup.json; its steps start a new round.
--dry-run records a simulated run (steps and progress comments, no Claude, no GitHub, no worktree).
See adws/docs/orchestrated_sdlc.md for the environment variables and models.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

ADWS_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_ROOT = os.path.dirname(ADWS_DIR)
sys.path.insert(0, ADWS_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(MAIN_ROOT, ".env"))

from adw_modules import messages, resources, steps  # noqa: E402

WORKFLOW = "Orchestrated SDLC"
AGENT_NAME = "orchestrator"
AGENTS_DIR = os.path.join(ADWS_DIR, "orchestrator", "subagents")
PROMPT_FILE = os.path.join(ADWS_DIR, "orchestrator", "orchestrator_prompt.md")
GUARD = os.path.join(ADWS_DIR, "orchestrator", "readonly_guard.py")
CLAUDE = os.getenv("CLAUDE_CODE_PATH", "claude")


def env_int(name: str, default: int) -> int:
    v = os.getenv(name, "")
    return int(v) if v.strip().isdigit() else default


ORCH_MODEL = os.getenv("ADW_ORCH_MODEL", "claude-opus-5-5")
FAST_MODEL = os.getenv("ADW_ORCH_FAST_MODEL", "claude-haiku-5-5")
ORCH_EFFORT = os.getenv("ADW_ORCH_EFFORT", "")                    # e.g. high; empty = the CLI's default
TIMEOUT_MIN = env_int("ADW_ORCH_TIMEOUT_MIN", 240)                # hard wall-clock limit per orchestrator session
MAX_REVIEW_ROUNDS = env_int("ADW_ORCH_MAX_REVIEW_ROUNDS", 4)
MAX_CHECK_ROUNDS = env_int("ADW_ORCH_MAX_CHECK_ROUNDS", 3)        # full checks that found failures of the branch
MAX_LIMIT_WAITS = env_int("ADW_ORCH_MAX_LIMIT_WAITS", 8)          # usage-limit / overload waits of 15 min
LIMIT_WAIT_SECONDS = 15 * 60                                      # overload, or a limit without a reset time
MAX_LIMIT_WAIT_HOURS = env_int("ADW_ORCH_MAX_LIMIT_WAIT_HOURS", 12)  # a usage limit resetting later than this fails
KEEP_APP = os.getenv("ADW_ORCH_KEEP_APP", "") == "1"             # leave the dev servers running at the end
DRY_DELAY = float(os.getenv("ADW_ORCH_DRY_DELAY", "0.5"))
EXIT_NO_RESOURCES = 75                                           # EX_TEMPFAIL: try again later (trigger re-queues)
SLOT_POLL_SECONDS = 30

RESULT_SCHEMA = messages.RESULT_SCHEMA     # what `adw_report.py result` writes to agents/<adw_id>/result.json


# ---- small helpers -----------------------------------------------------------

def orch_dir(adw_id: str) -> str:
    return os.path.join(MAIN_ROOT, "agents", adw_id, AGENT_NAME)


def result_path(adw_id: str) -> str:
    return os.path.join(MAIN_ROOT, "agents", adw_id, messages.RESULT)


def clear_result(adw_id: str) -> None:
    """A result.json left from an earlier session must not end the next one."""
    try:
        os.remove(result_path(adw_id))
    except OSError:
        pass


def uv_cmd(script: str) -> str:
    return f"uv run --quiet {os.path.join(ADWS_DIR, script)}"


def slugify(text: str, words: int = 6) -> str:
    parts = re.findall(r"[a-z0-9]+", (text or "").lower())
    return "-".join(parts[:words])[:50].strip("-") or "change"


def make_branch_name(issue_class: str, issue_number: str, adw_id: str, slug: str) -> str:
    kind = (issue_class or "/feature").lstrip("/")
    return f"{kind}-issue-{issue_number}-adw-{adw_id}-{slugify(slug)}"


def comment(issue_number: str, text: str, dry_run: bool = False, adw_id: str = "") -> None:
    """An [ADW-AGENTS] issue comment (dry run: only the local progress record Ore follows)."""
    from adw_modules.github import ADW_BOT_IDENTIFIER
    msg = f"{ADW_BOT_IDENTIFIER} {adw_id}_{AGENT_NAME}: {text}"     # workflow_ops.format_issue_message's format
    try:
        if dry_run:
            from adw_modules.github import _record_progress
            _record_progress(str(issue_number), msg)
        else:
            from adw_modules.github import make_issue_comment
            make_issue_comment(str(issue_number), msg)
    except Exception as e:  # noqa: BLE001 - a comment must not stop the workflow
        print(f"Couldn't post a comment: {e}", file=sys.stderr)


def heuristic_class(title: str, body: str) -> str:
    t = f"{title} {body[:400]}".lower()
    if re.search(r"\b(bug|fix|broken|error|crash|fail|regression|wrong)", t):
        return "/bug"
    if re.search(r"\b(chore|refactor|upgrade|bump|cleanup|clean up|rename|docs?)\b", t):
        return "/chore"
    return "/feature"


def classify(issue, adw_id: str, logger) -> tuple[str, str]:
    """(issue_class, branch slug) from one small, tool-less model call; heuristics if that fails."""
    schema = {"type": "object", "properties": {
        "issue_class": {"type": "string", "enum": ["feature", "bug", "chore"]},
        "slug": {"type": "string", "description": "3-6 lowercase words joined by hyphens"}},
        "required": ["issue_class", "slug"]}
    prompt = ("Classify this GitHub issue as feature, bug or chore, and give a 3-6 word kebab-case branch slug.\n\n"
              f"Title: {issue.title}\n\n{(issue.body or '')[:4000]}")
    try:
        from adw_modules.utils import get_safe_subprocess_env
        proc = subprocess.run([CLAUDE, "-p", prompt, "--model", FAST_MODEL, "--output-format", "json",
                               "--json-schema", json.dumps(schema), "--tools", "", "--no-session-persistence"],
                              capture_output=True, text=True, timeout=180, env=get_safe_subprocess_env(),
                              stdin=subprocess.DEVNULL)
        out = json.loads(proc.stdout or "{}").get("structured_output") or {}
        if out.get("issue_class") in ("feature", "bug", "chore"):
            return "/" + out["issue_class"], slugify(out.get("slug") or issue.title)
        logger.warning(f"Classification gave no usable answer: {proc.stderr.strip()[-300:]}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Classification failed: {e}")
    return heuristic_class(issue.title, issue.body or ""), slugify(issue.title)


# ---- setup -------------------------------------------------------------------

def release(state, logger) -> None:
    """Free what a stopped workflow holds while it waits for a rerun: dev servers and port reservation.
    The worktree and database stay, so a rerun resumes (trigger --cleanup removes everything)."""
    from adw_modules import env_setup
    from adw_modules.worktree_ops import release_ports
    adw_id = state.get("adw_id")
    env_setup.stop_app(adw_id, logger)
    if state.get("backend_port") and state.get("frontend_port"):
        release_ports(adw_id, state.get("backend_port"), state.get("frontend_port"))


def setup(state, issue, logger) -> None:
    """Everything the agents need, done by script. Records step "setup"; exits on failure."""
    from adw_modules import env_setup
    from adw_modules.worktree_ops import (create_worktree, find_next_available_ports, release_ports,
                                          setup_worktree_environment, validate_worktree)
    adw_id, issue_number = state.get("adw_id"), state.get("issue_number")
    resumed = bool(state.get("worktree_path")) and validate_worktree(adw_id, state)[0]
    old_ports = (state.get("backend_port"), state.get("frontend_port"))
    if all(old_ports) and not resources.enabled():   # a rerun: our old reservation would block us
        release_ports(adw_id, *old_ports)
    steps.record(adw_id, "setup", "running", label="Setup", note="Resuming" if resumed else "")
    backend_port = frontend_port = None
    if resources.enabled():
        # The machine-wide lease (ports + Redis database), held while this process runs. A rerun keeps its old
        # ports when they're still free.
        try:
            resources.acquire(adw_id, hold="process", worktree=state.get("worktree_path") or
                              os.path.join(MAIN_ROOT, "trees", adw_id),
                              prefer_ports=old_ports if all(old_ports) else None,
                              db_name=state.get("database_name"))
        except resources.ResourcesExhausted as e:
            steps.record(adw_id, "setup", "failed", label="Setup", note=f"Waiting for resources: {e}")
            comment(issue_number, f"⏳ No free resources on this machine yet: {e}", adw_id=adw_id)
            print(f"Setup postponed: {e}", file=sys.stderr)
            sys.exit(EXIT_NO_RESOURCES)
        if resumed:          # (a new worktree's Redis database is flushed by setup_worktree_environment)
            from adw_modules.database_ops import flush_redis_db_for_adw
            flush_redis_db_for_adw(adw_id, logger)       # the leased database may hold another workflow's keys
    try:
        backend_port, frontend_port = find_next_available_ports(adw_id)      # reserved: no other ADW gets them
        notes = [f"ports {backend_port}/{frontend_port}"]
        if resumed:
            worktree = state.get("worktree_path")
            db_name = state.get("database_name")
        else:
            branch = state.get("branch_name")
            worktree, actual_branch, err = create_worktree(adw_id, branch, logger)
            if err:
                raise env_setup.SetupError(f"Couldn't create the worktree: {err}")
            if actual_branch and actual_branch != branch:
                state.update(branch_name=actual_branch)
            db_name, backend_port, frontend_port, err = setup_worktree_environment(
                worktree, backend_port, frontend_port, adw_id, logger)
            if err:
                raise env_setup.SetupError(f"Couldn't create the isolated database: {err}")
        state.update(worktree_path=worktree, backend_port=backend_port, frontend_port=frontend_port,
                     database_name=db_name)
        state.save("orchestrated_setup")
        env_setup.configure_worktree(worktree, adw_id, backend_port, frontend_port, db_name, logger)
        notes.append(env_setup.install_dependencies(worktree, logger))
        notes.append(env_setup.ensure_browser(worktree, logger))
        notes.append(env_setup.run_migrations(worktree, logger))
        notes.append(env_setup.start_app(worktree, backend_port, frontend_port, logger,
                                         log_path=os.path.join(orch_dir(adw_id), "app_start.log")))
    except Exception as e:  # noqa: BLE001 - SetupError, or anything unexpected: same handling
        if backend_port and frontend_port:
            release_ports(adw_id, backend_port, frontend_port)
        env_setup.stop_app(adw_id, logger)
        steps.record(adw_id, "setup", "failed", label="Setup", note=str(e))
        comment(issue_number, f"❌ Setup failed: {e}", adw_id=adw_id)
        sys.exit(f"Setup failed: {e}")
    steps.record(adw_id, "setup", "done", label="Setup", note=("Resumed; " if resumed else "") + "; ".join(notes))


# ---- the orchestrator session -----------------------------------------------

def read_agent_file(name: str) -> tuple[dict, str]:
    """Frontmatter (key: value, comma lists) and body of adws/orchestrator/subagents/<name>.md; `@include x.md`
    as the body pulls in another agent's prompt."""
    with open(os.path.join(AGENTS_DIR, name), encoding="utf-8") as f:
        text = f.read()
    meta, body = {}, text
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    inc = re.match(r"^\s*@include\s+(\S+)\s*$", body)
    if inc:
        body = read_agent_file(inc.group(1))[1]
    return meta, body


def agent_definitions(suites: str, guard_cmd: str) -> dict:
    """The subagents, as `claude --agents` JSON: tools enforced by the CLI, model from the environment."""
    agents = {}
    for name in sorted(os.listdir(AGENTS_DIR)):
        if not name.endswith(".md"):
            continue
        meta, body = read_agent_file(name)
        listed = lambda key: [t.strip() for t in meta.get(key, "").split(",") if t.strip()]  # noqa: E731
        spec = {"description": meta.get("description", ""), "prompt": body.replace("{{suites}}", suites).strip(),
                "tools": listed("tools"),
                "model": os.getenv(meta.get("model_env", ""), "") or meta.get("model") or "inherit"}
        if listed("disallowedTools"):
            spec["disallowedTools"] = listed("disallowedTools")
        if meta.get("readonly") == "true":
            spec["hooks"] = {"PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": f"{guard_cmd} --always", "timeout": 30}]}]}
        agents[meta.get("name") or name[:-3]] = spec
    return agents


def readonly_agents(agents: dict) -> list[str]:
    return [n for n, a in agents.items() if a.get("hooks")]


def build_prompt(ctx: dict) -> str:
    with open(PROMPT_FILE, encoding="utf-8") as f:
        text = f.read()
    for k, v in ctx.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def orchestrator_command(agents: dict, guard_cmd: str, worktree: str, resume: str | None) -> list[str]:
    """The orchestrator's claude command. Streaming input: the prompt (and every later message) goes in on stdin as
    stream-json user messages, so Ore's messages can be injected while it works. No --json-schema: the result comes
    through `adw_report.py result` (with the schema the CLI forces a result at every turn's end, also while
    subagents still run)."""
    # The guard also runs as a session hook keyed on the subagent type, in case agent-scoped hooks don't load.
    settings = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": f"{guard_cmd} --agents {','.join(readonly_agents(agents))}", "timeout": 30}]}]}}
    cmd = [CLAUDE, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--replay-user-messages", "--model", ORCH_MODEL,
           "--agents", json.dumps(agents),
           "--settings", json.dumps(settings), "--dangerously-skip-permissions",
           "--disallowedTools", "Bash(git push --force:*)", "Bash(git push -f:*)", "Bash(git reset --hard:*)"]
    if ORCH_EFFORT:
        cmd += ["--effort", ORCH_EFFORT]
    mcp = os.path.join(worktree, ".mcp.json")
    if os.path.exists(mcp):
        cmd += ["--mcp-config", mcp]
    if resume:
        cmd += ["--resume", resume]
    return cmd


FINISH = "finish by running `{report} result ...` (see Finishing in your instructions)"
RESUME_PROMPT = ("You were interrupted. Check `git status`, `git log origin/main..HEAD`, the steps you reported "
                 "(agents/{adw_id}/steps.jsonl in the main checkout: {steps_file}) and which subagents finished. "
                 "Relaunch only unfinished packages, with a brief that says to continue from the files already "
                 "changed; then carry on with the workflow. Do not redo finished work. Same rules: end your turn "
                 "while subagents run, and " + FINISH + " only when the whole workflow is done.")
FORCED_RESULT_NOTE = ("Your earlier \"failed\" result was not your decision: a bug in the workflow forced it (the CLI "
                      "demanded a structured result when your turn ended while your subagents were still running). "
                      "Ignore that result; the run is not over. The StructuredOutput tool is gone, and ending a turn "
                      "while subagents run is expected now. Continue planning from what the investigations found "
                      "(their reports are in this conversation; relaunch any that didn't report), write the plan and "
                      "carry on with the workflow. ")
LIMIT_RESUME_PROMPT = ("The Claude usage limit has reset. Continue where you stopped: check `git status` and which "
                       "subagents finished (relaunch the ones a limit cut off, telling them to continue from the files "
                       "already changed), then carry on. Same rules; " + FINISH + " when the workflow is done.")
FOLLOW_UP_PROMPT = (
    "Follow-up {n} from {who}, through Ore. This workflow finished earlier ({pr}); now this is wanted too:\n\n"
    "{text}\n\n"
    "Do it as a new round of this same workflow: the same worktree and branch, and the same pull request, which "
    "updates when you push. First check `git status` and `git log --oneline origin/main..HEAD`. The steps you report "
    "start again (route and setup stay done): follow the workflow in your instructions at the size this request "
    "needs: a short written plan (`{report} plan ...`), the work through the implementer subagents, your checks on "
    "the changed code, screens if the UI changed (else skip them), the review until it passes (it reviews this "
    "round's changes), docs where they're now wrong, then commit and `{report} pr ...` (it pushes; the pull request "
    "exists already). The full check is your call this round. Run it (`{report} check`, before the PR step) when "
    "this round's changes could break what your checks on the changed code don't cover: shared code, data models or "
    "migrations, APIs and their types, configuration or dependencies, changes across many files, or a fix for "
    "failures of the last full check. Skip it for a small, contained change those checks cover (copy, styling, docs, "
    "one component and its tests): record `{report} step check skipped --label \"Full check\" --note \"<why>\"`. "
    "Earlier decisions stand unless this request changes them; if it is unclear, or would undo one, ask with "
    "`{report} ask`. Update the workflow report ({report_file}): keep it a complete report of the workflow as it is "
    "now, with a `## Follow-up {n}` section first (what was asked, what changed, decisions, whether the full check "
    "ran and why, what's not done, caveats). Then " + FINISH + ".")


def follow_up_message(follow: dict, report: str, report_file: str, pr: str | None) -> str:
    text = FOLLOW_UP_PROMPT
    for key, value in (("{n}", str(follow.get("n") or 1)), ("{who}", str(follow.get("from") or "the user")),
                       ("{pr}", pr or "its pull request"), ("{report_file}", report_file), ("{report}", report)):
        text = text.replace(key, value)
    return text.replace("{text}", str(follow.get("text") or "").strip())     # last: the user's words stay as written


def read_follow_up(adw_id: str) -> dict | None:
    """The follow-up the Ore trigger handed this run (agents/<adw_id>/followup.json), or None."""
    try:
        with open(os.path.join(MAIN_ROOT, "agents", adw_id, messages.FOLLOW_UP), encoding="utf-8") as f:
            follow = json.load(f)
    except (OSError, ValueError):
        return None
    return follow if isinstance(follow, dict) and str(follow.get("text") or "").strip() else None


NUDGE = ("Your turn ended without the final result, and no subagent or command is running. Continue the workflow "
         "where you are. If you are done (PR opened) or must give up, " + FINISH + " now.")
WAIT_FOR_TASKS = ("Your result was NOT recorded: {running} still running. Wait for them: end your turn now; their "
                  "reports start a new turn. Act on them, and report the result when the workflow is done. Only if you "
                  "deliberately give up without their results, run the result command again with --force.")
BAD_RESULT = ("The result file isn't valid, so it was not recorded. Report it with `{report} result <pr_opened|failed|dropped> "
              "--summary \"...\"` (the command checks it).")
NUDGE_AFTER = env_int("ADW_ORCH_NUDGE_SECONDS", 45)     # idle (turn over, nothing running) this long: nudge
MAX_NUDGES = 3                                          # nudges in a row without any tool call: give up
EXIT_GRACE = env_int("ADW_ORCH_EXIT_GRACE_SECONDS", 60)  # result in, stdin closed: claude exits within this, else
                                                        # its leftover background commands (a dev server) are stopped


def user_message(text: str, priority: str | None = None) -> str:
    """One stream-json input line. priority (claude 2.1): "next" = at the next tool boundary of the current turn,
    "later" = after the turn, "now" = interrupt the turn."""
    msg: dict = {"type": "user", "message": {"role": "user", "content": text}}
    if priority:
        msg["priority"] = priority
    return json.dumps(msg, ensure_ascii=False) + "\n"


class Messenger:
    """Ore's messages for this workflow: agents/<adw_id>/inbox.jsonl (written by the Ore trigger), forwarded to the
    orchestrator session as user messages. The offset is kept on disk, so a resumed workflow forwards only what it
    hasn't yet."""

    def __init__(self, adw_id: str, report: str):
        self.dir = os.path.join(MAIN_ROOT, "agents", adw_id)
        self.inbox = os.path.join(self.dir, messages.INBOX)
        self.outbox = os.path.join(self.dir, messages.OUTBOX)
        self.offset_file = os.path.join(self.dir, AGENT_NAME, "inbox.offset")
        self.report = report
        try:
            with open(self.offset_file, encoding="utf-8") as f:
                self.offset = int(f.read().strip() or 0)
        except (OSError, ValueError):
            self.offset = 0
        self.paused = messages.paused(messages.read_all(self.inbox))
        self.busy_replied: set = set()
        self._checking = (None, False, False)   # ((outbox size, inbox size), waiting for the full check, asking)

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.offset_file), exist_ok=True)
            with open(self.offset_file, "w", encoding="utf-8") as f:
                f.write(str(self.offset))
        except OSError:
            pass

    def poll(self) -> list[str]:
        """The new inbox entries as texts for the orchestrator (answers to its own questions are read by
        `adw_report.py ask`; only late ones, after it gave up waiting, are forwarded)."""
        entries, self.offset = messages.read_new(self.inbox, self.offset)
        if not entries:
            return []
        out = []
        outbox = messages.read_all(self.outbox)
        for e in entries:
            if e.get("type") == "message":
                out.append(messages.for_orchestrator(e, self.report))
                if e.get("mode") == "pause":
                    self.paused = True
                elif e.get("mode") in ("resume", "amend"):
                    self.paused = False
            elif e.get("type") == "answer":
                if any(o.get("type") == "ask_cancel" and o.get("n") == e.get("ask") for o in outbox):
                    ask = next((o for o in outbox if o.get("type") == "ask" and o.get("n") == e.get("ask")), {})
                    out.append(messages.late_answer(ask, e))
        self._save()
        return out

    def _refresh(self) -> None:
        sizes = (messages.size(self.outbox), messages.size(self.inbox))
        if sizes != self._checking[0]:
            outbox, inbox = messages.read_all(self.outbox), messages.read_all(self.inbox)
            self._checking = (sizes, messages.check_pending(outbox, inbox), messages.ask_open(outbox, inbox))

    def checking(self) -> bool:
        """Waiting for the batch's full check (it waits for the other workflows, so the time doesn't count)."""
        self._refresh()
        return self._checking[1]

    def asking(self) -> bool:
        """A question waits for the user (it stays open until answered, so the time doesn't count)."""
        self._refresh()
        return self._checking[2]

    def reply_busy(self, why: str, then: str = "The orchestrator gets your message when it continues.") -> None:
        """While no session runs (usage-limit wait, or it has finished), tell senders once about their message."""
        for e in messages.read_new(self.inbox, self.offset)[0]:
            if e.get("type") == "message" and e.get("id") and e["id"] not in self.busy_replied:
                self.busy_replied.add(e["id"])
                messages.append(self.outbox, {"type": "reply", "to": e["id"], "text": f"{why} {then}".strip()})


_current: list = []          # the claude session running now, so a SIGTERM to this workflow stops it too


def _on_signal(signum, frame):
    for proc in list(_current):
        _kill(proc)
    raise SystemExit(f"Stopped by signal {signum}")


def _stop_strays(proc: subprocess.Popen) -> None:
    """After the session: anything still in its process group (a background command claude left running) is
    stopped. The group is the session's own (start_new_session), so nothing else is touched."""
    if proc.poll() is None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, AttributeError, OSError):
        pass


def _kill(proc: subprocess.Popen) -> None:
    """SIGTERM to the session's process group (claude and its tool processes), then SIGKILL."""
    for sig in (signal.SIGTERM, getattr(signal, "SIGKILL", signal.SIGTERM)):
        try:
            os.killpg(proc.pid, sig)
        except (ProcessLookupError, PermissionError, AttributeError, OSError):
            try:
                proc.send_signal(sig)
            except Exception:  # noqa: BLE001
                pass
        try:
            proc.wait(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


def final_status(result: dict | None) -> bool:
    """A result message with a structured status (only from a session started with --json-schema; kept as a
    harmless fallback: the orchestrator reports through result.json)."""
    out = (result or {}).get("structured_output")
    return isinstance(out, dict) and bool(out.get("status"))


def running_names(tasks: dict) -> str:
    """'these subagents/commands are "A", "B"' for the wait message."""
    names = sorted({d for d in tasks.values() if d})
    if not names:
        return f"{len(tasks)} subagent{'s are' if len(tasks) != 1 else ' is'}"
    return ("these subagents/commands are " if len(names) > 1 else "this subagent/command is ") + \
        ", ".join(f'"{n}"' for n in names)


def forced_result_in(path: str) -> bool:
    """Did this session transcript give a StructuredOutput "failed" while background tasks still ran? That is the
    result the CLI forced under --json-schema (issue #37 of OneFan): not the orchestrator's decision."""
    tasks: set = set()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                kind, sub = msg.get("type"), msg.get("subtype")
                if kind == "system" and sub == "task_started" and msg.get("task_id"):
                    tasks.add(msg["task_id"])
                elif kind == "system" and sub == "task_notification":
                    tasks.discard(msg.get("task_id"))
                elif kind == "system" and sub == "background_tasks_changed" and isinstance(msg.get("tasks"), list):
                    tasks = {t.get("task_id") for t in msg["tasks"] if isinstance(t, dict)}
                elif kind == "assistant" and not msg.get("parent_tool_use_id"):
                    for c in (msg.get("message") or {}).get("content") or []:
                        if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "StructuredOutput" \
                                and (c.get("input") or {}).get("status") == "failed" and tasks:
                            return True
    except OSError:
        pass
    return False


def last_output(adw_id: str) -> str | None:
    """The newest raw_output-*.jsonl of this workflow's orchestrator sessions."""
    d = orch_dir(adw_id)
    try:
        names = sorted(n for n in os.listdir(d) if n.startswith("raw_output-") and n.endswith(".jsonl"))
    except OSError:
        return None
    return os.path.join(d, names[-1]) if names else None


def run_session(cmd: list[str], cwd: str, env: dict, out_path: str, timeout_s: int, on_session,
                beat=None, first_message: str | None = None, messenger: Messenger | None = None,
                usage: "messages.UsageTracker | None" = None, poll: float = 1.0, result_file: str | None = None,
                report: str = "adw_report.py") -> dict:
    """Run one claude -p session, streaming to out_path; returns {"result": <the last result message> | None,
    "final": <the result.json it ended on> | None, "timed_out": bool, "returncode": int, "stderr": str}.

    With first_message, the session reads stream-json from stdin: the first message is the prompt; Ore's messages
    (messenger) are injected as they arrive (priority "next": at the next tool boundary). Subagents run in the
    background, so a turn can end with work still running: the CLI starts a new turn when they report. The session
    is over when result_file (written by `adw_report.py result`) exists and no background task is running (or at
    an error result): then stdin is closed and claude exits. A result written while tasks still run is removed and
    the orchestrator is told to wait for them (unless it gives up on purpose: --force). A turn that ends with
    nothing running and no result gets a nudge (MAX_NUDGES at most).
    on_session(id) is called as soon as the id is known; beat() about once a minute (the lease's heartbeat); usage
    gets every message (usage.json). Time spent paused (a pause message) doesn't count against timeout_s."""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    err_path = out_path + ".stderr"
    st = {"result": None, "final": None, "session": None, "pos": 0, "buf": b"", "tasks": {}, "idle_since": None,
          "nudges": 0, "open": first_message is not None}

    def send(proc, text: str, priority: str | None = None) -> None:
        if not st["open"]:
            return
        try:
            proc.stdin.write(user_message(text, priority).encode("utf-8"))
            proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            st["open"] = False

    def close(proc) -> None:
        if st["open"]:
            st["open"] = False
            try:
                proc.stdin.close()
            except OSError:
                pass

    def handle(proc, msg: dict) -> None:
        sid = msg.get("session_id")
        if sid and sid != st["session"]:
            st["session"] = sid
            on_session(sid)
        if usage is not None:
            usage.on_message(msg)
        kind, sub = msg.get("type"), msg.get("subtype")
        if kind == "result":
            st["result"] = msg
            if final_status(msg) or msg.get("is_error"):
                close(proc)
            else:
                st["idle_since"] = time.time()
        elif kind == "system" and sub == "task_started" and msg.get("task_id"):
            st["tasks"][msg["task_id"]] = msg.get("description") or msg.get("subagent_type") or ""
        elif kind == "system" and sub == "task_notification" and msg.get("task_id"):
            st["tasks"].pop(msg["task_id"], None)
        elif kind == "system" and sub == "background_tasks_changed" and isinstance(msg.get("tasks"), list):
            st["tasks"] = {t["task_id"]: t.get("description") or t.get("subagent_type") or ""   # the CLI's own list
                           for t in msg["tasks"] if isinstance(t, dict) and t.get("task_id")}
        elif kind == "assistant":
            st["idle_since"] = None
            if any(c.get("type") == "tool_use" for c in (msg.get("message") or {}).get("content") or []
                   if isinstance(c, dict)):
                st["nudges"] = 0

    def check_result(proc) -> None:
        """result.json: the end once nothing runs in the background; written too early, it is set aside."""
        if not (result_file and st["open"] and os.path.exists(result_file)):
            return
        found = messages.read_result(result_file)
        if found is not None and (found["force"] or not st["tasks"]):
            st["final"] = found
            st["closed_at"] = time.time()
            close(proc)
            return
        try:
            os.remove(result_file)
        except OSError:
            pass
        st["idle_since"] = None
        if found is None:
            send(proc, BAD_RESULT.replace("{report}", report), "next")
        else:
            send(proc, WAIT_FOR_TASKS.replace("{running}", running_names(st["tasks"])), "next")

    def consume(proc, final: bool = False) -> None:
        with open(out_path, "rb") as f:
            f.seek(st["pos"])
            chunk = f.read()
        st["pos"] += len(chunk)
        lines = (st["buf"] + chunk).split(b"\n")
        st["buf"] = b"" if final else lines.pop()
        for raw in lines:
            try:
                msg = json.loads(raw.decode("utf-8", errors="replace"))
            except ValueError:
                continue
            if isinstance(msg, dict):
                handle(proc, msg)

    if usage is not None:
        usage.new_process()
    timed_out = False
    with open(out_path, "wb") as out, open(err_path, "wb") as err:
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out, stderr=err,
                                stdin=subprocess.PIPE if first_message is not None else subprocess.DEVNULL,
                                start_new_session=True)
        _current.append(proc)
        try:
            if first_message is not None:
                send(proc, first_message)
            deadline = time.time() + timeout_s
            last_beat = last_tick = time.time()
            while proc.poll() is None:
                consume(proc)
                check_result(proc)
                now = time.time()
                if messenger is not None:
                    if messenger.paused or messenger.checking() or messenger.asking():
                        deadline += now - last_tick            # a pause, the batch's check or an open question
                                                               # doesn't use up the time
                    if st["open"]:
                        for text in messenger.poll():
                            send(proc, text, "next")
                            st["idle_since"] = None
                last_tick = now
                if st["open"] and st["idle_since"] and not st["tasks"] and \
                        not (messenger is not None and messenger.paused) and now - st["idle_since"] > NUDGE_AFTER:
                    if st["nudges"] >= MAX_NUDGES:
                        close(proc)                              # it keeps stopping without a result: give up
                    else:
                        st["nudges"] += 1
                        st["idle_since"] = None
                        send(proc, NUDGE.replace("{report}", report), "next")
                if beat and now - last_beat > 60:
                    last_beat = now
                    try:
                        beat()
                    except Exception:  # noqa: BLE001 - a heartbeat must not stop the session
                        pass
                if now > deadline:
                    timed_out = True
                    _kill(proc)
                    break
                if st.get("closed_at") and now - st["closed_at"] > EXIT_GRACE:
                    # claude waits for its background commands before exiting, and a server never ends: the result
                    # is in, so stop the session's process group (claude and what it left running)
                    _kill(proc)
                    break
                time.sleep(poll)
        finally:
            close(proc)
            _current.remove(proc)
            _stop_strays(proc)
    consume(proc, final=True)
    with open(err_path, encoding="utf-8", errors="replace") as f:
        stderr = f.read()[-3000:]
    return {"result": st["result"], "final": st["final"], "timed_out": timed_out, "returncode": proc.returncode,
            "stderr": stderr}


def transient(text: str) -> bool:
    from adw_modules.agent import _classify_transient_error
    return _classify_transient_error(text or "") is not None


def limit_wait(usage: "messages.UsageTracker | None", text: str) -> tuple[int, str | None]:
    """(seconds to wait, the reset time as HH:MM or None) after a usage-limit / overload stop: until the limit's
    reset (from the stream's rate_limit_event) plus a minute, else LIMIT_WAIT_SECONDS."""
    limit = ((usage.data if usage else {}) or {}).get("limit") or {}
    resets = limit.get("resets_at")
    rejected = limit.get("status") not in (None, "allowed", "allowed_warning") or \
        re.search(r"usage limit|limit reached|rate.?limit", text or "", re.I)
    if resets and rejected:
        try:
            from datetime import datetime
            at = datetime.fromisoformat(resets)
            secs = int((at - datetime.now()).total_seconds()) + 60
            if secs > 0:
                return secs, at.strftime("%H:%M")
        except ValueError:
            pass
    return LIMIT_WAIT_SECONDS, None


def orchestrate(state, issue, logger, fresh: bool, follow_up: dict | None = None) -> dict:
    """Run (or resume) the orchestrator until it finishes, fails, or hits the wall-clock limit. A follow-up resumes
    the session with the request as its next instruction."""
    from adw_modules.utils import get_safe_subprocess_env
    adw_id, worktree = state.get("adw_id"), state.get("worktree_path")
    issue_number = state.get("issue_number")
    report, suites = uv_cmd("adw_report.py"), uv_cmd("adw_run_suites.py")
    guard_cmd = f"python3 {GUARD}"
    agents = agent_definitions(suites, guard_cmd)
    pr_body = os.path.join(orch_dir(adw_id), "pr_body.md")
    issue_class = state.get("issue_class") or "/feature"
    ctx = {"issue_number": issue_number, "issue_title": issue.title, "issue_body": issue.body or "(no description)",
           "adw_id": adw_id, "worktree": worktree, "branch": state.get("branch_name"), "issue_class": issue_class,
           "backend_port": state.get("backend_port"), "frontend_port": state.get("frontend_port"),
           "report": report, "suites": suites, "adws": ADWS_DIR, "max_review_rounds": MAX_REVIEW_ROUNDS,
           "max_check_rounds": MAX_CHECK_ROUNDS,
           "pr_body_file": pr_body, "report_file": os.path.join(orch_dir(adw_id), "workflow_report.md"),
           "pr_type": {"/feature": "feat", "/bug": "bug", "/chore": "chore"}.get(
               issue_class, "feat"),
           "plan_file": f"specs/orchestrated/issue-{issue_number}-{adw_id}.md",
           "screens_dir": os.path.join(MAIN_ROOT, "agents", adw_id, "screens")}
    os.makedirs(orch_dir(adw_id), exist_ok=True)
    prompt = build_prompt(ctx)
    with open(os.path.join(orch_dir(adw_id), "prompt.md"), "w", encoding="utf-8") as f:
        f.write(prompt)
    with open(os.path.join(orch_dir(adw_id), "agents.json"), "w", encoding="utf-8") as f:
        json.dump(agents, f, indent=1)
    env = get_safe_subprocess_env()
    env.update(ADW_ID=adw_id, ADW_ISSUE_NUMBER=str(issue_number), PWD=worktree)
    # `adw_report.py ask|wait` block until the user answers (up to an hour): let Bash calls run that long.
    env.setdefault("BASH_MAX_TIMEOUT_MS", os.getenv("BASH_MAX_TIMEOUT_MS") or "3900000")
    messenger = Messenger(adw_id, report)
    usage = messages.UsageTracker(os.path.join(MAIN_ROOT, "agents", adw_id, messages.USAGE))

    def keep_session(sid: str) -> None:
        state.update(orchestrator_session_id=sid)
        state.save("orchestrator_session")

    session = None if fresh else state.get("orchestrator_session_id")
    resume_text = RESUME_PROMPT.replace("{adw_id}", adw_id).replace("{steps_file}", steps.steps_path(adw_id))
    previous = last_output(adw_id) if session else None
    if previous and forced_result_in(previous):          # the last session ended on a result the CLI forced
        logger.info("The last session ended on a forced StructuredOutput result: resuming past it")
        resume_text = FORCED_RESULT_NOTE + resume_text
    resume_text = resume_text.replace("{report}", report)
    if follow_up:
        message = follow_up_message(follow_up, report, ctx["report_file"], pr_url_recorded(adw_id))
        if session:
            resume_text = message
        else:                                            # (no session to resume: a fresh one gets both)
            prompt = f"{prompt}\n\n## Follow-up\n\n{message}"
    if steps.last_status(adw_id, "plan") != "done":
        steps.record(adw_id, "plan", "running", label="Plan")
    deadline = time.time() + TIMEOUT_MIN * 60
    waits = 0
    interrupted = not follow_up          # a follow-up resumes a session that finished: no turn was cut off
    while True:
        run_env = dict(env)
        if session and interrupted:
            run_env["CLAUDE_CODE_RESUME_INTERRUPTED_TURN"] = "1"     # finish the turn the interruption cut off
        interrupted = True
        cmd = orchestrator_command(agents, guard_cmd, worktree, session)
        clear_result(adw_id)                                         # every session starts without a result
        out_path = os.path.join(orch_dir(adw_id), f"raw_output-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
        logger.info(f"Orchestrator session {'resumed' if session else 'started'} ({ORCH_MODEL}), output: {out_path}")
        run = run_session(cmd, worktree, run_env, out_path, max(60, int(deadline - time.time())), keep_session,
                          beat=(lambda: resources.heartbeat(adw_id)) if resources.enabled() else None,
                          first_message=resume_text if session else prompt, messenger=messenger, usage=usage,
                          result_file=result_path(adw_id), report=report)
        res = run["result"] or {}
        session = state.get("orchestrator_session_id") or session
        final = messages.read_result(result_path(adw_id))
        if final:                                                    # what `adw_report.py result` recorded
            final.pop("force", None)
            return final
        if run["timed_out"]:
            return {"status": "failed", "reason": f"The orchestrator hit the {TIMEOUT_MIN}-minute limit"}
        out = res.get("structured_output")                           # (only a session with --json-schema)
        if isinstance(out, dict) and out.get("status"):
            return out
        text = f"{res.get('result') or ''} {run['stderr']}"
        if (res.get("is_error") or not res) and transient(text) and waits < MAX_LIMIT_WAITS and session:
            waits += 1
            wait_s, until = limit_wait(usage, text)
            if wait_s > MAX_LIMIT_WAIT_HOURS * 3600:
                return {"status": "failed", "reason": f"Claude usage limit reached until {until} (more than "
                                                      f"{MAX_LIMIT_WAIT_HOURS} h away); press Resume after it resets"}
            why = (f"Claude usage limit reached until {until}." if until
                   else f"Claude usage limit or API overload: waiting {wait_s // 60} minutes.")
            logger.warning(f"{why} Resuming afterwards ({waits}/{MAX_LIMIT_WAITS})")
            comment(issue_number, f"⏳ {why} The workflow resumes automatically.", adw_id=adw_id)
            from datetime import datetime
            usage.set_waiting(datetime.fromtimestamp(time.time() + wait_s).isoformat(timespec="seconds"))
            end = time.time() + wait_s
            while time.time() < end:
                messenger.reply_busy(why)
                time.sleep(min(60, max(1, end - time.time())))
                if resources.enabled():
                    resources.heartbeat(adw_id)
            usage.set_waiting(None)
            deadline += wait_s
            resume_text = LIMIT_RESUME_PROMPT.replace("{report}", report)
            continue
        if not res:
            return {"status": "failed", "reason": f"The orchestrator session stopped (exit {run['returncode']}): "
                                                  f"{run['stderr'].strip()[-300:] or 'no result'}"}
        return {"status": "failed", "reason": (res.get("result") or "The orchestrator gave no result")[:500]}


# ---- after the session -------------------------------------------------------

def pr_url_recorded(adw_id: str) -> str | None:
    try:
        with open(os.path.join(orch_dir(adw_id), "pr_url.txt"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def open_pr_fallback(state, issue, summary: str, logger) -> str | None:
    """The review passed but no PR was opened (the session ended early): commit leftovers, open it by script."""
    adw_id, worktree = state.get("adw_id"), state.get("worktree_path")
    if subprocess.run(["git", "status", "--porcelain"], cwd=worktree, capture_output=True, text=True).stdout.strip():
        subprocess.run(["git", "add", "-A"], cwd=worktree, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"chore: remaining changes (#{state.get('issue_number')})"],
                       cwd=worktree, capture_output=True)
    kind = {"/bug": "bug", "/chore": "chore"}.get(state.get("issue_class"), "feat")
    body_path = os.path.join(orch_dir(adw_id), "pr_body.md")
    if not os.path.exists(body_path):
        with open(body_path, "w", encoding="utf-8") as f:
            f.write(f"## Summary\n\n{summary or issue.title}\n\nCloses #{state.get('issue_number')}\n")
    from adw_modules.utils import get_safe_subprocess_env
    env = {**get_safe_subprocess_env(), "ADW_ID": adw_id, "ADW_ISSUE_NUMBER": str(state.get("issue_number"))}
    proc = subprocess.run(["uv", "run", "--quiet", os.path.join(ADWS_DIR, "adw_report.py"), "pr", "--title",
                           f"{kind}: #{state.get('issue_number')} - {issue.title}", "--body-file", body_path],
                          cwd=worktree, env=env, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        logger.error(f"Opening the PR failed: {proc.stderr.strip()[-500:]}")
    return pr_url_recorded(adw_id)


def finish(state, issue, outcome: dict, logger) -> None:
    adw_id, issue_number = state.get("adw_id"), state.get("issue_number")
    review_ok = steps.last_status(adw_id, "review") == "done"
    pr_url = pr_url_recorded(adw_id) or (outcome.get("pr_url") if review_ok else None)
    if outcome.get("status") == "dropped":                      # nothing to change: stopped, not failed
        reason = outcome.get("reason") or outcome.get("summary") or "Nothing to do"
        steps.close_open(adw_id, reason, status="skipped")
        if steps.last_status(adw_id, "pr") is None:
            steps.record(adw_id, "pr", "skipped", label="Pull request", note=reason)
        comment(issue_number, f"⏹️ Orchestrated SDLC stopped, nothing to change: {reason}", adw_id=adw_id)
        print(f"\n=== ORCHESTRATED SDLC STOPPED (nothing to change) ===\n{reason}")
        return
    if outcome.get("status") != "failed" and review_ok and not pr_url:
        pr_url = open_pr_fallback(state, issue, outcome.get("summary", ""), logger)
    if review_ok and pr_url:
        steps.close_open(adw_id, "Not finished")
        comment(issue_number, f"🎉 Orchestrated SDLC workflow completed: {pr_url}\n\n{outcome.get('summary', '')}",
                adw_id=adw_id)
        print(f"\n=== ORCHESTRATED SDLC COMPLETED ===\nPR: {pr_url}")
        return
    if not review_ok and outcome.get("status") == "pr_opened":
        reason = "The orchestrator reported a PR, but no review round passed"
    else:
        reason = outcome.get("reason") or ("No passing review" if not review_ok else "No pull request")
    blockers = outcome.get("open_blockers") or []
    steps.close_open(adw_id, reason)
    if steps.last_status(adw_id, "pr") is None:
        steps.record(adw_id, "pr", "skipped", label="Pull request", note=reason)
    comment(issue_number, f"❌ Orchestrated SDLC failed: {reason}"
            + ("\n\nOpen blockers:\n" + "\n".join(f"- {b}" for b in blockers) if blockers else ""), adw_id=adw_id)
    sys.exit(f"Orchestrated SDLC failed: {reason}")


# ---- dry run -----------------------------------------------------------------

def dry_run(issue_number: str, adw_id: str, delay: float = DRY_DELAY) -> None:
    """Record what a run looks like (steps + progress comments), without Claude, GitHub or a worktree."""
    from adw_modules import orchestrated_sim
    path = steps.steps_path(adw_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for event, text in orchestrated_sim.EVENTS:
        if event:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "parent": None, "label": None,
                                    "note": "", **event}, ensure_ascii=False) + "\n")
        if text:
            comment(issue_number, text, dry_run=True, adw_id=adw_id)
        if delay:
            time.sleep(delay)
    print(f"Dry run recorded in {path}")


# ---- machine-wide resources ----------------------------------------------------

def take_workflow_slot(adw_id: str) -> None:
    """One of the machine's ADW_MAX_WORKFLOWS workflow slots (shared by every codebase). The Ore trigger takes it
    before starting this script (then this only records our pid); started by hand, this waits for a free one."""
    if not resources.enabled():
        from adw_run_suites import register_active
        register_active(adw_id)
        return

    def waiting(used: int, cap: int) -> None:
        msg = f"Waiting for a free slot: {used} workflows running on this machine (ADW_MAX_WORKFLOWS={cap})"
        print(msg, flush=True)
        steps.record(adw_id, "setup", "running", label="Setup", note=msg)
    resources.acquire_slot(resources.WORKFLOW, adw_id, adw_id=adw_id, wait=None, poll=SLOT_POLL_SECONDS,
                           on_wait=waiting)


def give_back(adw_id: str, keep_lease: bool = False) -> None:
    """Release the workflow slot, and the lease (ports, Redis) unless the app is left running (ADW_ORCH_KEEP_APP)."""
    if not resources.enabled():
        from adw_run_suites import unregister_active
        unregister_active(adw_id)
        return
    try:
        if keep_lease:
            resources.release_slot(resources.WORKFLOW, adw_id)
        else:
            resources.release(adw_id)
    except Exception as e:  # noqa: BLE001
        print(f"Couldn't release the resource lease: {e}", file=sys.stderr)


# ---- main --------------------------------------------------------------------

def main() -> None:
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args or not args[0].isdigit():
        sys.exit(__doc__)
    issue_number, adw_id = args[0], (args[1] if len(args) > 1 else None)

    if "--dry-run" in flags:
        from adw_modules.utils import make_adw_id
        dry_run(issue_number, adw_id or make_adw_id())
        return

    from adw_modules.github import extract_repo_path, fetch_issue, get_repo_url
    from adw_modules.state import ADWState
    from adw_modules.utils import check_env_vars, setup_logger
    from adw_modules.workflow_ops import ensure_adw_id

    adw_id = ensure_adw_id(issue_number, adw_id)
    print(f"Using ADW ID: {adw_id}")
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    logger = setup_logger(adw_id, "adw_orchestrated_sdlc_iso")
    check_env_vars(logger)
    state = ADWState.load(adw_id, logger) or ADWState(adw_id)
    state.update(adw_id=adw_id, issue_number=issue_number)
    state.append_adw_id("adw_orchestrated_sdlc_iso")
    state.save("orchestrated_start")
    take_workflow_slot(adw_id)
    succeeded = False
    follow = read_follow_up(adw_id) if "--follow-up" in flags else None
    try:
        issue = fetch_issue(issue_number, extract_repo_path(get_repo_url()))
        if follow:
            steps.new_round(adw_id, follow.get("n") or 1, note=follow["text"])
            comment(issue_number, f"🔁 Follow-up {follow.get('n') or 1} from {follow.get('from') or 'the user'}: "
                                  f"{follow['text']}", adw_id=adw_id)

        # Route: the router may have decided already (ADW_ORCHESTRATED=1); else classify here, cheaply.
        if steps.last_status(adw_id, "route") != "done":
            steps.record(adw_id, "route", "running", label="Route")
            issue_class, slug = classify(issue, adw_id, logger)
            state.update(issue_class=issue_class)
            steps.route(adw_id, issue_class, "dynamic", WORKFLOW)
        else:
            slug = slugify(issue.title)
        if not state.get("branch_name"):
            state.update(branch_name=make_branch_name(state.get("issue_class"), issue_number, adw_id, slug))
        state.save("orchestrated_route")
        if not follow:
            comment(issue_number, f"🚀 Starting Orchestrated SDLC workflow (`{state.get('issue_class')}`, "
                                  f"orchestrator {ORCH_MODEL})", adw_id=adw_id)

        setup(state, issue, logger)
        state.save("orchestrated_setup_done")
        try:
            outcome = orchestrate(state, issue, logger, fresh="--fresh" in flags, follow_up=follow)
        except Exception as e:  # noqa: BLE001
            outcome = {"status": "failed", "reason": f"{type(e).__name__}: {e}"}
        finish(state, issue, outcome, logger)
        succeeded = True
        if not KEEP_APP:
            from adw_modules import env_setup
            env_setup.stop_app(adw_id, logger)
    except BaseException:
        steps.close_open(adw_id, "Stopped")
        try:
            release(state, logger)
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        try:                      # messages the session didn't take any more: say so instead of leaving them
            Messenger(adw_id, "").reply_busy("The orchestrator has finished; it can't take messages any more.", "")
        except Exception:  # noqa: BLE001
            pass
        give_back(adw_id, keep_lease=succeeded and KEEP_APP)


if __name__ == "__main__":
    steps.run_main(main)
