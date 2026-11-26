#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic"]
# ///

"""
ADW Ore trigger: turn approved meeting action items into GitHub issues and SDLC workflows.

Usage (Ore runs this as a workspace script, in WSL or over SSH, from the repo root or anywhere in it):
  uv run adws/adw_triggers/trigger_ore.py <items-file>            # the approved action items (Markdown or JSON)
  uv run adws/adw_triggers/trigger_ore.py --resume <run-dir>      # Ore resumes an interrupted run, or reruns
                                                                  # the workflows that failed
  uv run adws/adw_triggers/trigger_ore.py --resume <run-dir> --follow-up <request>   # Ore's Follow up on a
                                                                  # finished workflow (base64url JSON: id, part,
                                                                  # text, from)
  uv run adws/adw_triggers/trigger_ore.py --resume <run-dir> --ore-replan <request>  # Ore's board sends work back
                                                                  # to planning (base64url JSON: id, reason,
                                                                  # keep_work, items, prs)
  uv run adws/adw_triggers/trigger_ore.py --cleanup <run-dir>     # Ore undoes a run the user deleted
  uv run adws/adw_triggers/trigger_ore.py --ore-query machine      # Ore's Home page asks (see 7. Queries)
  uv run adws/adw_triggers/trigger_ore.py --ore-query prs
  uv run adws/adw_triggers/trigger_ore.py --ore-query merge <pr-number>
  uv run adws/adw_triggers/trigger_ore.py --ore-query consult <specialist> <request.json>   # Ore's project manager
  uv run adws/adw_triggers/trigger_ore.py --ore-query revert <pr-number>   # opens a revert PR (writes, in trees/)
  uv run adws/adw_triggers/trigger_ore.py --ore-merge <pr-number> [--no-checks]   # Ore's Merge button (9. Merging)
  add --dry-run to go through clarification and review without creating issues or starting ADWs;
  add --simulate (after the items file, or alone for 3 sample items) to rehearse the whole run without Claude
  or GitHub: one canned round of questions, the group review, fake issues and simulated Orchestrated SDLC
  workflows (about 3 minutes; resources are leased from the registry, nothing else is touched) that post a
  plan, ask one question, report screenshots and usage, and answer messages (pause/resume included);
  --model <claude model> and --model-set <base|heavy|superheavy> override the environment defaults

Flow:
  1. Clarify: Claude Code reads the repo (CLAUDE.md, ai_docs, the code) and the action items, and asks
     multiple-choice questions only where an item is unclear, in as many rounds as it needs. Answers come
     from the user in Ore. Each round is `claude -p ... --resume <session>`, so a run can wait for
     answers indefinitely and survive restarts.
  2. Review: Claude proposes groups (one workflow per group), grouped by repo surface and aiming at no more
     groups than there are free workflow slots on this machine. The user moves items between groups,
     renames them, and starts, or asks for changes (back to 1). Claude marks every group's size (S/M/L; the batch
     items' "Size" when Ore sends it) and how much it changes the screens (frontend none/small/significant).
  2b. Checks (the question round, still "planning"): per group, the test planner (every group) and the risk
     reviewer (M and L) in read-only sessions, and the designer (frontend significant), who writes one self-contained
     HTML prototype per version at .ore/designs/<run id>/<group slug>/v<n>.html and may write nowhere else (git status
     is checked afterwards). Risks that need the user's OK and each prototype are asked as reviews (input kind
     "review", gates "risk" and "design"); "change" continues that specialist's session with the feedback and files.
     The parts carry the specialists' notes and the gates (design, risk, tests, questions). Then the build check
     (gate "build"): approve goes on to 3, change goes back to 1 with the feedback (the same groups keep their checks
     and Claude says which to redo). Prompts: adws/specialists/designer.md, risk.md, tests.md (built-in copies when
     missing); ORE_SPECIALIST_MODEL / ORE_DESIGNER_MODEL (default: the run's model), ORE_SPECIALISTS_PARALLEL (3).
  3. Issues: Claude writes one GitHub issue per confirmed group; each is created with gh. The question round adds
     the approved prototype (kept in agents/ore/<run id>/designs/; the trigger copies it into the workflow's worktree
     as specs/designs/<slug>.html, committed with the work), the test plan, the accepted risks and the user's notes.
  4. Workflows: adw_orchestrated_sdlc_iso.py runs per issue (one orchestrator agent with parallel subagents;
     see adws/docs/orchestrated_sdlc.md); ORE_WORKFLOW=router runs adw_sdlc_router_iso.py instead (classic
     single- or multi-phase SDLC). Before each launch the trigger takes a workflow slot from the machine-wide
     resource registry (adw_modules/resources.py, shared by every codebase and Ore run on this machine,
     ADW_MAX_WORKFLOWS of them); while none is free the group stays queued ("Waiting for a free slot: N
     workflows running on this Mac"). A launch that finds no free ports or Redis database goes back to the
     queue for a minute instead of failing.
  5. Progress: every ADW issue comment is also appended to agents/progress/issue-<n>.jsonl (see
     adw_modules/github.py make_issue_comment); this script follows those files and reports per-group
     progress and PR links to Ore. The ADWs also record their steps in agents/<adw_id>/steps.jsonl
     (adw_modules/steps.py); from those, each part carries its flow (route, steps with retries, times), and
     every status message carries the run's own stages, so Ore can draw the run as a tree.

  6. Messages: the run says it accepts messages ("accepts": ["message", ...] in every status). A message for a part
     (or the whole run) goes into each targeted workflow's agents/<adw_id>/inbox.jsonl (queued ones get it when
     they start); the orchestrator answers with adw_report.py reply, which this script relays as a `reply`.
     The orchestrator's own questions (adw_report.py ask) become input requests `ask-<issue>-<n>`, one open
     at a time per run, answered back into its inbox. Parts also carry usage (agents/<adw_id>/usage.json,
     summed per run with the clarification turns) and images (agents/<adw_id>/images.jsonl).
     adw_modules/messages.py describes the files. Each part also carries "items": the batch-file item ids
     ("1", "3", ...) its group implements, so Ore can map parts back to its action items.

  8. The full check, once per batch: the workflows check only their changed code while they work
     (adw_run_suites.py changed). When one is done it asks for the full check (adw_report.py check: "check" in its
     outbox). Once every running orchestrated workflow of the run has asked, or the first has waited
     ORE_CHECK_MAX_WAIT_MIN (default 30), this script starts adw_batch_check.py on the waiting branches: merged
     onto origin/main in trees/check-<run-id>, the full suites once, and each failure attributed to main
     ("preexisting"), one branch ("yours"), or only the combination ("combined"); see adw_modules/batch_check.py.
     Each workflow gets its part in its inbox ("check_result") and step "check" shows the progress. A branch that
     conflicts with another is checked on its own when it asks again. agents/ore/<run-id>/checks/<n>/ keeps the
     request, the logs, the reports and result.json.

  9. Merging: Ore's Merge button starts this script as a run with --ore-merge <n> (it offers "merge_run" among the
     queries). adw_modules/pr_merge.py merges the PR: when it conflicts with main, main is merged into its branch
     and Claude (ADW_MERGE_MODEL, default claude-opus-5-5) resolves the conflicts with the issue, the PR and the
     workflow's report; the merge is pushed, the PR's checks are waited for, and it's merged with the repository's
     method. The run shows those steps and ends with the conflict notes. With --no-checks (Ore's "Run the tests"
     left unticked) Claude checks its resolution by reading instead of running the suites on the changed code.
     When a workflow finishes, its part also carries "report": the orchestrator's report of the work (decisions and
     why, what wasn't done, what's pending, caveats; agents/<adw_id>/report.md).

  7. Queries: every status also says "queries": ["machine", "prs", "merge", "merge_run", "ask", "items", "consult",
     "revert"]. Ore then runs this script on its own
     with `--ore-query <name> [args]` (no stdin) and reads one line, {"type": "answer", "query", "data"} (exit 0)
     or {"type": "error", "message"} (exit 1). Queries never start workflows; only ask, items and consult call Claude,
     and only merge and revert write (to GitHub; revert in a temporary worktree):
     - machine: this machine, its workflow / full-suite slots, every codebase's leases and queued workflows (the
       machine-wide registry), free ports and Redis databases, and the latest Claude usage windows (five-hour,
       seven-day) from ~/.adw/usage.json, which every ADW claude process updates from its rate_limit_events;
     - prs: this repo's ADW pull requests (branch <type>-issue-<n>-adw-<id>-..., or "ADW ID:" in the body), open
       ones and those merged or closed in the last 14 days, with checks, review, mergeability and the issue;
     - merge <n>: merges ADW PR n if it's open (squash when the repo allows it, else merge, else rebase) and
       deletes its branch on GitHub. A worktree still on this machine is left alone;
     - ask <question> [<session id> [<file>...]]: the one query that calls Claude: a read-only Claude Code session (Read, Glob,
       Grep; plan mode; ADW_ASK_MODEL, default sonnet) in the repository's root, so CLAUDE.md, the project's docs and
       .claude/ are there, answers a question asked through Ore (e.g. from Telegram) in chat-sized plain text. The
       session id comes back, and passing it again continues the conversation (a follow-up question);
     - items <request.json>: the action items Ore found in a meeting for this workspace, read here so they come
       back in this codebase's own terms. Ore writes the request ({rules, prompt, schema, transcript, minutes}) and the
       transcript into .ore/items/<id>/; a read-only Claude Code session in the repository's root (as for ask, plus
       read-only git log / show and gh pr list / view, to tell whether an item is already done;
       ADW_ITEMS_MODEL, default ADW_ASK_MODEL) answers with the schema's structured output, returned as "items".
       The request's folder is removed afterwards.
     - consult <specialist> <request.json>: Ore asks one of the repository's specialists (adws/specialists/<name>.md:
       backlog, triage, planner, scoper for Ore's project manager, and after the build doctor, pr_reviewer,
       merge_planner, closer; built-in copies when the files are missing) for a structured answer. Ore writes the
       request ({specialist, version, workspace, goals, items, workspaces, session_id, message, schema, minutes};
       version 3 adds "run" for the doctor and "card" for the other three) into .ore/pm/<run id>/, attached files
       into its files/; a read-only
       Claude Code session in the repository's root (as for items; ADW_CONSULT_MODEL, default ADW_ITEMS_MODEL; no
       cost cap) gets the specialist's prompt as its system prompt and the request (the user's message and the
       attached files' paths first) as the message, and answers with the request's schema. With a session_id it
       continues that session (--resume). Returns {"result", "session_id", "cost_usd"}; the request's folder is
       removed afterwards. The consult sessions may also run git diff, gh pr diff and gh pr checks.
     - revert <n>: opens a pull request that reverts merged PR n: a temporary worktree (trees/revert-pr-<n>) on a new
       branch revert-<n>-<short sha> from the PR's base branch, git revert of its merge commit (-m 1 when it has two
       parents), push, gh pr create 'Revert "<title>"'. Returns {"number", "url"}; refuses unmerged PRs and
       conflicting reverts (the worktree and branches are cleaned up). The main checkout is never touched.

Follow-ups: a finished orchestrated workflow can be asked for more (Ore's Follow up, message mode "follow_up";
the run then also accepts "follow_up"). The same ADW continues: same worktree, branch, pull request and
orchestrator session, with the request as the session's next instruction; its steps start a new round. Ore
restarts a finished run with --resume <run-dir> --follow-up <request>; a running one gets the message on stdin.
A workflow still running gets a follow-up as a change (amend).

Files: the run's "accepts" lists "files", so Ore lets the user attach files to an answer or a message (it sends none
to a run that doesn't list it). Ore copies them into .ore/runs/<run id>/files/ and sends their repository-relative
paths as "files"; the trigger hands them to the Claude session or workflow the answer is for.

Ore's project board: every status says the run's "phase": "planning" through the questions, the groups check and the
specialists' checks, "building" from the moment the user starts the build (Ore draws the run in its Approved or Building lane), and
"accepts" also lists "withdraw" and "replan".
  - withdraw (stdin {"type": "withdraw", "id", "items": [positions], "reason"}): while planning, those items leave
    the plan and the groups (an open groups check is asked again without them), Claude hears why at its next turn,
    and a reply "Took out ..." answers the id. Once building, the reply says it can't.
  - replan (--resume <run-dir> --ore-replan <base64url JSON {id, reason, keep_work, items, prs}>): the workflows
    holding those items go back to planning (the others carry on and rejoin when the new groups start), with the
    reason as Claude's next input. keep_work true: they're stopped, their worktrees, branches and sessions kept, and
    the open pull requests turned into drafts; a new group with exactly the items of one of them continues it as a
    follow-up round (and its pull request is marked ready again when it finishes). keep_work false: they're undone
    as Delete would with the GitHub option (pull requests and issues closed, branches and worktrees removed) and
    planned from scratch. Then questions, the groups check and the workflows as usual.

If any workflow fails, the run fails in Ore once the others are finished. Resume then runs the failed
workflows again on the same issues, and those whose process died with Ore. An orchestrated workflow that got
past setup (worktree and orchestrator session still there) continues with the same ADW; the others get a fresh
ADW (the failed one's worktree, local branch, database and ports are removed first). The finished ones are left
alone.

Deleting the run in Ore undoes it (--cleanup): this script and its ADWs are stopped, and their worktrees,
local branches, isolated databases, Redis databases and resource leases are removed, with the run's
state. With the GitHub option ticked, the issues and open pull requests are closed and the branches
deleted on GitHub too. It is safe to run again after a partial failure.

State lives in agents/ore/<run-id>/state.json. Environment:
  ORE_MODEL (default opus), ORE_MODEL_SET (default base), ORE_MAX_PARALLEL (this run's own cap; default: no
  cap beyond the machine's ADW_MAX_WORKFLOWS slots), ORE_WORKFLOW (orchestrated, the default, or router),
  ORE_SIM_SPEED (--simulate time factor, default 1), ORE_CHECK_MAX_WAIT_MIN (default 30: how long a workflow
  that asked for the full check waits for the others before the check runs without them)
"""

import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ADWS_DIR = Path(__file__).resolve().parent.parent          # adws/ (this file is in adws/adw_triggers/)
REPO_ROOT = ADWS_DIR.parent
ROUTER = "adw_sdlc_router_iso.py"
ORCHESTRATED = "adw_orchestrated_sdlc_iso.py"
WORKFLOW_SCRIPTS = {"router": ROUTER, "orchestrated": ORCHESTRATED}


def _extend_path() -> None:
    """Ore runs this from a plain (non-login) shell, whose PATH lacks the user's tool folders. Add the
    usual ones, so `claude` and `uv` resolve here and in the ADWs this script starts (they inherit PATH)."""
    home = Path.home()
    extra = [home / ".local/bin", home / ".cargo/bin", home / ".npm-global/bin", home / ".claude/local",
             *sorted((home / ".nvm/versions/node").glob("*/bin"), reverse=True)[:1],
             Path("/opt/homebrew/bin"), Path("/usr/local/bin")]          # Homebrew on Apple silicon / Intel Macs
    path = os.environ.get("PATH", "").split(os.pathsep)
    os.environ["PATH"] = os.pathsep.join([str(p) for p in extra if p.is_dir() and str(p) not in path] + path)


_extend_path()


def _bootstrap() -> None:
    """Ore starts this with plain python3; re-run under uv so the script's dependencies are there."""
    try:
        import dotenv  # noqa: F401
        import pydantic  # noqa: F401
    except ImportError:
        uv = shutil.which("uv") or next((str(p) for p in (Path.home() / ".local/bin/uv", Path.home() / ".cargo/bin/uv")
                                         if p.exists()), None)
        if not uv or os.environ.get("ORE_BOOTSTRAPPED"):
            sys.exit("This script needs uv (https://docs.astral.sh/uv/) to install its dependencies.")
        os.environ["ORE_BOOTSTRAPPED"] = "1"
        os.execv(uv, [uv, "run", "--quiet", "--script", __file__, *sys.argv[1:]])


_bootstrap()
sys.path.insert(0, str(ADWS_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")     # e.g. ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN for Claude Code

from adw_modules import batch_check, messages, resources, steps  # noqa: E402
from adw_modules.github import extract_repo_path, get_repo_url  # noqa: E402
from adw_modules.state import ADWState  # noqa: E402
from adw_modules.utils import get_safe_subprocess_env, make_adw_id  # noqa: E402

_out_lock = threading.Lock()


def emit(msg: dict) -> None:
    """One protocol message on stdout (docs/script-protocol.md §3); thread-safe."""
    with _out_lock:
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()


# What a run takes from Ore besides answers (status "accepts"): messages to its workflows, follow-ups on finished
# ones, taking items out while it plans (stdin "withdraw"), going back to planning (--ore-replan), and files with
# answers and messages ("files": Ore sends them only to a run that lists it; split_files/repo_files read them).
ACCEPTS = ("message", "follow_up", "withdraw", "replan", "files")


def ore_status(message, progress=None, parts=None, stages=None, usage=None, phase=None):
    """A status message (docs/script-protocol.md §3), with the run's stages, usage and phase ("planning" or
    "building"), which ore_sdk.status() lacks; under Ore it says what the run accepts."""
    msg = {"type": "status", "message": message, "progress": progress}
    if parts is not None:
        msg["parts"] = parts
    if stages is not None:
        msg["stages"] = stages
    if usage:
        msg["usage"] = usage
    if phase:
        msg["phase"] = phase
    if IO.enabled:
        msg["accepts"] = list(ACCEPTS)
        msg["queries"] = list(QUERIES)
    emit(msg)


try:
    from ore_sdk import ask_questions, checkpoint, error, log, result, review_groups

    status = ore_status
except ImportError:                       # run by hand, outside Ore: answer in the terminal
    def status(message, progress=None, parts=None, stages=None, usage=None, phase=None):
        print(f"[status] {message}"
              + (" [" + " > ".join(f"{st['label']}: {st['status']}" for st in stages) + "]" if stages else "")
              + "".join(f"\n  - {p['label']}: {p['status']} {p['message']}" for p in parts or []))

    def checkpoint(*args):
        print(f"[checkpoint] resume with: {' '.join(args)}")

    def log(message):
        print(message, file=sys.stderr)

    def error(message, exit_code=1):
        sys.exit(message)

    def result(summary, links=(), actions=(), data=None):
        print(f"[result] {summary}\n" + "\n".join(f"  {a}: {b}" for a, b in links))

    def ask_questions(questions, prompt="", key=None):
        print(prompt)
        out = {}
        for q in questions:
            print(f"\n{q['question']}")
            for n, o in enumerate(q["options"], 1):
                print(f"  {n}. {o['label']} - {o.get('description', '')}")
            raw = input("Number(s), or your own answer: ").strip()
            picks = [q["options"][int(x) - 1]["label"] for x in raw.replace(",", " ").split() if x.isdigit()]
            out[q["question"]] = (picks if q.get("multiSelect") else picks[0]) if picks else raw
        return out

    def review_groups(groups, prompt="", key=None):
        for g in groups:
            print(f"\n## {g['title']}\n{g.get('summary', '')}")
            for it in g["items"]:
                print(f"  - [{it['id']}] {it['title']}")
        fb = input("\nPress Enter to start, or type what should change: ").strip()
        if fb:
            return {"action": "change", "feedback": fb}
        return {"action": "start", "groups": [{"title": g["title"], "item_ids": [i["id"] for i in g["items"]]}
                                              for g in groups]}

try:
    from ore_sdk import cleanup, cleanup_options
except ImportError:                       # outside Ore, or an Ore without run deletion
    def cleanup(*args, description="", options=()):
        pass

    def cleanup_options():
        return {k for k in os.getenv("ORE_CLEANUP_OPTIONS", "").split(",") if k}


_MISSING = object()


class OreInput:
    """Ore's stdin (docs/script-protocol.md §4), read by one thread: answers to input requests (by id) and the
    user's messages to the run or a part. Under Ore (ORE_PROTOCOL set) the trigger asks its own questions through
    this too, so a message can arrive at any time, also while a question is open."""

    def __init__(self):
        self.enabled = False
        self.closed = False
        self.answers: dict = {}
        self.messages: list = []
        self.lock = threading.Lock()

    def start(self) -> None:
        if self.enabled:
            return
        self.enabled = True
        threading.Thread(target=self._read, daemon=True, name="ore-stdin").start()

    def _read(self) -> None:
        try:
            for line in sys.stdin:
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                with self.lock:
                    if msg.get("type") in ("message", "withdraw"):
                        self.messages.append(msg)
                    elif "id" in msg:
                        self.answers[str(msg["id"])] = msg.get("value")
        finally:
            self.closed = True

    def take_messages(self) -> list[dict]:
        with self.lock:
            out, self.messages = self.messages, []
        return out

    def answer(self, key: str):
        with self.lock:
            return self.answers.pop(key, _MISSING)

    def wait(self, key: str, tick=None):
        """Block until the answer to input request `key`; tick() runs meanwhile (e.g. to answer messages)."""
        while True:
            value = self.answer(key)
            if value is not _MISSING:
                return value
            if self.closed:
                raise EOFError("Ore closed the input stream before answering")
            if tick:
                tick()
            time.sleep(0.2)


IO = OreInput()
_while_waiting: list = []                # what runs while a question waits (handle_messages for the current run)


def _tick() -> None:
    for fn in _while_waiting:
        fn()


def _io_ask_questions(questions, prompt="", key=None):
    emit({"type": "input_request", "id": key, "prompt": prompt or "Please answer", "kind": "questions",
          "questions": questions})
    return IO.wait(key, _tick)


def _io_review_groups(groups, prompt="", key=None):
    emit({"type": "input_request", "id": key, "prompt": prompt or "Review the groups", "kind": "groups",
          "groups": groups})
    return IO.wait(key, _tick)


def use_ore_input() -> None:
    """Under Ore: read stdin in a thread, and ask through it (so the run can take messages)."""
    global ask_questions, review_groups
    if not os.getenv("ORE_PROTOCOL"):
        return
    IO.start()
    ask_questions, review_groups = _io_ask_questions, _io_review_groups


def reply(to: str, text: str, part: str | None = None) -> None:
    """A reply to a user's message (shown under it in Ore)."""
    msg = {"type": "reply", "to": str(to), "text": str(text)[:4000]}
    if part is not None:
        msg["part"] = part
    if IO.enabled:
        emit(msg)
    else:
        log(f"[reply to {to}{f' ({part})' if part else ''}] {text}")

def repo_files(raw) -> list[str]:
    """The files the user attached to an answer or a message (Ore copies them into .ore/runs/<run id>/files/ and
    sends their repository-relative paths): absolute paths, only those inside the repository's .ore/."""
    inbox = (REPO_ROOT / ".ore").resolve()
    out = []
    for f in raw if isinstance(raw, list) else []:
        if not isinstance(f, str) or not f.strip():
            continue
        path = Path(f).expanduser()
        path = (path if path.is_absolute() else REPO_ROOT / path).resolve()
        if inbox in path.parents:
            out.append(str(path))
        else:
            log(f"Ignored an attached file outside .ore/: {f}")
    return out


def split_files(value) -> tuple:
    """(the answer without its files, the attached files' absolute paths). With files, Ore sends a text answer as
    {"text", "files"} and adds "files" to the other answers' objects (questions, groups, review)."""
    if isinstance(value, dict) and "files" in value:
        rest = {k: v for k, v in value.items() if k != "files"}
        files = repo_files(value.get("files"))
        return (rest["text"] if set(rest) == {"text"} else rest), files
    return value, []


def files_text(files: list[str]) -> str:
    """The attached files, for a Claude session's message."""
    if not files:
        return ""
    return ("\n\nFiles the user attached (read each with the Read tool; it reads images and PDFs directly, and an "
            "Office document's text is in the .txt file beside it):\n" + "\n".join(f"- {f}" for f in files))


MODEL = os.getenv("ORE_MODEL", "opus")
MODEL_SET = os.getenv("ORE_MODEL_SET", "base")
MAX_PARALLEL = int(os.getenv("ORE_MAX_PARALLEL", "0") or 0) or 10 ** 6     # 0: only the machine's slots
EXIT_NO_RESOURCES = 75                    # a workflow that found no free ports / Redis (EX_TEMPFAIL): re-queue
REQUEUE_DELAY = 60
MACHINE = "this Mac" if sys.platform == "darwin" else "this machine"


def workflow_mode() -> str:
    """Which workflow each issue gets: "orchestrated" (default: adw_orchestrated_sdlc_iso.py) or "router" (the
    SDLC router picks single- or multi-phase). From ORE_WORKFLOW."""
    mode = os.getenv("ORE_WORKFLOW", "orchestrated").strip().lower()
    return mode if mode in WORKFLOW_SCRIPTS else "orchestrated"


def free_workflow_slots() -> int:
    """Workflow slots free on this machine right now (all codebases), at least 1: the grouping target."""
    try:
        if resources.enabled():
            return max(1, resources.free_slots(resources.WORKFLOW))
    except Exception as e:  # noqa: BLE001 - the registry unreadable: fall back to the configured limit
        log(f"Couldn't read the resource registry: {e}")
    try:
        return max(1, int(os.getenv("ADW_MAX_WORKFLOWS", "4")))
    except ValueError:
        return 4

TURN_TIMEOUT = 30 * 60
SIZES = ("S", "M", "L")                    # small, medium, large: Ore's planner's sizes, smallest first
FRONTEND = ("none", "small", "significant")    # how much a group changes the screens, least first
PR_URL = re.compile(r"https://github\.com/[^\s)]+/pull/\d+")
LOG_LINES = 10                            # progress comments a part's log keeps
COMMENT_PREFIX = re.compile(r"^\[ADW-AGENTS\]\s*(\S+?_\S+?:\s*)?")
# Rough position in the SDLC pipeline from the wording of ADW comments: (keyword, progress, phase label)
PHASES = [("routing decision", 0.05, "Routing"), ("planning", 0.1, "Planning"), ("plan", 0.15, "Planning"),
          ("build", 0.35, "Building"), ("implement", 0.35, "Building"), ("test", 0.55, "Testing"),
          ("smoke", 0.65, "Smoke testing"), ("review", 0.75, "Reviewing"), ("document", 0.85, "Documenting"),
          ("pull request", 0.95, "Pull request"), ("sdlc workflow completed", 1.0, "Done")]

CLARIFY_RULES = """You are preparing work for an automated SDLC pipeline (ADW) in this repository.
You receive action items approved from a meeting transcript. The transcript came from speech recognition:
expect misheard words and mixed languages, and work out what was meant.

Your job, in this order:
1. Investigate: read CLAUDE.md, the relevant ai_docs and the code each item touches, until you understand
   what each item asks for and where it lives. You can only read; do not try to change anything.
2. Clarify: an item is clear when a developer who knows this codebase could implement it without asking
   anything. Ask only about items that are not clear, and only what you could not find out from the repo.
   Ask multiple-choice questions (2 to 4 options each, with a short description per option, multiSelect
   when several can apply; the user can always type their own answer). At most 4 questions per round.
   Put concrete options from the codebase in front of the user rather than open questions.
3. Group: once everything is clear, group the items into workflows. Each group becomes one GitHub issue,
   one branch, one PR and one Orchestrated SDLC workflow, which splits its items into work packages and
   runs them in parallel inside one worktree. So bigger groups are cheap, and every extra group costs a
   whole workflow (a worktree, a running app, its own full test suites) on a machine that runs only a few
   at a time. Group by repo surface, using what you read in the code:
   - items that touch the same pages, modules or services go in one group;
   - small chores and polish items (copy, styling, small fixes) are bundled together in one group;
   - split only when items are large AND independent of each other.
   Target: at most {target} group(s): that is how many workflow slots are free on {machine} right now.
   Use more only when you have to, and then say why in grouping_reason.
   For every group also give:
   - size: S (a small change in one place), M (a few files or one feature, about a day) or L (several parts of
     the code, a new feature or a migration). Use the items' "Size:" when they have one;
   - frontend: how much it changes what users see: none (nothing visible), small (copy, styling, a field or a
     button on an existing screen) or significant (a new screen or flow, or a visible redesign of one). Before
     anything is built, a designer makes a clickable prototype of every significant group for the user to approve,
     a risk reviewer looks at the M and L groups, and a test planner writes how we'll know each group works.

Always reply with JSON matching the schema:
- {"status": "questions", "questions": [...]} while something is unclear
- {"status": "ready", "groups": [{"title", "summary", "item_ids", "size", "frontend"}], "grouping_reason"} once
  everything is clear (grouping_reason: why the items are grouped this way, and why more groups than the target if so).
  When the user asked for changes at the build check, keep the same groups (the same items) unless the change needs
  other groups, and give each group "recheck": the checks the change affects ("design", "risk", "tests"), empty when
  none
- {"status": "issues", "groups": [{"title", "item_ids", "issue_title", "issue_body"}]} only when asked to
  write the issues for confirmed groups."""

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["questions", "ready", "issues"]},
        "questions": {"type": "array", "maxItems": 4, "items": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "header": {"type": "string", "description": "A label of at most 12 characters"},
                "options": {"type": "array", "minItems": 2, "maxItems": 4, "items": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}, "description": {"type": "string"}},
                    "required": ["label", "description"]}},
                "multiSelect": {"type": "boolean"}},
            "required": ["question", "header", "options", "multiSelect"]}},
        "grouping_reason": {"type": "string", "description": "Why the items are grouped like this; required "
                            "when there are more groups than the target"},
        "groups": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "summary": {"type": "string"},
                "item_ids": {"type": "array", "items": {"type": "string"},
                             "description": "Item numbers as plain strings, e.g. [\"1\", \"3\"]"},
                "size": {"type": "string", "enum": list(SIZES)},
                "frontend": {"type": "string", "enum": list(FRONTEND),
                             "description": "none: nothing visible changes; small: copy, styling, a field or button "
                                            "on an existing screen; significant: a new screen or flow, or a visible "
                                            "redesign (gets a prototype the user approves)"},
                "recheck": {"type": "array", "items": {"type": "string", "enum": ["design", "risk", "tests"]},
                            "description": "Only after changes asked at the build check: the checks they affect"},
                "issue_title": {"type": "string"},
                "issue_body": {"type": "string", "description": "Markdown: context, what to build or fix, "
                               "acceptance criteria, relevant files, and the clarifications agreed with the user"}},
            "required": ["title", "item_ids"]}},
    },
    "required": ["status"],
}

ISSUES_PROMPT = """The user confirmed these groups. Write one GitHub issue per group: issue_title (short,
imperative) and issue_body in Markdown with: Context (from the meeting, in English), What to do,
Acceptance criteria, Relevant files and docs you found, and the Clarifications agreed with the user.
It goes to an automated planner, so be specific. Reply with status "issues".

Confirmed groups:
{groups}"""


# ---- action items --------------------------------------------------------

def parse_items(path: Path) -> list[dict]:
    """Ore batch files: JSON {"items": [...]} or Markdown "- [ ] title" blocks. An item's "images" are reference
    images Ore saved next to the batch file (a note's screenshots): their paths, from "Image: <path>" lines. An item's
    "criteria" are the acceptance criteria agreed in Ore: JSON "criteria", or the Markdown "Acceptance criteria:"
    block of "- " lines. An item's "size" (S, M or L, from Ore's planner) is JSON "size" or a Markdown "Size: M" line;
    None when Ore sent none."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        return [{"id": str(n), "title": it["title"], "detail": it.get("detail") or "", "images": it.get("images") or [],
                 "criteria": [str(c).strip() for c in it.get("criteria") or [] if str(c).strip()],
                 "size": item_size(it.get("size")),
                 "text": json.dumps(it, ensure_ascii=False, indent=1)} for n, it in enumerate(data["items"], 1)]
    items: list[dict] = []
    block = None                                      # the indented block ("Transcript:", ...) a "- " line is in
    for line in text.splitlines():
        if line.startswith("- [ ] "):
            items.append({"id": str(len(items) + 1), "title": line[6:].strip(), "detail": "", "images": [],
                          "criteria": [], "size": None, "text": line})
            block = None
        elif items:
            items[-1]["text"] += "\n" + line
            s = line.strip()
            if s in ("Transcript:", "Acceptance criteria:"):
                block = s
            elif not s:
                block = None
            elif s.startswith("- ") and block == "Acceptance criteria:":
                items[-1]["criteria"].append(s[2:].strip())
            elif s.startswith("Image: "):
                items[-1]["images"].append(s[len("Image: "):].strip())
            elif s.startswith("Size: ") and block is None:
                items[-1]["size"] = item_size(s[len("Size: "):])
            elif not items[-1]["detail"] and not s.startswith((">", "Transcript:", "- ")):
                items[-1]["detail"] = s
    return items


def item_size(raw) -> str | None:
    """S, M or L from Ore's "size" ("M", "m", "Medium"), else None."""
    s = str(raw or "").strip().upper()[:1]
    return s if s in SIZES else None


def item_id(raw) -> str:
    """A batch item's id as Ore or Claude may write it: "1", "Item 1" and "#1" all mean item 1."""
    m = re.search(r"\d+", str(raw))
    return m.group(0) if m else str(raw)


def planned_items(run) -> list[dict]:
    """The items the run plans now: not taken out (withdraw), and within the replan's scope while it plans again."""
    withdrawn, scope = run.s.get("withdrawn") or {}, run.s.get("scope")
    return [it for it in run.s["items"] if it["id"] not in withdrawn and (scope is None or it["id"] in scope)]


def images_section(images: list[str]) -> str:
    """The issue's reference images: exact paths for the agent to open (Read), whatever Claude wrote above."""
    if not images:
        return ""
    return ("\n\n## Reference images\nScreenshots or mockups that came with the request: open each one (Read) "
            "before planning, and match them exactly.\n" + "\n".join(f"- `{p}`" for p in images))


def criteria_section(criteria: list[str]) -> str:
    """The issue's acceptance criteria agreed with the user in Ore, whatever Claude wrote above."""
    if not criteria:
        return ""
    return ("\n\n## Acceptance criteria agreed in Ore\nThe user agreed these before approving: the work must meet each "
            "one.\n" + "\n".join(f"- {c}" for c in criteria))


def item_text(it: dict) -> str:
    """An item as the planning prompt shows it: the batch file's text, with its agreed acceptance criteria spelled
    out when the text doesn't already list them (JSON batches)."""
    text = it["text"].strip()
    if it.get("criteria") and "Acceptance criteria:" not in text:
        text += "\nAcceptance criteria:\n" + "\n".join(f"- {c}" for c in it["criteria"])
    return text


def items_prompt(items: list[dict], source: str) -> str:
    body = "\n\n".join(f"### Item {it['id']}\n{item_text(it)}" for it in items)
    note = ("\n\n`Image:` lines are reference images (screenshots, mockups) on this machine: open them with Read."
            if any(it.get("images") for it in items) else "")
    if any(it.get("criteria") for it in items):
        note += ("\n\n`Acceptance criteria:` were agreed with the user in Ore: don't ask about what they settle, and "
                 "carry them into the issues' acceptance criteria.")
    return f"Action items approved in Ore (from {source}):\n\n{body}{note}\n\nStart with step 1."


# ---- state ---------------------------------------------------------------

class Run:
    def __init__(self, run_dir: Path):
        self.dir = run_dir
        self.path = run_dir / "state.json"
        self.s: dict = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    @classmethod
    def new(cls, items_file: Path | None, dry_run: bool, simulate: bool = False) -> "Run":
        run_id = make_adw_id()
        run = cls(REPO_ROOT / "agents" / "ore" / run_id)
        run.dir.mkdir(parents=True, exist_ok=True)
        if items_file is None:                       # --simulate without a batch: the sample items
            items_file = run.dir / "sample_batch.md"
            items_file.write_text(SIM_BATCH, encoding="utf-8")
        items = parse_items(items_file)
        if not items:
            error(f"No action items found in {items_file}")
        if items_file.parent != run.dir:
            shutil.copy(items_file, run.dir / items_file.name)
        run.s = {"run_id": run_id, "items_file": str(items_file), "items": items, "phase": "clarify",
                 "session_id": None, "next_message": None, "pending": None, "groups": [], "dry_run": dry_run,
                 "simulate": simulate,
                 "model": MODEL, "model_set": MODEL_SET,
                 "created_at": datetime.now().isoformat(timespec="seconds")}
        run.save()
        return run

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.s, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)


# The run's own stages, as Ore draws them across the top: (key, label, phases while it's running)
STAGES = [("clarify", "Questions", ("clarify",)), ("review", "Your check", ("review",)),
          ("checks", "Checks", ("checks",)), ("issues", "Issues", ("issues", "workflows")),
          ("workflows", "Workflows", ("workflows",))]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def iso(epoch) -> str | None:
    return datetime.fromtimestamp(epoch).isoformat(timespec="seconds") if epoch else None


def stage_start(run: Run, key: str) -> None:
    """Record when a run stage starts (again: going back to the questions reopens them)."""
    st = run.s.setdefault("stages", {}).setdefault(key, {})
    st.setdefault("started", now_iso())
    st.pop("ended", None)


def stage_end(run: Run, key: str, note: str | None = None) -> None:
    st = run.s.setdefault("stages", {}).setdefault(key, {})
    st.setdefault("started", now_iso())
    st["ended"] = now_iso()
    if note is not None:
        st["note"] = note


def issue_range(groups: list[dict]) -> str:
    nums = sorted(int(g["issue_number"]) for g in groups if str(g.get("issue_number") or "").isdigit())
    if not nums:
        n = sum(bool(g.get("issue_number")) for g in groups)
        kind = "simulated" if any(str(g.get("issue_number") or "").startswith("sim-") for g in groups) else "dry run"
        return f"{n} issue{'s' if n != 1 else ''} ({kind})" if n else ""
    return f"#{nums[0]}" if len(nums) == 1 else f"#{nums[0]}\u2013#{nums[-1]}"


def stages(run: Run) -> list[dict]:
    """The run's stages for every status message: done before the current phase, running in it, then pending."""
    phase, saved, groups = run.s.get("phase"), run.s.get("stages") or {}, run.s.get("groups") or []
    order = ["clarify", "review", "checks", "issues", "workflows", "done"]
    at = order.index(phase) if phase in order else 0
    out = []
    for key, label, active in STAGES:
        st = saved.get(key, {})
        if key == "issues" and phase == "workflows":       # issues are created as workflows start
            ended = all(g.get("issue_number") or g.get("status") == "failed" for g in groups)
            status_ = "done" if ended else "running"
        elif phase in active:
            status_ = "running"
        elif st.get("ended") or order.index(key) < at:
            status_ = "done"
        else:
            status_ = "pending"
        if key == "workflows" and phase == "done" and any(g.get("status") == "failed" for g in groups):
            status_ = "failed"
        note = st.get("note") or ""
        if key == "clarify" and not note and run.s.get("question_rounds"):
            n = run.s["question_rounds"]
            note = f"{n} round{'s' if n != 1 else ''}"
        elif key == "review" and not note and groups and at > 1:
            note = f"{len(groups)} workflow{'s' if len(groups) != 1 else ''}"
        elif key == "issues":
            note = issue_range(groups)
        elif key == "workflows" and groups and at >= order.index("workflows"):
            counts = {k: sum(g.get("status") == k for g in groups) for k in ("done", "running", "failed", "queued")}
            note = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
        out.append({"key": key, "label": label, "status": status_, "started": st.get("started"),
                    "ended": st.get("ended") if status_ in ("done", "failed") else None, "note": note})
    return out


PLANNING = ("clarify", "review", "checks")  # the run's phases Ore calls "planning"; from "issues" on, "building"
_last_status = [""]


def run_phase(run: Run) -> str:
    """The run's phase for Ore (status "phase"): planning through the questions, the groups check and the
    specialists' checks, building once the user said to start building (issues, workflows, done)."""
    return "planning" if run.s.get("phase") in PLANNING else "building"


def report(run: Run, message: str, progress=None, parts=None) -> None:
    phase = run_phase(run)
    if parts is None and phase == "planning":
        # planning again: the workflows it keeps are parts; so are the groups the specialists check (or checked,
        # while the questions run again after the build check)
        built = run.s.get("kept_groups") or [g for g in run.s.get("groups") or [] if g.get("status")]
        checking = new_groups(run) if run.s.get("phase") == "checks" else run.s.get("checked_groups") or []
        if "kept_groups" in run.s or built or checking:
            parts = parts_of(run, built) + [check_part(run, g) for g in checking]
    usage = run_usage(run, parts or []) if (parts or run.s.get("usage")) else None
    _last_status[0] = message
    status(message, progress=progress, parts=parts, stages=stages(run), usage=usage or None, phase=phase)


# ---- Claude ---------------------------------------------------------------

class ClaudeAuthError(RuntimeError):
    """Claude Code can't sign in. Retrying won't help; the user has to fix it, then press Resume."""


AUTH_FAILURE = re.compile(r"not logged in|/login|invalid api key|api key|oauth|authenticat|unauthori[sz]ed|"
                          r"credential|token (has )?expired", re.I)


def auth_problem(out: dict, stderr: str) -> str | None:
    """A user-facing explanation when a claude -p result failed because it isn't signed in, else None."""
    text = f"{out.get('result') or ''} {stderr}"
    rejected = out.get("api_error_status") in (401, 403)
    failed = bool(out.get("is_error")) or not out          # no JSON at all: the CLI stopped before answering
    if not (rejected or (failed and AUTH_FAILURE.search(text))):
        return None
    reason = (out.get("result") or (stderr.strip().splitlines() or [""])[-1]).strip()
    if os.getenv("ANTHROPIC_API_KEY") or "api key" in text.lower():
        return (f"Claude Code rejected the API key ({reason}). It comes from ANTHROPIC_API_KEY in this repo's .env "
                "or the environment, and it takes priority over `claude login`. Fix the key, or remove it to use "
                "your Claude subscription, then press Resume.")
    if os.getenv("CLAUDE_CODE_OAUTH_TOKEN"):
        return (f"Claude Code rejected the token in CLAUDE_CODE_OAUTH_TOKEN ({reason}). Create a new one with "
                "`claude setup-token` and update it in this repo's .env, then press Resume.")
    if sys.platform == "darwin":
        return (f"Claude Code can't sign in over SSH on this Mac ({reason}). macOS keeps the Claude login in the "
                "login Keychain, which SSH sessions can't open. On the Mac, run `claude setup-token` once and add "
                "the token to this repo's .env as CLAUDE_CODE_OAUTH_TOKEN=..., then press Resume. Your answers so "
                "far are kept.")
    return (f"Claude Code isn't signed in on {socket.gethostname()} ({reason}). Run `claude` there and sign in with "
            "/login, or add a token from `claude setup-token` to this repo's .env as CLAUDE_CODE_OAUTH_TOKEN=..., "
            "then press Resume. Your answers so far are kept.")


def check_claude_auth() -> str:
    """Fail fast, for free, if Claude Code isn't signed in; returns how it's signed in (for the status line).

    Uses the same environment as the ADWs, so an ANTHROPIC_API_KEY from the repo's .env counts. It can't tell
    whether a key or token is still valid; claude_turn() catches those when the first request is rejected.
    """
    claude = os.getenv("CLAUDE_CODE_PATH", "claude")
    try:
        proc = subprocess.run([claude, "auth", "status"], cwd=REPO_ROOT, env=get_safe_subprocess_env(),
                              capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise ClaudeAuthError(f"Claude Code (`claude`) isn't installed on {socket.gethostname()}, or isn't on "
                              "PATH. Install it, sign in, then press Resume.")
    except subprocess.TimeoutExpired:
        return "unknown"                 # don't block on the check itself; the first turn will tell
    try:
        info = json.loads(proc.stdout)
    except ValueError:
        return "unknown"                 # an older CLI without JSON status
    if not info.get("loggedIn"):
        raise ClaudeAuthError(auth_problem({"is_error": True, "result": "Not logged in"}, ""))
    method = info.get("authMethod") or ""
    return {"claude.ai": "your Claude subscription", "api_key": "an API key (billed per token)",
            "oauth_token": "a Claude subscription token (CLAUDE_CODE_OAUTH_TOKEN)"}.get(method, method)


def clarify_rules(target: int) -> str:
    """CLARIFY_RULES with the grouping target: the workflow slots free on this machine now."""
    return CLARIFY_RULES.replace("{target}", str(target)).replace("{machine}", MACHINE)


def claude_turn(run: Run, message: str) -> dict:
    """One clarification turn, resuming the session. Returns Claude's structured reply. Notes about the plan that
    came in meanwhile (items the user took out) go first, once."""
    notes = run.s.get("planning_notes") or []
    if run.s.get("simulate"):
        run.s.pop("planning_notes", None)
        return simulated_turn(run, message)
    if notes:
        message = "\n".join(notes) + "\n\n" + message
    target = free_workflow_slots()
    run.s["slots_free"] = target
    claude = os.getenv("CLAUDE_CODE_PATH", "claude")
    message += (f"\n\n(Workflow slots free on {MACHINE} right now: {target}. When you propose groups, aim for at "
                f"most {target}.)")
    cmd = [claude, "-p", message, "--output-format", "stream-json", "--verbose", "--json-schema", json.dumps(SCHEMA),
           "--model", MODEL, "--append-system-prompt", clarify_rules(target),
           "--allowedTools", "Read", "Glob", "Grep", "--disallowedTools", "Edit", "Write", "NotebookEdit"]
    if run.s["session_id"]:
        cmd += ["--resume", run.s["session_id"]]
    mcp = REPO_ROOT / ".mcp.json"
    if mcp.exists():
        cmd += ["--mcp-config", str(mcp)]
    for attempt in (1, 2):
        try:
            proc = subprocess.run(cmd, cwd=REPO_ROOT, env=get_safe_subprocess_env(), capture_output=True, text=True,
                                  timeout=TURN_TIMEOUT)
        except subprocess.TimeoutExpired:
            if attempt == 2:
                raise RuntimeError(f"Claude didn't answer within {TURN_TIMEOUT // 60} minutes")
            continue
        out = turn_result(proc.stdout)
        if out.get("session_id"):
            run.s["session_id"] = out["session_id"]
            run.save()
        if out.get("total_cost_usd") is not None:
            run.s["usage"] = messages.add_usage(run.s.get("usage") or {}, messages.result_usage(out))
        reply = out.get("structured_output")
        if proc.returncode == 0 and not out.get("is_error") and isinstance(reply, dict):
            if notes:
                run.s.pop("planning_notes", None)
            return reply
        problem = auth_problem(out, proc.stderr)
        if problem:
            raise ClaudeAuthError(problem)
        log(f"Claude turn failed (attempt {attempt}): {proc.stderr.strip()[-500:] or out.get('result')}")
    raise RuntimeError("Claude Code didn't return a usable reply; see the script output")


def turn_result(stdout: str) -> dict:
    """The result message of a `claude -p --output-format stream-json` turn ({} when there is none). Its
    rate_limit_events go to the machine-wide usage file on the way (Ore's machine view)."""
    out: dict = {}
    for line in (stdout or "").splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        if msg.get("type") in ("result", None):        # None: a plain JSON result (--output-format json, older CLI)
            out = msg
        elif msg.get("type") == "rate_limit_event" and isinstance(msg.get("rate_limit_info"), dict):
            messages.record_machine_usage(msg["rate_limit_info"])
    return out


# ---- phases ---------------------------------------------------------------

def clarify(run: Run) -> None:
    """Ask, answer, repeat; ends with proposed groups in run.s["groups"] and phase 'review'."""
    stage_start(run, "clarify")
    while run.s["phase"] == "clarify":
        handle_messages(run)                     # e.g. items taken out while Claude was thinking
        pending = run.s["pending"]
        if pending and pending.get("questions"):
            answers = ask_questions(pending["questions"], "Claude needs a few answers before it can start",
                                    key=pending["key"])
            answers, files = split_files(answers)
            said = json.dumps(answers, ensure_ascii=False, indent=1) + files_text(files)
            run.s.setdefault("clarifications", []).append(said)
            run.s.update(pending=None, next_message="My answers:\n" + said
                         + "\nContinue: ask more if anything is still unclear, otherwise propose the groups.")
            run.save()
            continue
        message = run.s["next_message"] or items_prompt(planned_items(run), Path(run.s["items_file"]).name)
        report(run, "Claude is planning again" if run.s.get("replanning") else
               "Claude is reading the repository and the action items" if not run.s["session_id"]
               else "Claude is working through your answers")
        reply = claude_turn(run, message)
        run.s.pop("replanning", None)
        run.s["turn"] = run.s.get("turn", 0) + 1
        questions = valid_questions(reply.get("questions"))
        if reply.get("status") == "questions" and questions:
            run.s.update(pending={"key": f"clarify-{run.s['turn']}", "questions": questions}, next_message=None)
            run.s["question_rounds"] = run.s.get("question_rounds", 0) + 1
            report(run, "Claude needs a few answers before it can start")
        elif reply.get("status") == "ready" and reply.get("groups") and same_groups_again(run, reply["groups"]):
            n = run.s.get("question_rounds", 0)
            stage_end(run, "clarify", f"{n} round{'s' if n != 1 else ''}" if n else "No questions")
            stage_end(run, "review", "Same groups")
            report(run, "The groups stay as they were; the specialists look at your changes")
        elif reply.get("status") == "ready" and reply.get("groups"):
            run.s.update(groups=normalise_groups(run, reply["groups"]), phase="review", next_message=None,
                         pending={"key": f"review-{run.s['turn']}"},
                         grouping={"slots_free": run.s.get("slots_free") or free_workflow_slots(),
                                   "reason": str(reply.get("grouping_reason") or "").strip()})
            n = run.s.get("question_rounds", 0)
            stage_end(run, "clarify", f"{n} round{'s' if n != 1 else ''}" if n else "No questions")
            stage_start(run, "review")
            report(run, "Check the workflows before they start")
        else:
            run.s["next_message"] = ("Your reply had neither questions nor groups. Ask questions, or propose the "
                                     "groups with status ready.")
        run.save()


def valid_questions(questions) -> list[dict]:
    """Questions with a text and at least two labelled options; anything malformed is dropped."""
    out = []
    for q in questions if isinstance(questions, list) else []:
        opts = q.get("options") if isinstance(q, dict) else None
        if not isinstance(opts, list):
            continue
        opts = [o if isinstance(o, dict) else {"label": str(o), "description": ""} for o in opts]
        opts = [{"label": str(o.get("label") or "").strip(), "description": str(o.get("description") or "")}
                for o in opts if str(o.get("label") or "").strip()]
        if q.get("question") and len(opts) >= 2:
            out.append({"question": str(q["question"]), "header": str(q.get("header") or "")[:24],
                        "options": opts[:4], "multiSelect": bool(q.get("multiSelect"))})
    return out[:4]


def normalise_groups(run: Run, groups: list[dict]) -> list[dict]:
    """Keep every planned item exactly once: anything Claude left out goes into its own group; items taken out
    (or outside a replan's scope) are left out."""
    items = planned_items(run)
    known = {it["id"] for it in items}
    seen: set[str] = set()
    out = []
    for g in groups:
        ids = []
        for raw in g.get("item_ids") or []:
            i = item_id(raw)
            if i in known and i not in seen:
                ids.append(i)
                seen.add(i)
        if ids:
            out.append({"title": g.get("title") or "Untitled", "summary": g.get("summary") or "", "item_ids": ids,
                        **group_marks(g)})
    for it in items:
        if it["id"] not in seen:
            out.append({"title": it["title"], "summary": "", "item_ids": [it["id"]]})
    return out


def group_marks(g: dict) -> dict:
    """The planner's marks on a group, only those it gave: size (S/M/L), frontend (none/small/significant) and, after
    the build check, recheck (the checks the user's changes affect)."""
    out = {}
    if g.get("size") in SIZES:
        out["size"] = g["size"]
    if g.get("frontend") in FRONTEND:
        out["frontend"] = g["frontend"]
    recheck = [k for k in CHECK_KINDS if k in (g.get("recheck") or [])]
    if recheck:
        out["recheck"] = recheck
    return out


def inherit_marks(groups: list[dict], proposed: list[dict]) -> list[dict]:
    """The user's groups (title and items only) take the marks of the proposed groups their items came from: the
    largest size, the most frontend, every recheck; and the summary of a group they left as it was."""
    for g in groups:
        ids = set(g["item_ids"])
        src = [p for p in proposed if ids & set(p.get("item_ids") or [])]
        sizes = [p["size"] for p in src if p.get("size") in SIZES]
        fronts = [p["frontend"] for p in src if p.get("frontend") in FRONTEND]
        if sizes:
            g["size"] = max(sizes, key=SIZES.index)
        if fronts:
            g["frontend"] = max(fronts, key=FRONTEND.index)
        recheck = [k for k in CHECK_KINDS if any(k in (p.get("recheck") or []) for p in src)]
        if recheck:
            g["recheck"] = recheck
        same = next((p for p in src if set(p.get("item_ids") or []) == ids), None)
        if same and not g.get("summary"):
            g["summary"] = same.get("summary") or ""
    return groups


def review_payload(run: Run) -> list[dict]:
    """The groups as the user checks them (input request kind "groups")."""
    by_id = {it["id"]: it for it in run.s["items"]}
    return [{"title": g["title"], "summary": g["summary"],
             "items": [{"id": i, "title": by_id[i]["title"], "detail": by_id[i]["detail"]} for i in g["item_ids"]]}
            for g in run.s["groups"]]


def review(run: Run) -> None:
    decision = review_groups(review_payload(run), review_prompt(run), key=run.s["pending"]["key"])
    decision, files = split_files(decision)
    decision = decision if isinstance(decision, dict) else {"action": "change", "feedback": str(decision or "")}
    if decision.get("action") == "start":
        new = inherit_marks(normalise_groups(run, decision["groups"]), run.s.get("groups") or [])
        kept = run.s.pop("kept_groups", None) or []      # planning again: the workflows it didn't touch stay
        taken = {g["title"] for g in kept}
        for g in new:
            while g["title"] in taken:                    # a part's key is its title: keep them apart
                g["title"] += " (new)"
            taken.add(g["title"])
        run.s.pop("scope", None)
        run.s.update(groups=kept + adopt_checked(run, new), phase="checks", pending=None)
        n = len(new)
        stage_end(run, "review", f"{n} workflow{'s' if n != 1 else ''}")
        stage_start(run, "checks")
    else:
        run.s.setdefault("stages", {}).pop("review", None)
        stage_start(run, "clarify")
        run.s["stages"]["clarify"].pop("note", None)
        said = f"{decision.get('feedback', '')}{files_text(files)}"
        run.s.setdefault("clarifications", []).append(f"Changes asked at the groups check: {said}")
        run.s.update(phase="clarify", pending=None,
                     next_message=f"The user wants changes before starting: {said}\n"
                                  "Ask if you need to, then propose the groups again.")
    run.save()


def review_prompt(run: Run) -> str:
    """What the user reads above the groups: how many workflows, against the free slots, and why."""
    n = len(run.s["groups"])
    info = run.s.get("grouping") or {}
    free = info.get("slots_free") or free_workflow_slots()
    text = (f"Grouped into {n} workflow{'s' if n != 1 else ''} ({free} slot{'s' if free != 1 else ''} free on "
            f"{MACHINE}).")
    if info.get("reason"):
        text += f" {info['reason'].rstrip('.')}."
    if n > free:
        text += f" {n - free} will wait for a free slot."
    return f"Claude has no more questions. {text} Check the workflows before they start."


# ---- the question round: the specialists' checks and the build check (Ore's Approved lane) ---------------------
#
# After the user starts the groups, every new group gets the specialists, before anything is built:
#   tests  - the test planner (every group, read-only): how we'll know it works; goes into the build instructions;
#   risk   - the risk reviewer (size M and L, read-only): migrations, security, breaking changes, data loss; risks the
#            user must accept are asked as a review (gate "risk");
#   design - the designer (frontend "significant"): one self-contained HTML prototype per version at
#            .ore/designs/<run id>/<group slug>/v<n>.html, reviewed by the user (gate "design"); "change" continues
#            the designer's session with the feedback and files for the next version.
# The sessions run in parallel (ORE_SPECIALISTS_PARALLEL, default 3), the reviews one at a time. When every group is
# checked, the build check asks once (gate "build"): approve -> issues and workflows, change -> back to the questions
# with the feedback. Each group's part carries the specialists' "notes" and its "gates" (design, risk, tests,
# questions). Everything is in state.json: an interrupted session runs again, an open review is asked again with the
# same id.

CHECK_KINDS = ("tests", "risk", "design")
CHECK_NAMES = {"tests": "The test planner", "risk": "The risk reviewer", "design": "The designer"}
NOTE_AUTHORS = {"tests": "tests", "risk": "risk", "design": "designer"}
GATE_LABELS = {"design": "Design", "risk": "Risks", "tests": "Test plan", "questions": "Questions"}
NOTES_KEPT = 30
ROUND_TIMEOUT = 20 * 60
DESIGN_TIMEOUT = 30 * 60
APPROVE_WORDS = ("approve", "approved", "accept", "accepted", "start", "yes", "ok")
BUILD_PROMPT = "Plan, designs and answers are agreed. Start building?"


def specialists_parallel() -> int:
    try:
        return max(1, int(os.getenv("ORE_SPECIALISTS_PARALLEL", "3") or 3))
    except ValueError:
        return 3


TESTS_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "One line: what the plan checks"},
        "plan": {"type": "string", "description": "Markdown: the automated tests to add or change (with files), the "
                                                  "manual checks, and the data or setup they need"}},
    "required": ["summary", "plan"],
}
RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "One or two plain sentences"},
        "risks": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "detail": {"type": "string", "description": "What could go wrong, and for whom"},
                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                "needs_acceptance": {"type": "boolean",
                                     "description": "True only when the user must accept it before building"},
                "mitigation": {"type": "string", "description": "How the build should handle it"}},
            "required": ["title", "detail", "severity", "needs_acceptance", "mitigation"]}}},
    "required": ["summary", "risks"],
}
DESIGN_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "What the prototype shows and what to click, in two or three "
                                                     "plain sentences"},
        "screens": {"type": "array", "items": {"type": "string"}, "description": "The screens or states it has"}},
    "required": ["summary"],
}
ROUND_SCHEMAS = {"tests": TESTS_SCHEMA, "risk": RISK_SCHEMA, "design": DESIGN_SCHEMA}


def new_groups(run: Run) -> list[dict]:
    """The groups the question round checks: those not started yet (a replan's kept workflows have a status)."""
    return [g for g in run.s.get("groups") or [] if not g.get("status")]


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:40].strip("-")
    return s or "group"


def group_slug(run: Run, g: dict) -> str:
    """The group's slug for its prototypes' folder and specs/designs/<slug>.html: from its title, unique in the run,
    and kept once given."""
    if not g.get("slug"):
        taken = {x.get("slug") for x in all_groups(run) + (run.s.get("checked_groups") or []) if x is not g}
        base = slug = slugify(g["title"])
        n = 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        g["slug"] = slug
    return g["slug"]


def group_size(run: Run, g: dict) -> str:
    """The group's size: the largest of its items' sizes when Ore sent them, else the planner's, else M."""
    sizes = [it["size"] for it in run.s["items"] if it["id"] in g.get("item_ids", []) and it.get("size") in SIZES]
    if sizes:
        return max(sizes, key=SIZES.index)
    return g["size"] if g.get("size") in SIZES else "M"


def needs(run: Run, g: dict, kind: str) -> bool:
    if kind == "risk":
        return group_size(run, g) in ("M", "L")
    if kind == "design":
        return g.get("frontend") == "significant"
    return True


def sync_checks(run: Run, g: dict) -> None:
    """Make the group's checks match what it needs now (its size and frontend may change when it's planned again)."""
    prep = g.setdefault("prep", {})
    for kind in CHECK_KINDS:
        st = prep.get(kind) or {}
        if not needs(run, g, kind):
            prep[kind] = {**{k: v for k, v in st.items() if k in ("round", "version", "session")}, "state": "skipped"}
        elif not st or st.get("state") == "skipped":
            prep[kind] = {**{k: v for k, v in st.items() if k in ("round", "version", "session")}, "state": "pending"}


def add_note(run: Run, g: dict, author: str, text: str, attachments: list | None = None) -> None:
    """A note on the group's part (shown in its conversation in Ore): newest last, the latest NOTES_KEPT."""
    n = int(g.get("note_seq") or 0) + 1
    g["note_seq"] = n
    note = {"id": f"{run.s['run_id']}-{group_slug(run, g)}-{author}-{n}", "author": author, "text": text[:8000],
            "time": now_iso(), "attachments": attachments or []}
    g["notes"] = (g.get("notes") or [])[-(NOTES_KEPT - 1):] + [note]


def start_checks_for(run: Run, g: dict) -> None:
    """A group enters the question round: its slug, its checks, and the planner's note."""
    group_slug(run, g)
    first = "prep" not in g
    sync_checks(run, g)
    if first:
        size, front = group_size(run, g), g.get("frontend") or "none"
        screens = {"none": "no visible changes", "small": "small screen changes",
                   "significant": "significant screen changes, so the designer makes a clickable prototype for you "
                                  "to approve"}[front if front in FRONTEND else "none"]
        text = (f"Planned as one workflow{': ' + g['summary'].rstrip('.') if g.get('summary') else ''}. "
                f"Size {size}, {screens}. "
                + ("The risk reviewer checks it. " if needs(run, g, "risk") else "")
                + "The test planner writes how we'll know it works.")
        add_note(run, g, "planning", text)


def design_rel(run: Run, g: dict, version: int) -> str:
    return f".ore/designs/{run.s['run_id']}/{group_slug(run, g)}/v{version}.html"


def design_attachment(run: Run, g: dict, version: int) -> dict:
    return {"label": f"Prototype v{version}", "path": design_rel(run, g, version), "kind": "design"}


def gates(run: Run, g: dict) -> list[dict]:
    """The group's gates for its part: design, risk, tests and questions, each ok, open or skipped, with a note."""
    prep = g.get("prep") or {}
    out = []
    d = prep.get("design") or {"state": "skipped"}
    if d["state"] == "skipped":
        gate = ("skipped", "No significant screen changes: no prototype")
    elif d["state"] == "ok":
        gate = ("ok", f"Prototype v{d.get('approved') or d.get('version')} approved")
    elif d["state"] == "review":
        gate = ("open", f"Prototype v{d.get('version')} waits for your review")
    elif d["state"] == "failed":
        gate = ("open", d.get("note") or "The designer stopped")
    else:
        gate = ("open", f"The designer is working on prototype v{int(d.get('version') or 0) + 1}")
    out.append({"key": "design", "label": GATE_LABELS["design"], "state": gate[0], "note": gate[1]})
    r = prep.get("risk") or {"state": "skipped"}
    if r["state"] == "skipped":
        gate = ("skipped", "Small change: no risk review")
    elif r["state"] == "ok":
        n = sum(bool(x.get("needs_acceptance")) for x in r.get("risks") or [])
        gate = ("ok", f"You accepted {n} risk{'s' if n != 1 else ''}" if r.get("accepted") and n
                else "No risks that need your OK")
    elif r["state"] == "review":
        n = sum(bool(x.get("needs_acceptance")) for x in r.get("risks") or [])
        gate = ("open", f"{n} risk{'s' if n != 1 else ''} need{'s' if n == 1 else ''} your OK")
    elif r["state"] == "failed":
        gate = ("open", r.get("note") or "The risk reviewer stopped")
    else:
        gate = ("open", "The risk reviewer is looking at it")
    out.append({"key": "risk", "label": GATE_LABELS["risk"], "state": gate[0], "note": gate[1]})
    t = prep.get("tests") or {"state": "pending"}
    if t["state"] == "ok":
        gate = ("ok", t.get("summary") or "Test plan written")
    elif t["state"] == "failed":
        gate = ("open", t.get("note") or "The test planner stopped")
    else:
        gate = ("open", "The test planner is writing the plan")
    out.append({"key": "tests", "label": GATE_LABELS["tests"], "state": gate[0], "note": gate[1][:300]})
    n = run.s.get("question_rounds", 0)
    out.append({"key": "questions", "label": GATE_LABELS["questions"], "state": "ok",
                "note": f"{n} round{'s' if n != 1 else ''} answered" if n else "No questions"})
    return out


def check_part(run: Run, g: dict) -> dict:
    """A group in the question round as a part: queued, running while a specialist works on it, input while its
    review is open; with the specialists' notes and the gates."""
    prep = g.get("prep") or {}
    pending = run.s.get("pending") or {}
    working = [k for k in CHECK_KINDS if (prep.get(k) or {}).get("state") in ("running", "pending")]
    if pending.get("group") == g["title"] and run.s.get("phase") == "checks":
        status_ = "input"
        message = {"design": "Waiting for your review of the prototype",
                   "risk": "Waiting for you to accept the risks"}.get(pending.get("gate"), "Waiting for you")
    elif working and run.s.get("phase") == "checks":
        status_ = "running"
        message = ", ".join({"tests": "writing the test plan", "risk": "reviewing the risks",
                             "design": "designing the prototype"}[k] for k in working)
        message = message[0].upper() + message[1:]
    else:
        status_ = "queued"
        message = ("Checked: waiting for the build check" if run.s.get("phase") == "checks"
                   else "Waiting while the plan is changed")
    part = {"key": g["title"], "label": g["title"], "status": status_, "message": message, "progress": None,
            "links": [], "items": [str(i) for i in g.get("item_ids") or []], "gates": gates(run, g),
            "notes": list(g.get("notes") or []),
            "details": [{"label": "Size", "value": group_size(run, g)},
                        {"label": "Screen changes", "value": g.get("frontend") or "none"}]}
    return part


def group_context(run: Run, g: dict) -> str:
    """What every specialist reads about the group: the plan, its items, the user's answers and notes."""
    by_id = {it["id"]: it for it in run.s["items"]}
    lines = [f"Ore run {run.s['run_id']}. After the user agrees the plan, this group becomes one GitHub issue, one "
             "branch and one pull request, built by an automated workflow (ADW) in its own worktree.",
             f"\n## Group: {g['title']}", g.get("summary") or "",
             f"Size: {group_size(run, g)}. Screen changes: {g.get('frontend') or 'none'}.", "\n## Its items"]
    for i in g.get("item_ids") or []:
        if i in by_id:
            lines.append(f"### Item {i}\n{item_text(by_id[i])}")
    said = run.s.get("clarifications") or []
    if said:
        lines.append("\n## The user's answers while planning\n" + "\n\n".join(said[-10:]))
    notes = (g.get("prep") or {}).get("user_notes") or []
    if notes:
        lines.append("\n## Notes from the user\n" + "\n".join(
            f"- {n.get('text') or '(files only)'}{files_text(n.get('files') or [])}" for n in notes[-10:]))
    return "\n".join(x for x in lines if x is not None)


def feedback_text(fb: dict | None) -> str:
    if not fb:
        return ""
    return (fb.get("text") or "(no text, only files)") + files_text(fb.get("files") or [])


def job_for(run: Run, g: dict, kind: str) -> dict:
    """What one specialist session needs: its message, the session to continue, where it may write."""
    st = g["prep"][kind]
    fb = st.get("feedback")
    session = st.get("session")
    job = {"group": g["title"], "kind": kind, "simulate": bool(run.s.get("simulate")), "session": None,
           "write_dir": None, "path": None, "version": None, "slug": group_slug(run, g)}
    if kind == "design":
        version = int(st.get("version") or 0) + 1
        rel = design_rel(run, g, version)
        job.update(version=version, path=str(REPO_ROOT / rel), write_dir=str((REPO_ROOT / rel).parent),
                   title=g["title"])
        task = (f"Write prototype v{version} to exactly this file: {REPO_ROOT / rel}\n"
                f"You may write only in {REPO_ROOT / rel}'s folder. One self-contained HTML file: inline CSS and "
                "JavaScript, images as data: URIs, nothing loaded from the network.")
        if version > 1 and session:
            prev = REPO_ROOT / design_rel(run, g, version - 1)
            job["session"] = session
            job["message"] = (f"The user looked at prototype v{version - 1} ({prev}) and asks for changes:\n\n"
                              f"{feedback_text(fb) or '(no details)'}\n\n{task}\nMake it a complete new file with "
                              f"the changes; leave v{version - 1} as it is.")
        else:
            job["message"] = (group_context(run, g) + "\n\n## Your task\nDesign a clickable prototype of what this "
                              "group changes on screen.\n" + task
                              + (f"\n\nThe user asked for this:\n{feedback_text(fb)}" if fb else ""))
        return job
    what = {"tests": "Write the test plan for this group.",
            "risk": "Review this group's risks before it is built."}[kind]
    if fb and session:
        job["session"] = session
        job["message"] = (f"The user asks for changes:\n\n{feedback_text(fb)}\n\nLook again and answer in the same "
                          "schema with your updated answer.")
    else:
        job["message"] = (group_context(run, g) + f"\n\n## Your task\n{what}"
                          + (f"\n\nThe user asked for this:\n{feedback_text(fb)}" if fb else ""))
    return job


def round_session(name: str, message: str, schema: dict, session: str | None = None,
                  write_dir: str | None = None, timeout: int = ROUND_TIMEOUT) -> dict:
    """One specialist session in the repository's root: read-only (plan mode; Read, Glob, Grep, read-only git and gh)
    or, for the designer, allowed to write only in write_dir. Continues `session` when given (one that's gone starts
    over). Never raises: {"reply", "session_id", "usage"} or {"error"} or {"auth"}."""
    try:
        prompt = specialist_prompt(name, ROUND_FALLBACKS)
    except QueryError as e:
        return {"error": str(e)}
    claude = os.getenv("CLAUDE_CODE_PATH", "claude")
    model = os.getenv("ORE_DESIGNER_MODEL" if name == "designer" else "ORE_SPECIALIST_MODEL") or MODEL
    cmd = [claude, "-p", "--output-format", "stream-json", "--verbose", "--json-schema", json.dumps(schema),
           "--model", model, "--append-system-prompt", prompt]
    if write_dir is None:
        cmd += ["--permission-mode", "plan", "--allowedTools", "Read", "Glob", "Grep", *ITEMS_HISTORY,
                "--disallowedTools", "Edit", "Write", "NotebookEdit"]
    else:
        rel = Path(os.path.relpath(write_dir, REPO_ROOT)).as_posix()
        cmd += ["--allowedTools", "Read", "Glob", "Grep", f"Write({rel}/**)", f"Edit({rel}/**)",
                "--disallowedTools", "Bash", "NotebookEdit"]
    mcp = REPO_ROOT / ".mcp.json"
    if mcp.exists():
        cmd += ["--mcp-config", str(mcp)]
    last = "no reply"
    for attempt in (1, 2):
        try:
            # The message goes in on stdin: a group with long items doesn't fit a command line.
            proc = subprocess.run(cmd + (["--resume", session] if session else []), input=message, cwd=REPO_ROOT,
                                  env=get_safe_subprocess_env(), capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            return {"auth": f"Claude Code (`claude`) isn't installed on {socket.gethostname()}, or isn't on PATH. "
                            "Install it, sign in, then press Resume."}
        except subprocess.TimeoutExpired:
            last = f"no answer within {timeout // 60} minutes"
            continue
        out = turn_result(proc.stdout)
        res = {"session_id": out.get("session_id") or session}
        if out.get("total_cost_usd") is not None:
            res["usage"] = messages.result_usage(out)
        reply = out.get("structured_output")
        if proc.returncode == 0 and not out.get("is_error") and isinstance(reply, dict):
            res["reply"] = reply
            return res
        problem = auth_problem(out, proc.stderr)
        if problem:
            res["auth"] = problem
            return res
        if session and "no conversation found" in f"{proc.stderr}{proc.stdout}".lower():
            session = None                       # the session is gone: start over (the message may be short)
        last = (proc.stderr.strip()[-300:] or str(out.get("result") or "no reply")[-300:])
        log(f"{name} session failed (attempt {attempt}): {last}")
    return {"error": last}


SIM_DESIGN = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - prototype v{version}</title>
<style>
body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0; color: #1d1d1f; background: #f6f6f8; }}
header {{ background: #24292f; color: #fff; padding: 12px 20px; }}
main {{ max-width: 860px; margin: 24px auto; padding: 0 16px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; }}
th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #ddd; }}
button {{ font: inherit; padding: 6px 14px; border-radius: 6px; border: 1px solid #888; background: #fff; cursor: pointer; }}
button:focus-visible {{ outline: 3px solid #0969da; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; background: #ddf4ff; }}
</style></head>
<body><header>Orders (simulated prototype v{version})</header>
<main><h1>{title}</h1>
<p>Click an order to see its status history.</p>
<table><thead><tr><th>Order</th><th>Status</th><th>Last update</th></tr></thead>
<tbody><tr><td><button aria-expanded="false" onclick="toggle(this)">#1042</button></td>
<td><span class="badge">Shipped</span></td><td>Today 09:12</td></tr>
<tr hidden><td colspan="3">Paid on Monday, shipped today.</td></tr></tbody></table></main>
<script>function toggle(b) {{ const row = b.closest('tr').nextElementSibling; row.hidden = !row.hidden;
b.setAttribute('aria-expanded', String(!row.hidden)); }}</script>
</body></html>
"""


def simulated_specialist(job: dict) -> dict:
    """--simulate: what the specialists would answer, canned (the designer writes a small prototype)."""
    time.sleep(min(2.0, 2.0 / sim_speed()))
    kind = job["kind"]
    res = {"session_id": f"sim-{kind}-{job['slug']}"}
    if kind == "tests":
        res["reply"] = {"summary": "Unit tests for the changed code and one end-to-end check of the page",
                        "plan": "- Unit tests for the new code paths, next to the existing ones\n"
                                "- One end-to-end check: open the page, use the change, see the result\n"
                                "- Manual check on a phone-sized window"}
    elif kind == "risk":
        res["reply"] = {"summary": "(Simulated) One change needs your OK before building.",
                        "risks": [{"title": "Existing records get a default value",
                                   "detail": "Records created before this change have no value yet; they would show "
                                             "as empty.", "severity": "medium", "needs_acceptance": True,
                                   "mitigation": "A migration fills them with a sensible default."}]}
    else:
        path = Path(job["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SIM_DESIGN.format(title=job.get("title") or "Prototype", version=job["version"]),
                        encoding="utf-8")
        res["reply"] = {"summary": f"(Simulated) Prototype v{job['version']}: the orders table with a status column; "
                                   "click an order to see its history."}
    return res


def run_job(job: dict) -> dict:
    """One specialist session (in a worker thread: touches no run state)."""
    try:
        if job["simulate"]:
            res = simulated_specialist(job)
        else:
            name = {"tests": "tests", "risk": "risk", "design": "designer"}[job["kind"]]
            res = round_session(name, job["message"], ROUND_SCHEMAS[job["kind"]], job["session"], job["write_dir"],
                                DESIGN_TIMEOUT if job["kind"] == "design" else ROUND_TIMEOUT)
        if job["kind"] == "design" and res.get("reply") and not Path(job["path"]).is_file():
            res = {**res, "reply": None,
                   "error": f"it didn't write the prototype to {Path(job['path']).relative_to(REPO_ROOT).as_posix()}"}
        return res
    except Exception as e:  # noqa: BLE001 - reported as the check's problem
        return {"error": f"{type(e).__name__}: {e}"}


def clean_risks(risks) -> list[dict]:
    out = []
    for r in risks if isinstance(risks, list) else []:
        if isinstance(r, dict) and str(r.get("title") or "").strip():
            out.append({"title": str(r["title"]).strip(), "detail": str(r.get("detail") or "").strip(),
                        "severity": r.get("severity") if r.get("severity") in ("low", "medium", "high") else "medium",
                        "needs_acceptance": bool(r.get("needs_acceptance")),
                        "mitigation": str(r.get("mitigation") or "").strip()})
    return out


def risks_markdown(risks: list[dict]) -> str:
    return "\n".join(f"- **{r['title']}** ({r['severity']}{', needs your OK' if r['needs_acceptance'] else ''}): "
                     f"{r['detail']}" + (f" Plan: {r['mitigation']}" if r["mitigation"] else "") for r in risks)


def apply_job(run: Run, job: dict, res: dict, problems: list) -> None:
    """A finished session's answer into the group's checks and notes (main thread)."""
    g = next((x for x in new_groups(run) if x["title"] == job["group"]), None)
    if res.get("usage"):
        run.s["usage"] = messages.add_usage(run.s.get("usage") or {}, res["usage"])
    if g is None:                                   # the group left the plan meanwhile (items taken out)
        return
    kind = job["kind"]
    st = g["prep"][kind]
    if res.get("session_id"):
        st["session"] = res["session_id"]
    if res.get("auth"):
        st["state"] = "pending"
        problems.append(("auth", res["auth"]))
        return
    reply = res.get("reply")
    if not isinstance(reply, dict):
        why = res.get("error") or "no usable answer"
        st.update(state="failed", note=f"{CHECK_NAMES[kind]} stopped: {why}"[:300])
        problems.append(("error", f"{CHECK_NAMES[kind]} couldn't finish {g['title']}: {why}"))
        return
    st.pop("feedback", None)
    st.pop("note", None)
    summary = str(reply.get("summary") or "").strip()
    if kind == "tests":
        plan = str(reply.get("plan") or "").strip()
        st.update(state="ok", summary=summary, plan=plan)
        add_note(run, g, "tests", f"Test plan: {summary}\n\n{plan}".strip())
    elif kind == "risk":
        risks = clean_risks(reply.get("risks"))
        st.update(summary=summary, risks=risks, round=int(st.get("round") or 0) + 1, accepted=False,
                  state="review" if any(r["needs_acceptance"] for r in risks) else "ok")
        add_note(run, g, "risk", (summary + ("\n\n" + risks_markdown(risks) if risks else "")).strip()
                 or "No risks found.")
    else:
        st.update(state="review", version=job["version"], summary=summary)
        add_note(run, g, "designer", f"Prototype v{job['version']}: {summary}".strip(),
                 [design_attachment(run, g, job["version"])])


def git_changes() -> dict | None:
    """The repository's changes outside .ore/ (git status), each with its size and time, or None when git can't
    tell (not a repository)."""
    try:
        proc = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=REPO_ROOT,
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode:
        return None
    out = {}
    for line in proc.stdout.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip('"')
        if path == ".ore" or path.startswith(".ore/"):
            continue
        try:
            st = (REPO_ROOT / path).stat()
            out[path] = (line[:2], st.st_mtime_ns, st.st_size)
        except OSError:
            out[path] = (line[:2], None, None)
    return out


def checks_message(run: Run) -> str:
    pending = run.s.get("pending") or {}
    if pending.get("gate") == "build":
        return BUILD_PROMPT
    if pending.get("gate") == "design":
        return f"Review the design: {pending.get('group')}"
    if pending.get("gate") == "risk":
        return f"Accept the risks: {pending.get('group')}"
    working = [f"{CHECK_NAMES[k].split(' ', 1)[1]} for {g['title']}" for g in new_groups(run) for k in CHECK_KINDS
               if (g.get("prep") or {}).get(k, {}).get("state") == "running"]
    if working:
        return f"The specialists are checking the plan: {', '.join(working)}"[:300]
    return "The specialists are checking the plan"


def design_request(run: Run, g: dict) -> dict:
    d = g["prep"]["design"]
    n = d["version"]
    return {"type": "input_request", "id": f"design-{group_slug(run, g)}-v{n}", "kind": "review", "gate": "design",
            "part": g["title"], "title": f"Review the design: {g['title']}",
            "prompt": f"The designer made prototype v{n} for {g['title']}. Open it and click through it, then "
                      "approve it or ask for changes.",
            "attachments": [design_attachment(run, g, n)], "summary": d.get("summary") or ""}


def risk_request(run: Run, g: dict) -> dict:
    r = g["prep"]["risk"]
    need = [x for x in r.get("risks") or [] if x["needs_acceptance"]]
    others = [x for x in r.get("risks") or [] if not x["needs_acceptance"]]
    summary = (r.get("summary") or "") + "\n\n**Needs your OK**\n" + risks_markdown(need)
    if others:
        summary += "\n\n**Also noted** (handled in the build)\n" + risks_markdown(others)
    return {"type": "input_request", "id": f"risk-{group_slug(run, g)}-{r.get('round') or 1}", "kind": "review",
            "gate": "risk", "part": g["title"], "title": f"Accept the risks: {g['title']}",
            "prompt": f"The risk reviewer found {len(need)} risk{'s' if len(need) != 1 else ''} in {g['title']} that "
                      "need your OK before building. Accept them, or ask for changes.",
            "attachments": [], "summary": summary.strip()}


def build_request(run: Run) -> dict:
    """The build check: everything the specialists agreed, once, before anything is built."""
    n = int(run.s.get("build_rounds") or 0) + 1
    run.s["build_rounds"] = n
    lines, attachments = [], []
    for g in new_groups(run):
        prep = g.get("prep") or {}
        lines.append(f"### {g['title']}\nSize {group_size(run, g)}; items {', '.join(g['item_ids'])}."
                     + (f" {g['summary']}" if g.get("summary") else ""))
        d, r, t = prep.get("design") or {}, prep.get("risk") or {}, prep.get("tests") or {}
        if d.get("state") == "ok":
            v = d.get("approved") or d.get("version")
            lines.append(f"- **Design:** prototype v{v} approved.")
            attachments.append({**design_attachment(run, g, v), "label": f"{g['title']}: prototype v{v}"})
        elif d.get("state") == "skipped":
            lines.append("- **Design:** no prototype (no significant screen changes).")
        else:
            lines.append("- **Design:** not approved yet.")
        risks = r.get("risks") or []
        if r.get("state") == "skipped":
            lines.append("- **Risks:** not reviewed (small change).")
        elif r.get("state") == "ok":
            accepted = [x["title"] for x in risks if x["needs_acceptance"]]
            lines.append(f"- **Risks:** you accepted {', '.join(accepted)}." if accepted else
                         f"- **Risks:** none that need your OK ({len(risks)} noted for the build).")
        else:
            lines.append("- **Risks:** not accepted yet.")
        lines.append(f"- **Test plan:** {t.get('summary') or 'written'}." if t.get("state") == "ok"
                     else "- **Test plan:** missing.")
    return {"type": "input_request", "id": f"build-{n}", "kind": "review", "gate": "build", "part": None,
            "title": "Start building?", "prompt": BUILD_PROMPT, "attachments": attachments,
            "summary": "\n".join(lines)}


def next_review(run: Run) -> dict | None:
    """The next review to ask, one group at a time: its risks first, then its prototype."""
    for g in new_groups(run):
        prep = g.get("prep") or {}
        if (prep.get("risk") or {}).get("state") == "review":
            return risk_request(run, g)
        if (prep.get("design") or {}).get("state") == "review":
            return design_request(run, g)
    return None


def review_value(value) -> tuple[str, str, list[str]]:
    """(approve|change, feedback, attached files) from a review answer: {"action": "approve"} or {"action": "change",
    "feedback", "files"}; a plain text answer is feedback unless it says yes."""
    value, files = split_files(value)
    if isinstance(value, dict):
        action = str(value.get("action") or "").strip().lower()
        feedback = str(value.get("feedback") or value.get("text") or "").strip()
        return ("approve" if action in APPROVE_WORDS else "change"), feedback, files
    text = str(value or "").strip()
    if text.lower().rstrip(".!") in APPROVE_WORDS and not files:
        return "approve", "", []
    return "change", text, files


def apply_review(run: Run, pending: dict, value) -> None:
    action, feedback, files = review_value(value)
    fb = {"text": feedback, "files": files}
    run.s["pending"] = None
    if pending["gate"] == "build":
        if action == "approve":
            finish_checks(run)
        else:
            back_to_planning(run, fb)
        return
    g = next((x for x in new_groups(run) if x["title"] == pending.get("group")), None)
    if g is None:
        return
    st = g["prep"]["design" if pending["gate"] == "design" else "risk"]
    if action == "approve":
        if pending["gate"] == "design":
            st.update(state="ok", approved=st.get("version"))
        else:
            st.update(state="ok", accepted=True)
    else:
        st.update(state="pending", feedback=fb)
        if pending["gate"] == "risk":
            st["accepted"] = False


def ask_review(request: dict):
    """Outside Ore: the review in the terminal (blocking)."""
    print(f"\n{request['title']}\n{request['prompt']}\n{request.get('summary') or ''}")
    for a in request.get("attachments") or []:
        print(f"  {a['label']}: {REPO_ROOT / a['path']}")
    fb = input("Press Enter to approve, or type what should change: ").strip()
    return {"action": "change", "feedback": fb} if fb else {"action": "approve"}


def checks(run: Run) -> None:
    """The question round: the specialists' sessions in parallel, the reviews one at a time, then the build check."""
    stage_start(run, "checks")
    for g in new_groups(run):
        start_checks_for(run, g)
        for kind in CHECK_KINDS:
            if g["prep"][kind].get("state") in ("running", "failed"):      # interrupted, or failed before Resume
                g["prep"][kind]["state"] = "pending"
    run.save()
    _while_waiting[:] = []
    pool = ThreadPoolExecutor(max_workers=specialists_parallel(), thread_name_prefix="specialist")
    running: dict = {}                 # future -> job
    problems: list = []
    baseline = [None]                  # the repository's changes outside .ore/ before the designers started
    asked = None                       # the review this process has sent
    last = None
    try:
        while run.s["phase"] == "checks":
            handle_messages(run)
            if not problems:
                busy = {(j["group"], j["kind"]) for j in running.values()}
                for g in new_groups(run):
                    for kind in CHECK_KINDS:
                        if g["prep"][kind]["state"] != "pending" or (g["title"], kind) in busy:
                            continue
                        if kind == "design" and not run.s.get("simulate") and \
                                not any(j["kind"] == "design" for j in running.values()):
                            baseline[0] = git_changes()
                        job = job_for(run, g, kind)
                        g["prep"][kind]["state"] = "running"
                        running[pool.submit(run_job, job)] = job
                        run.save()
            for f in [f for f in running if f.done()]:
                job = running.pop(f)
                apply_job(run, job, f.result(), problems)
                if job["kind"] == "design" and baseline[0] is not None and \
                        not any(j["kind"] == "design" for j in running.values()):
                    after = git_changes()
                    changed = sorted(p for p in set(baseline[0]) | set(after or {})
                                     if baseline[0].get(p) != (after or {}).get(p)) if after is not None else []
                    baseline[0] = None
                    if changed:
                        for g in new_groups(run):
                            d = g["prep"]["design"]
                            if d.get("state") == "review":
                                d.update(state="failed", note="The designer changed files outside .ore/")
                        problems.append(("error", "The designer changed files outside .ore/ ("
                                         + ", ".join(changed[:5]) + (", ..." if len(changed) > 5 else "")
                                         + "). It may only write its prototypes there. Undo those changes in the "
                                           "repository, then press Resume."))
                run.save()
            if problems and not running:
                auth = next((p for kind, p in problems if kind == "auth"), None)
                if auth:
                    raise ClaudeAuthError(auth)
                raise RuntimeError("; ".join(p for _, p in problems))
            pending = run.s.get("pending")
            if not pending and not problems:
                nxt = next_review(run)
                if nxt is None and not running and not any(
                        g["prep"][k]["state"] == "pending" for g in new_groups(run) for k in CHECK_KINDS):
                    nxt = build_request(run)
                if nxt:
                    pending = {"key": nxt["id"], "gate": nxt["gate"], "group": nxt["part"], "request": nxt}
                    run.s["pending"] = pending
                    run.save()
            if pending and pending.get("request"):
                if not IO.enabled:
                    apply_review(run, pending, ask_review(pending["request"]))
                    run.save()
                    continue
                if asked != pending["key"]:
                    emit(pending["request"])             # again after a restart: the same id reopens it in Ore
                    asked = pending["key"]
                    report(run, checks_message(run))     # the part waits for the user now
                    last = json.dumps([[check_part(run, g) for g in new_groups(run)], stages(run)])
                value = IO.answer(pending["key"])
                if value is not _MISSING:
                    apply_review(run, pending, value)
                    asked = None
                    run.save()
                    continue
                if IO.closed:
                    raise EOFError("Ore closed the input stream before answering")
            if run.s["phase"] != "checks":
                break
            snapshot = json.dumps([[check_part(run, g) for g in new_groups(run)], stages(run)])
            if snapshot != last:
                report(run, checks_message(run))
                last = snapshot
            time.sleep(0.25 if IO.enabled or running else 0)
    finally:
        pool.shutdown(wait=True)
        for f, job in running.items():           # stopped meanwhile: keep what the sessions finished
            apply_job(run, job, f.result(), [])
        _while_waiting[:] = [lambda: handle_messages(run)]
        run.save()


def finish_checks(run: Run) -> None:
    """The build check approved: keep each approved prototype with the run (agents/ore/<run id>/designs/<slug>.html;
    the workflow's worktree gets it as specs/designs/<slug>.html), then the issues and workflows."""
    for g in new_groups(run):
        d = (g.get("prep") or {}).get("design") or {}
        v = d.get("approved") or (d.get("version") if d.get("state") in ("review", "ok") else None)
        if not v:
            continue
        src = REPO_ROOT / design_rel(run, g, v)
        if not src.is_file():
            raise RuntimeError(f"The prototype for {g['title']} is gone ({design_rel(run, g, v)}). Ask for changes "
                               "at the build check so the designer makes it again.")
        dst = run.dir / "designs" / f"{group_slug(run, g)}.html"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        g.update(design_file=str(dst), design_version=v, design_approved=bool(d.get("approved")))
    n = len(new_groups(run))
    run.s.update(phase="issues", pending=None)
    run.s.pop("checked_groups", None)
    stage_end(run, "checks", f"{n} group{'s' if n != 1 else ''} checked")
    stage_start(run, "issues")
    run.save()


def back_to_planning(run: Run, fb: dict) -> None:
    """The build check asked for changes: back to the questions with the feedback. The checked groups wait in
    checked_groups; a group that comes back with the same items keeps its checks, and the planner says which of them
    the change affects (recheck)."""
    groups = run.s.get("groups") or []
    kept = [g for g in groups if g.get("status")]
    new = [g for g in groups if not g.get("status")]
    if kept:
        run.s["kept_groups"] = kept
        run.s["scope"] = [i for g in new for i in g["item_ids"]]
    run.s["checked_groups"] = new
    run.s["build_feedback"] = fb
    said = feedback_text(fb)
    run.s.setdefault("clarifications", []).append(f"Changes asked at the build check: {said}")
    lines = ["The user looked at the plan, the prototypes, the risks and the test plans at the build check and "
             f"wants changes before anything is built:\n\n{said}\n", "What the specialists agreed so far:"]
    for g in new:
        gs = {x["key"]: x for x in gates(run, g)}
        lines.append(f"- {g['title']} (items {', '.join(g['item_ids'])}; size {group_size(run, g)}, screen changes "
                     f"{g.get('frontend') or 'none'}): design: {gs['design']['note']}; risks: {gs['risk']['note']}; "
                     f"test plan: {gs['tests']['note']}")
    lines.append("Ask if you need to, then propose the groups again with status ready. Keep the same groups (the same "
                 "items) unless the change needs other ones, and give each group recheck: the checks the change "
                 "affects (design, risk, tests), empty when none.")
    stages_ = run.s.setdefault("stages", {})
    for key in ("review", "checks"):
        stages_.pop(key, None)
    stage_start(run, "clarify")
    stages_["clarify"].pop("note", None)
    run.s.update(groups=[], phase="clarify", pending=None, next_message="\n".join(lines))
    run.save()


def recheck(run: Run, g: dict, kinds: list[str], fb: dict | None) -> None:
    for kind in kinds:
        st = g["prep"].get(kind) or {}
        if st.get("state") in (None, "skipped"):
            continue
        st.update(state="pending", feedback=fb)
        if kind == "risk":
            st["accepted"] = False
    sync_checks(run, g)


def adopt_checked(run: Run, groups: list[dict], keep_titles: bool = False) -> list[dict]:
    """Groups planned again after the build check take over the checks of the checked group with the same items (its
    slug, notes and checks), and the planner's recheck runs those specialists again with the user's feedback; the
    feedback also becomes a note from the user on every group."""
    checked = run.s.get("checked_groups") or []
    fb = run.s.get("build_feedback")
    for g in groups:
        old = next((c for c in checked if sorted(c["item_ids"]) == sorted(g["item_ids"])), None)
        kinds = g.pop("recheck", None) or []
        if old:
            for k in ("slug", "prep", "notes", "note_seq"):
                if k in old:
                    g[k] = old[k]
            if keep_titles:
                g["title"] = old["title"]
            if not g.get("summary"):
                g["summary"] = old.get("summary") or ""
            recheck(run, g, kinds, fb)
        if fb and (fb.get("text") or fb.get("files")):
            g.setdefault("prep", {}).setdefault("user_notes", []).append(
                {"text": f"At the build check: {fb.get('text') or ''}".strip(), "files": fb.get("files") or [],
                 "time": now_iso()})
    run.s.pop("checked_groups", None)
    run.s.pop("build_feedback", None)
    return groups


def same_groups_again(run: Run, proposed: list[dict]) -> bool:
    """After the build check: when Claude proposes the same groups (the same items), they skip the groups check and go
    straight back to the specialists (with recheck). Returns whether it did that."""
    checked = run.s.get("checked_groups")
    if not checked:
        return False
    groups = normalise_groups(run, proposed)
    if sorted(sorted(g["item_ids"]) for g in groups) != sorted(sorted(g["item_ids"]) for g in checked):
        return False
    kept = run.s.pop("kept_groups", None) or []
    run.s.pop("scope", None)
    run.s.update(groups=kept + adopt_checked(run, groups, keep_titles=True), phase="checks", pending=None,
                 next_message=None)
    stage_start(run, "checks")
    return True


def build_sections(run: Run, g: dict) -> str:
    """What the question round adds to a group's issue: the approved prototype, the test plan, the accepted risks and
    the user's notes."""
    out = ""
    prep = g.get("prep") or {}
    if g.get("design_file"):
        rel = f"specs/designs/{group_slug(run, g)}.html"
        approved = "approved" if g.get("design_approved", True) else "made (the user started the build without approving it)"
        out += (f"\n\n## Approved design\nThe user {approved} a clickable prototype for this work (v"
                f"{g.get('design_version')}): `{rel}` in your worktree (Ore's trigger puts it there when the worktree "
                f"is created; if it is missing, copy it from `{g['design_file']}`). Open it (Read) before planning and "
                "build the screens to match it: layout, wording, states and flows, following this repository's own "
                "components. Commit it with the work.")
    t = prep.get("tests") or {}
    if t.get("state") == "ok" and t.get("plan"):
        out += f"\n\n## Test plan\nAgreed before building; the work is done when these pass.\n\n{t['plan']}"
    r = prep.get("risk") or {}
    risks = r.get("risks") or []
    if risks:
        accepted = [x for x in risks if x["needs_acceptance"]]
        others = [x for x in risks if not x["needs_acceptance"]]
        if accepted:
            out += ("\n\n## Accepted risks\nThe user accepted these before building" if r.get("accepted") else
                    "\n\n## Risks the user hasn't accepted\nThe user started the build without accepting these")
            out += "; handle each as planned.\n" + risks_markdown(accepted)
        if others:
            out += "\n\n## Other risks\nThe risk reviewer noted these; handle each as planned.\n" + risks_markdown(others)
    notes = prep.get("user_notes") or []
    if notes:
        out += "\n\n## Notes from the user while planning\n" + "\n".join(
            f"- {n.get('text') or '(files only)'}{files_text(n.get('files') or [])}" for n in notes)
    return out


def place_design(run: Run, g: dict) -> None:
    """The approved prototype into the group's worktree (specs/designs/<slug>.html) once the workflow created it."""
    if not g.get("design_file") or g.get("design_placed") or not g.get("adw_id") or fake(run):
        return
    worktree = adw_state(g["adw_id"]).get("worktree_path")
    if not worktree or not Path(worktree).is_dir():
        return
    dst = Path(worktree) / "specs" / "designs" / f"{group_slug(run, g)}.html"
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copyfile(g["design_file"], dst)
        g["design_placed"] = True
    except OSError as e:
        log(f"Couldn't put the prototype into {worktree}: {e}")


def write_issues(run: Run) -> None:
    new = [g for g in run.s["groups"] if not g.get("status")]     # planning again: the kept workflows have theirs
    groups = [{"title": g["title"], "item_ids": g["item_ids"]} for g in new]
    stage_start(run, "issues")
    report(run, "Claude is writing the issues")
    reply = claude_turn(run, ISSUES_PROMPT.format(groups=json.dumps(groups, ensure_ascii=False, indent=1)))
    def ids(g):
        return tuple(sorted((re.search(r"\d+", str(i)) or re.search(r".+", str(i))).group(0)
                            for i in g.get("item_ids") or []))
    written = {ids(g): g for g in reply.get("groups") or []}
    for g in new:
        w = written.get(tuple(sorted(g["item_ids"]))) or {}
        g["issue_title"] = w.get("issue_title") or g["title"]
        g["issue_body"] = w.get("issue_body") or "\n\n".join(
            next(it["text"] for it in run.s["items"] if it["id"] == i) for i in g["item_ids"])
        images = list(dict.fromkeys(p for it in run.s["items"] if it["id"] in g["item_ids"] for p in it.get("images") or []))
        g["issue_body"] += images_section(images)
        criteria = list(dict.fromkeys(c for it in run.s["items"] if it["id"] in g["item_ids"]
                                      for c in it.get("criteria") or []))
        g["issue_body"] += criteria_section(criteria)
        g["issue_body"] += build_sections(run, g)
        g["issue_body"] += f"\n\n---\nCreated from Ore (run {run.s['run_id']})."
        g.update(status="queued", message="Waiting to start", progress=0.0)
        carry_on(run, g)
    run.s["phase"] = "workflows"
    stage_start(run, "workflows")
    run.save()


def fake(run: Run) -> bool:
    """A --dry-run or a --simulate run: no GitHub issues, no real workflows."""
    return bool(run.s.get("dry_run") or run.s.get("simulate"))


def create_issue(run: Run, g: dict) -> None:
    if fake(run):
        kind = "sim" if run.s.get("simulate") else "dry"
        g.update(issue_number=f"{kind}-{run.s['run_id']}-{run.s['groups'].index(g) + 1}", issue_url=None)
        return
    repo = extract_repo_path(get_repo_url(str(REPO_ROOT)))
    proc = subprocess.run(["gh", "issue", "create", "-R", repo, "--title", g["issue_title"], "--body", g["issue_body"]],
                          cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"gh issue create failed: {proc.stderr.strip()}")
    url = proc.stdout.strip().splitlines()[-1]
    g.update(issue_url=url, issue_number=url.rstrip("/").rsplit("/", 1)[-1])


def start_adw(run: Run, g: dict, adw_id: str | None = None) -> None:
    adw_id = adw_id or make_adw_id()
    progress = progress_file(g)
    progress.parent.mkdir(parents=True, exist_ok=True)
    # Only this ADW's comments: an issue that had an earlier workflow already has lines in the file.
    offset = progress.stat().st_size if progress.exists() else 0
    g.update(adw_id=adw_id, status="running", message="Continuing" if g.get("continue_adw") == adw_id else "Starting",
             started_at=time.time(), offset=offset,
             workflow="orchestrated" if run.s.get("simulate") else workflow_mode())
    g.pop("not_before", None)
    flush_pending(g)
    if fake(run):
        g["pid"] = None
        if run.s.get("simulate"):
            sim_lease(run, g)
        return
    follow = g.pop("follow_up", None)
    # Continuing (same adw_id): keep its state (worktree, ports, orchestrator session); the ADW resumes from it.
    state = (ADWState.load(adw_id) if g.get("continue_adw") == adw_id else None) or ADWState(adw_id)
    state.update(adw_id=adw_id, issue_number=str(g["issue_number"]), model_set=MODEL_SET, ore_run_dir=str(run.dir))
    state.save("ore_trigger")
    launch_log = REPO_ROOT / "agents" / adw_id / "ore_launch.log"
    launch_log.parent.mkdir(parents=True, exist_ok=True)
    with open(launch_log, "a") as fh:
        script = WORKFLOW_SCRIPTS[g["workflow"]]
        cmd = ["uv", "run", str(ADWS_DIR / script), str(g["issue_number"]), adw_id]
        if follow:                                   # the request, for the orchestrator's resumed session
            adw_file(adw_id, messages.FOLLOW_UP).write_text(json.dumps(follow, ensure_ascii=False), encoding="utf-8")
            cmd.append("--follow-up")
            g["round"] = follow["n"]                 # its pull request predates it: only a clean finish counts
            g["message"] = f"Follow-up {follow['n']}: {follow['text']}"[:300]
        proc = subprocess.Popen(cmd, cwd=REPO_ROOT, env=get_safe_subprocess_env(), stdout=fh, stderr=subprocess.STDOUT,
                                start_new_session=True)
    _children[adw_id] = proc
    g["pid"] = proc.pid
    if resources.enabled():
        resources.set_slot_pid(resources.WORKFLOW, adw_id, proc.pid)     # the slot lives while the ADW runs
    state.update(workflow_pid=proc.pid, workflow_pgid=os.getpgid(proc.pid))
    state.save("ore_trigger")


_children: dict[str, subprocess.Popen] = {}
_auth_checked = [0.0]                    # when check_claude_auth last passed


def progress_file(g: dict) -> Path:
    return REPO_ROOT / "agents" / "progress" / f"issue-{g['issue_number']}.jsonl"


def alive(g: dict) -> tuple[bool, int | None]:
    """Is the group's ADW still running? Exit code when this process started it, else None."""
    proc = _children.get(g.get("adw_id"))
    if proc is not None:
        code = proc.poll()
        return code is None, code
    pid = g.get("pid")
    if not pid:
        return False, None
    try:
        os.kill(pid, 0)
    except OSError:
        return False, None
    try:                                  # a zombie (exited, not yet reaped) counts as finished
        return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z", None
    except OSError:
        return True, None


def read_progress(g: dict) -> None:
    path = progress_file(g)
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        f.seek(g.get("offset", 0))
        lines = f.readlines()
        g["offset"] = f.tell()
    for line in lines:
        try:
            entry = json.loads(line)
            text = entry["comment"]
        except (ValueError, KeyError, TypeError):
            continue
        body = COMMENT_PREFIX.sub("", text).strip()
        first = next((ln.strip(" #*") for ln in body.splitlines() if ln.strip()), "")
        if first:
            g["message"] = first[:160]
            g["log"] = (g.get("log") or [])[-(LOG_LINES - 1):] + [{"time": entry.get("ts"), "text": first[:300]}]
        low = body.lower()
        for word, prog, phase in PHASES:
            if word in low and prog >= g.get("progress", 0):
                g.update(progress=prog, phase=phase)
        m = PR_URL.search(body)
        if m:
            g["pr_url"] = m.group(0)
        if "sdlc workflow completed" in low or "multi-phase sdlc completed" in low:
            g["completed"] = True


# Each workflow's steps in order, so the steps still to come show as pending: (key, label, children)
SDLC_STEPS = [("route", "Route", None), ("plan", "Plan", None), ("build", "Build", None), ("test", "Test", None),
              ("smoke", "Smoke test", None), ("review", "Review", None), ("docs", "Docs", None),
              ("domain_docs", "Domain docs", None), ("pr", "Pull request", None)]
PHASE_STEPS = [("build", "Build", None), ("test", "Test", None), ("review", "Review", None), ("commit", "Commit", None)]
MULTI_PHASE_STEPS = [("route", "Route", None), ("setup", "Setup", None), ("plan", "Plan", None), ("phases", "Phases", []),
                     ("integration", "Integration", [("build", "Build", None), ("tests", "Tests", None),
                                                     ("smoke", "Smoke test", None), ("review", "Review", None),
                                                     ("docs", "Docs", None)]),
                     ("pr", "Pull request", None)]
ORCHESTRATED_STEPS = [("route", "Route", None), ("setup", "Setup", None), ("plan", "Plan", None), ("work", "Work", []),
                      ("integrate", "Checks", None), ("screens", "Screens", None), ("review", "Review", None),
                      ("docs", "Docs", None), ("check", "Full check", None),
                      ("pr", "Pull request", None)]
SKELETONS = {"SDLC": SDLC_STEPS, "Multi-phase SDLC": MULTI_PHASE_STEPS, "Orchestrated SDLC": ORCHESTRATED_STEPS}
FINISHED = ("done", "failed", "skipped")


def steps_file(adw_id: str) -> Path:
    return REPO_ROOT / "agents" / adw_id / "steps.jsonl"


def read_steps(adw_id: str | None) -> list[dict] | None:
    """The ADW's step events, or None when it records none (an older ADW)."""
    path = steps_file(adw_id) if adw_id else None
    if not path or not path.exists():
        return None
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict) and e.get("key") and e.get("status"):
            events.append(e)
    return events


def _node(key: str, label: str | None, children=None) -> dict:
    node = {"key": key, "label": label or key.replace("_", " ").capitalize(), "status": "pending", "started": None,
            "ended": None, "note": "", "attempts": [], "steps": []}
    for ck, cl, cc in children or []:
        node["steps"].append(_node(ck, cl, cc))
    return node


def build_steps(events: list[dict]) -> tuple[list[dict], dict]:
    """(steps, route) for a part, from its step events: a skeleton per workflow type, then each event in order."""
    events = steps.current(events)                  # a follow-up round starts the steps again
    route_ev = next((e for e in reversed(events) if e["key"] == "route" and e.get("workflow")), None)
    workflow = (route_ev or {}).get("workflow")
    if not workflow:
        if any(e["key"] in ("work", "integrate") or e.get("parent") == "work" for e in events):
            workflow = "Orchestrated SDLC"
        elif any(e["key"] in ("setup", "phases") or e.get("parent") == "phases" for e in events):
            workflow = "Multi-phase SDLC"
        elif any(e["key"] != "route" for e in events):
            workflow = "SDLC"
    skeleton = SKELETONS.get(workflow, [("route", "Route", None)])
    top = [_node(k, lbl, c) for k, lbl, c in skeleton]
    containers: dict = {None: top}                   # parent key -> its list of steps
    nodes: dict = {}                                 # (parent key, key) -> step

    def index(siblings, parent):
        for n in siblings:
            nodes[(parent, n["key"])] = n
            containers[n["key"]] = n["steps"]
            index(n["steps"], n["key"])

    index(top, None)

    def find(parent, key, label=None):
        if (parent, key) in nodes:
            n = nodes[(parent, key)]
            if label:
                n["label"] = label
            return n
        if parent is not None and parent not in containers:     # e.g. a phase before the plan said so
            find("phases" if workflow == "Multi-phase SDLC" and parent not in ("integration", "phases") else None,
                 parent)
        n = _node(key, label, PHASE_STEPS if parent == "phases" else None)
        containers[parent].append(n)
        index([n], parent)
        return n

    for e in events:
        ts, st, note = e.get("ts"), e["status"], e.get("note") or ""
        if st == "planned":                              # the steps still to come under e["key"] (phases, work)
            for ph in e.get("phases") or []:
                find(e["key"], str(ph.get("id")), ph.get("name"))
            continue
        n = find(e.get("parent"), e["key"], e.get("label"))
        if st == "running":
            if n["status"] == "failed":                  # a rerun after failing: a new attempt
                n["attempts"].append({k: n[k] for k in ("status", "started", "ended", "note")})
                n.update(started=ts, ended=None, note=note)
            elif n["status"] in FINISHED:                # run again after finishing (e.g. a resumed workflow)
                n.update(started=ts, ended=None, note=note)
            else:
                n["started"] = n["started"] or ts
                n["note"] = note or n["note"]
            n["status"] = "running"
        elif st in FINISHED:
            n.update(status=st, started=n["started"] or ts, ended=ts, note=note or n["note"])
    route = {}
    if route_ev:
        route = {k: str(route_ev[k]) for k in ("type", "complexity", "workflow") if route_ev.get(k)}
    for n in nodes.values():
        if n["attempts"]:
            n["attempts"] = n["attempts"] + [{k: n[k] for k in ("status", "started", "ended", "note")}]
    _derive(top)
    return top, route


def _derive(steps: list[dict]) -> None:
    """A parent with no events of its own takes its status and times from its sub-steps."""
    for n in steps:
        if not n["steps"]:
            continue
        _derive(n["steps"])
        if n["started"] or n["status"] != "pending":
            continue
        kids = [c["status"] for c in n["steps"]]
        if "failed" in kids and "running" not in kids:
            n["status"] = "failed"
        elif all(k in ("done", "skipped") for k in kids):
            n["status"] = "done"
        elif any(k != "pending" for k in kids):
            n["status"] = "running"
        starts = [c["started"] for c in n["steps"] if c["started"]]
        ends = [c["ended"] for c in n["steps"] if c["ended"]]
        n["started"] = min(starts) if starts else None
        n["ended"] = max(ends) if ends and n["status"] in ("done", "failed") else None


def _leaves(steps: list[dict]):
    for n in steps:
        if n["steps"]:
            yield from _leaves(n["steps"])
        else:
            yield n


def _current(steps: list[dict], parent: str = "") -> str | None:
    """The label of the step running now, deepest first, e.g. "Phase 2 · Review"."""
    for n in steps:
        if n["status"] == "running":
            name = f"{parent} \u00b7 {n['label']}" if parent else n["label"]
            return _current(n["steps"], n["label"] if n["key"] != "phases" else "") or name
    return None


def _stopped(steps: list[dict]) -> None:
    """The workflow is gone: whatever it left running didn't finish."""
    for n in steps:
        _stopped(n["steps"])
        if n["status"] == "running":
            n["status"] = "failed"
            n["note"] = n["note"] or "Stopped"


def adw_state(adw_id: str | None) -> dict:
    path = REPO_ROOT / "agents" / adw_id / "adw_state.json" if adw_id else None
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path and path.exists() else {}
    except (OSError, ValueError):
        return {}


def flow(g: dict) -> dict:
    """A part's flow fields (docs/script-protocol.md §3): started, ended, route, steps, details, log. Also keeps
    g's progress and phase in line with its steps when it has some."""
    out: dict = {}
    if iso(g.get("started_at")):
        out["started"] = iso(g["started_at"])
    if g.get("ended_at") and g.get("status") in ("done", "failed"):
        out["ended"] = iso(g["ended_at"])
    adw_id = g.get("adw_id")
    events = read_steps(adw_id)
    state = adw_state(adw_id)
    if events is not None:
        steps, route = build_steps(events)
        if g.get("status") == "failed":
            _stopped(steps)
        out["steps"] = steps
        leaves = list(_leaves(steps))
        if g.get("status") == "running" and leaves:
            g["progress"] = round(sum(n["status"] in FINISHED for n in leaves) / len(leaves), 3)
            g["phase"] = _current(steps) or g.get("phase")
    else:
        route = {}
    if not route.get("type") and state.get("issue_class"):
        route["type"] = str(state["issue_class"]).lstrip("/")
    if route:
        out["route"] = route
    details = [("Branch", state.get("branch_name")), ("ADW id", adw_id), ("Worktree", state.get("worktree_path"))]
    if any(v for _, v in details):
        out["details"] = [{"label": k, "value": str(v)} for k, v in details if v]
    if g.get("log"):
        out["log"] = g["log"][-LOG_LINES:]
    return out


# What --dry-run pretends an ADW does, one line every 2 seconds: (step event or None, progress comment or None)
SIM_SDLC = [
    ({"key": "route", "status": "running", "label": "Route"}, None),
    ({"key": "route", "status": "done", "label": "Route", "note": "feature, single-phase", "type": "feature",
      "complexity": "single-phase", "workflow": "SDLC"}, "Routing decision: /feature, single-phase"),
    ({"key": "plan", "status": "running"}, "Planning phase started"),
    ({"key": "plan", "status": "done"}, "Implementation plan created"),
    ({"key": "build", "status": "running"}, None),
    ({"key": "build", "status": "done"}, "Build phase completed"),
    ({"key": "test", "status": "running"}, None),
    ({"key": "test", "status": "failed", "note": "1 test failed: test_footer_version"}, "Found 1 failed tests"),
    ({"key": "test", "status": "running", "note": "Attempt 2"}, "Re-running tests (attempt 2/4)"),
    ({"key": "test", "status": "done"}, "Test phase completed"),
    ({"key": "smoke", "status": "running"}, None),
    ({"key": "smoke", "status": "done"}, None),
    ({"key": "review", "status": "running"}, None),
    ({"key": "review", "status": "done"}, "Review phase completed"),
    ({"key": "docs", "status": "running"}, None),
    ({"key": "docs", "status": "done"}, None),
    ({"key": "domain_docs", "status": "running"}, None),
    ({"key": "domain_docs", "status": "done"}, None),
    ({"key": "pr", "status": "done", "note": "PR #1: https://github.com/example/repo/pull/1"},
     "Pull request created: https://github.com/example/repo/pull/1"),
    (None, "SDLC workflow completed"),
]
SIM_MULTI = [
    ({"key": "route", "status": "running", "label": "Route"}, None),
    ({"key": "route", "status": "done", "label": "Route", "note": "feature, multi-phase", "type": "feature",
      "complexity": "multi-phase", "workflow": "Multi-phase SDLC"}, "Routing decision: /feature, multi-phase"),
    ({"key": "setup", "status": "running", "label": "Setup"}, "Starting Multi-Phase SDLC workflow"),
    ({"key": "setup", "status": "done", "label": "Setup"}, None),
    ({"key": "plan", "status": "running", "label": "Plan"}, "Creating multi-phase implementation plan with Opus..."),
    ({"key": "phases", "status": "planned", "phases": [{"id": "phase-1", "name": "Data model"},
                                                        {"id": "phase-2", "name": "API and UI"}]}, None),
    ({"key": "plan", "status": "done", "label": "Plan", "note": "2 phases"}, "Multi-phase plan created"),
]
for _pid, _name in (("phase-1", "Data model"), ("phase-2", "API and UI")):
    SIM_MULTI += [({"key": _pid, "parent": "phases", "label": _name, "status": "running"}, f"Starting phase: {_pid}")]
    for _k in ("build", "test", "review", "commit"):
        SIM_MULTI.append(({"key": _k, "parent": _pid, "status": "running"}, None))
        if _k == "review" and _pid == "phase-2":
            SIM_MULTI += [({"key": _k, "parent": _pid, "status": "failed", "note": "1 blocker(s): missing validation"},
                           None),
                          ({"key": _k, "parent": _pid, "status": "running", "note": "Attempt 2"},
                           f"Retrying review for phase {_pid} after resolution...")]
        SIM_MULTI.append(({"key": _k, "parent": _pid, "status": "done"}, None))
    SIM_MULTI.append(({"key": _pid, "parent": "phases", "label": _name, "status": "done"}, f"Phase {_pid} completed"))
SIM_MULTI += [({"key": "integration", "status": "running", "label": "Integration"}, "Starting integration validation...")]
for _k in ("build", "tests", "smoke", "review", "docs"):
    SIM_MULTI += [({"key": _k, "parent": "integration", "status": "running"}, None),
                  ({"key": _k, "parent": "integration", "status": "done"}, None)]
SIM_MULTI += [({"key": "integration", "status": "done", "label": "Integration"}, None),
              ({"key": "pr", "status": "done", "label": "Pull request",
                "note": "PR #2: https://github.com/example/repo/pull/2"},
               "Pull request created: https://github.com/example/repo/pull/2"),
              (None, "Multi-Phase SDLC completed!")]


def simulate(run: Run, g: dict) -> None:
    """--dry-run: pretend to be an ADW (progress comments and step events) so Ore's display, flow included, can
    be tried without GitHub. Every second workflow pretends to be a multi-phase one; with ORE_WORKFLOW=orchestrated
    every workflow is an orchestrated one (parallel packages, a failed review round).
    --simulate: an orchestrated workflow on a clock that stops while it is paused or waits for an answer; it
    answers messages, asks one question after the plan, reports screenshots and usage (sim_orchestrator)."""
    extra = None
    if run.s.get("simulate"):
        from adw_modules import orchestrated_sim
        idx = run.s["groups"].index(g)
        sim_orchestrator(run, g)
        now = time.time()
        if not g.get("paused") and not g.get("sim_waiting_ask"):
            g["sim_elapsed"] = g.get("sim_elapsed", 0.0) + (now - g.get("sim_tick", now))
        g["sim_tick"] = now
        script = orchestrated_sim.events_for(idx + 1, g.get("ports"))
        n = orchestrated_sim.due(g.get("sim_elapsed", 0.0), idx, sim_speed())
        if n >= orchestrated_sim.ASK_AT and not g.get("sim_asked") and IO.enabled:
            n = orchestrated_sim.ASK_AT                  # the orchestrator asks after the plan, and waits
            g.update(sim_asked=True, sim_waiting_ask=True)
            messages.append(str(adw_file(g["adw_id"], messages.OUTBOX)),
                            {"type": "ask", "n": 1, **orchestrated_sim.ASK})
        extra = orchestrated_sim
    elif g.get("workflow") == "orchestrated":
        from adw_modules.orchestrated_sim import EVENTS as script
        n = int((time.time() - g["started_at"]) // 2)
    else:
        script = SIM_MULTI if run.s["groups"].index(g) % 2 else SIM_SDLC
        n = int((time.time() - g["started_at"]) // 2)
    done = g.get("simulated", 0)
    steps_path = steps_file(g["adw_id"])
    steps_path.parent.mkdir(parents=True, exist_ok=True)
    with open(progress_file(g), "a", encoding="utf-8") as f, open(steps_path, "a", encoding="utf-8") as sf:
        for i, (event, text) in enumerate(script[done:min(n, len(script))], start=done):
            if event:
                sf.write(json.dumps({"ts": now_iso(), "parent": None, "label": None, "note": "", **event}) + "\n")
            if text:
                f.write(json.dumps({"ts": now_iso(), "comment": f"[ADW-AGENTS] {g['adw_id']}_ops: {text}"}) + "\n")
            if extra and i == extra.SCREENS_DONE:
                for img in extra.IMAGES:
                    messages.append(str(adw_file(g["adw_id"], messages.IMAGES)), img)
    g["simulated"] = min(n, len(script))
    if extra and g["simulated"] > done:
        path = adw_file(g["adw_id"], messages.USAGE)
        path.write_text(json.dumps(extra.usage_at(g["simulated"], run.s["groups"].index(g)), indent=1),
                        encoding="utf-8")


def sim_orchestrator(run: Run, g: dict) -> None:
    """--simulate: what the orchestrator does with its inbox (canned replies through its outbox, as
    adw_report.py reply writes them), so messages, pause/resume and the question round trip like a real run."""
    inbox = str(adw_file(g["adw_id"], messages.INBOX))
    outbox = str(adw_file(g["adw_id"], messages.OUTBOX))
    entries, g["sim_inbox"] = messages.read_new(inbox, g.get("sim_inbox", 0))
    at = g.get("phase") or "Setup"
    for e in entries:
        if e.get("type") == "answer" and e.get("ask") == 1:
            g["sim_waiting_ask"] = False
            with open(progress_file(g), "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": now_iso(), "comment": f"[ADW-AGENTS] {g['adw_id']}_orchestrator: Answer "
                                    f"received: {e.get('text', '')}; continuing"}) + "\n")
            continue
        if e.get("type") != "message":
            continue
        mode = e.get("mode")
        text = {"ask": f"(Simulated orchestrator) I'm at {at}; all packages are on track. You asked: "
                       f"{e.get('text', '')}",
                "amend": "(Simulated) Noted: I'll take this into account from the next step and re-brief the "
                         "packages it affects.",
                "pause": "(Simulated) Paused at a safe point: work in progress committed. Send resume to continue.",
                "resume": "(Simulated) Resumed where I stopped."}.get(mode, "(Simulated) Noted.")
        messages.append(outbox, {"type": "reply", "to": e.get("id"), "text": text})


# ---- messages from Ore, the orchestrator's questions, usage and screenshots ---------------------------
# The files are described in adw_modules/messages.py: the trigger writes a workflow's inbox.jsonl and reads its
# outbox.jsonl, usage.json and images.jsonl.

def adw_file(adw_id: str, name: str) -> Path:
    return REPO_ROOT / "agents" / adw_id / name


def find_groups(run: Run, part) -> list[dict]:
    """The groups a message is for: the part's (by key, i.e. title, or label), or every group for part null."""
    groups = run.s.get("groups") or []
    if part in (None, ""):
        return list(groups)
    return [g for g in groups if part in (g["title"], g.get("label"))]


def handle_messages(run: Run) -> None:
    for msg in IO.take_messages():
        try:
            if msg.get("type") == "withdraw":
                withdraw(run, msg)
                continue
            deliver(run, msg)
        except Exception as e:  # noqa: BLE001 - a message must never stop the run
            log(f"Couldn't deliver message {msg.get('id')}: {type(e).__name__}: {e}")
            reply(msg.get("id") or "?", f"Couldn't deliver this message: {e}", msg.get("part"))


def deliver(run: Run, msg: dict) -> None:
    """A message from the user (protocol §4) to the workflows it is for: into their inbox (the orchestrator gets it
    at its next step and answers with a reply); queued workflows get it when they start."""
    mid = str(msg.get("id") or f"m{int(time.time())}")
    part, text = msg.get("part"), str(msg.get("text") or "").strip()
    mode = msg.get("mode") if msg.get("mode") in messages.MODES else "ask"
    if run.s.get("phase") in PLANNING:
        planning_message(run, msg)
        return
    if run.s.get("phase") == "issues":
        reply(mid, "No workflow has started yet. Answer the questions or change the groups instead; messages go to "
                   "the workflows once they run.", part)
        return
    if mode == "follow_up":
        follow_up(run, msg)
        return
    targets = find_groups(run, part)
    if not targets:
        reply(mid, f"There is no workflow called {part!r} in this run.", part)
        return
    files = repo_files(msg.get("files"))
    entry = {"type": "message", "id": mid, "mode": mode, "text": text + files_text(files),
             "from": msg.get("from") or msg.get("user") or os.getenv("ORE_USER_NAME") or "the user"}
    if files:
        entry["files"] = files
    reached = []
    for g in targets:
        if g["status"] in ("running", "queued") and g.get("workflow", "orchestrated") != "orchestrated":
            if part is not None:
                reply(mid, "This workflow runs the classic SDLC pipeline (ORE_WORKFLOW=router), which can't take "
                           "messages.", g["title"])
            continue
        if g["status"] == "running" and g.get("adw_id"):
            messages.append(str(adw_file(g["adw_id"], messages.INBOX)), entry)
            reached.append(g)
        elif g["status"] == "queued":
            g.setdefault("pending_messages", []).append(entry)
            if part is not None:
                reply(mid, "This workflow hasn't started yet; it gets your message when it starts.", g["title"])
            reached.append(g)
        elif part is not None:
            reply(mid, f"This workflow has {'finished' if g['status'] == 'done' else 'stopped'}"
                       + (f" ({g['pr_url']})" if g.get("pr_url") else "") + "; nothing is listening any more."
                       + (" Send a follow-up to have it do more." if g["status"] == "done" else ""),
                  g["title"])
        if g in reached and mode == "pause":
            g["paused"] = True
        elif g in reached and mode in ("resume", "amend"):
            g["paused"] = False
    if part is None and not reached:
        reply(mid, "No workflow of this run is running any more.")
    run.save()


def planning_message(run: Run, msg: dict) -> None:
    """A message while the run plans: for the planning Claude's next turn (questions, groups check), or, in the
    question round, a note from the user on the group (or every group) that the specialists read from their next
    session on and that goes into the build instructions."""
    mid = str(msg.get("id") or f"m{int(time.time())}")
    part, text = msg.get("part"), str(msg.get("text") or "").strip()
    files = repo_files(msg.get("files"))
    who = msg.get("from") or msg.get("user") or "the user"
    if run.s.get("phase") == "checks":
        targets = [g for g in new_groups(run) if part in (None, "", g["title"])]
        if not targets:
            reply(mid, f"There is no group called {part!r} in this plan.", part)
            return
        for g in targets:
            g.setdefault("prep", {}).setdefault("user_notes", []).append(
                {"text": text, "files": files, "from": who, "time": now_iso()})
        run.save()
        reply(mid, "Noted. The specialists read it the next time they work on "
                   + ("this group" if part else "the plan") + ", and it goes into the build instructions. To change "
                   "a prototype or the risks, answer that review with Ask for changes.", part)
        return
    run.s.setdefault("planning_notes", []).append(f"{who} wrote while you plan: {text or '(files only)'}"
                                                  + files_text(files))
    run.save()
    reply(mid, "Noted. Claude reads it before its next step in planning.", part)


FOLLOW_UP_RESET = ("pid", "progress", "phase", "completed", "offset", "started_at", "ended_at", "cleaned", "closed",
                   "not_before", "paused", "check", "next_adw_id")


def follow_up(run: Run, msg: dict) -> bool:
    """Ore's Follow up on a finished orchestrated workflow: the same ADW continues (same worktree, branch, pull
    request and orchestrator session) with the request as its next instruction. A workflow still running gets it as
    a change (amend). Returns whether the request was taken."""
    mid = str(msg.get("id") or f"m{int(time.time())}")
    part, text = msg.get("part"), str(msg.get("text") or "").strip()
    targets = find_groups(run, part) if part not in (None, "") else []
    if len(targets) != 1:
        reply(mid, "Say which workflow to follow up on." if part in (None, "") else
              f"There is no workflow called {part!r} in this run.", part)
        return False
    g = targets[0]
    if not text:
        reply(mid, "Write what the follow-up should do.", g["title"])
        return False
    if g["status"] in ("running", "queued"):
        deliver(run, {**msg, "mode": "amend"})
        return True
    if g["status"] != "done":
        reply(mid, "This workflow didn't finish: Resume continues it; send the request once it runs.", g["title"])
        return False
    if not can_continue(run, g):
        reply(mid, "This workflow can't be followed up: its worktree or orchestrator session is gone, or it isn't an "
                   "orchestrated workflow. Start a new workflow for this instead.", g["title"])
        return False
    n = int(g.get("follow_ups") or 0) + 1
    give_back(run, g)
    for key in FOLLOW_UP_RESET:
        g.pop(key, None)
    who = msg.get("from") or msg.get("user") or os.getenv("ORE_USER_NAME") or "the user"
    g.update(status="queued", follow_ups=n, continue_adw=g["adw_id"], next_adw_id=g["adw_id"],
             follow_up={"n": n, "id": mid, "text": text, "from": who}, message=f"Follow-up {n}: waiting to start")
    run.s["phase"] = "workflows"
    stage_start(run, "workflows")
    run.save()
    reply(mid, f"Follow-up {n} queued: the orchestrator continues this workflow on its branch, and the pull request "
               "updates when it's done.", g["title"])
    return True


def follow_up_arg(args: list[str], flag: str = "--follow-up") -> tuple[list[str], dict | None]:
    """(the other arguments, the request) for `--follow-up <base64url JSON>` (or another such flag: --ore-replan);
    the request is None without it, {} when it can't be read."""
    if flag not in args:
        return args, None
    i = args.index(flag)
    raw = args[i + 1] if i + 1 < len(args) else ""
    rest = args[:i] + args[i + 2:]
    try:
        import base64
        msg = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        msg = None
    return rest, (msg if isinstance(msg, dict) else {})


def flush_pending(g: dict) -> None:
    """Messages that arrived while the group was queued, into its new ADW's inbox."""
    for entry in g.pop("pending_messages", None) or []:
        messages.append(str(adw_file(g["adw_id"], messages.INBOX)), entry)


def poll_outbox(run: Run, g: dict) -> None:
    """Replies and questions from the group's orchestrator (adw_report.py reply|ask)."""
    adw_id = g.get("adw_id")
    if not adw_id:
        return
    offsets = g.setdefault("outbox_offsets", {})
    entries, offsets[adw_id] = messages.read_new(str(adw_file(adw_id, messages.OUTBOX)), offsets.get(adw_id, 0))
    asks = run.s.setdefault("asks", [])
    for e in entries:
        kind = e.get("type")
        if kind == "reply" and e.get("to") and e.get("text"):
            reply(e["to"], e["text"], g["title"])
        elif kind == "ask" and e.get("question"):
            g["ask_count"] = g.get("ask_count", 0) + 1
            asks.append({"id": f"ask-{g.get('issue_number')}-{g['ask_count']}", "group": g["title"], "adw_id": adw_id,
                         "n": e.get("n"), "question": str(e["question"]),
                         "options": [str(o) for o in e.get("options") or [] if str(o).strip()], "state": "queued"})
        elif kind == "check" and e.get("sha"):
            prev = g.get("check") or {}
            g["check"] = {"n": e.get("n"), "sha": e["sha"], "branch": e.get("branch"), "since": time.time(),
                          "state": "waiting", "solo": prev.get("result") == "conflict",
                          "note": "Waiting for the batch's full check"}
        elif kind == "ask_cancel":
            for a in asks:
                if a["adw_id"] == adw_id and a["n"] == e.get("n"):
                    if a["state"] == "queued":
                        a["state"] = "dropped"
                    a["timed_out"] = True


def ask_request(a: dict) -> dict:
    msg = {"type": "input_request", "id": a["id"], "prompt": f"{a['group']}: {a['question']}"}
    if a.get("options"):
        msg.update(kind="choice", options=a["options"])
    else:
        msg.update(kind="text", placeholder="Your answer (the workflow continues meanwhile only if it can)")
    return msg


def poll_asks(run: Run) -> None:
    """One orchestrator question open in Ore at a time (protocol: one input_request at a time); the answer goes to
    that workflow's inbox. Questions of workflows that ended are dropped."""
    asks = run.s.get("asks") or []
    by_title = {g["title"]: g for g in run.s.get("groups") or []}
    for a in asks:
        if a["state"] == "open" and IO.enabled:
            value = IO.answer(a["id"])
            if value is not _MISSING:
                value, files = split_files(value)
                text = (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)) + files_text(files)
                entry = {"type": "answer", "ask": a["n"], "text": text}
                if files:
                    entry["files"] = files
                messages.append(str(adw_file(a["adw_id"], messages.INBOX)), entry)
                a["state"] = "answered"
                run.save()
        if a["state"] == "queued" and (by_title.get(a["group"]) or {}).get("status") in ("done", "failed"):
            a["state"] = "dropped"
    if not IO.enabled or any(a["state"] == "open" for a in asks):
        return
    nxt = next((a for a in asks if a["state"] == "queued"), None)
    if nxt:
        nxt["state"] = "open"
        emit(ask_request(nxt))
        run.save()


def group_usage(g: dict) -> dict:
    """The group's usage in the protocol's shape: its ADW's usage.json, plus earlier ADWs' (a fresh rerun)."""
    total = dict(g.get("usage_before") or {})
    if g.get("adw_id"):
        try:
            data = json.loads(adw_file(g["adw_id"], messages.USAGE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if data:
            total = messages.add_usage(total, data) if total else data
    return messages.protocol_usage(total) if total else {}


def usage_waiting(g: dict) -> str | None:
    """"Claude usage limit reached until HH:MM" while the group's workflow waits for a usage limit to reset."""
    if not g.get("adw_id") or g.get("status") != "running":
        return None
    try:
        until = json.loads(adw_file(g["adw_id"], messages.USAGE).read_text(encoding="utf-8")).get("waiting_until")
        at = datetime.fromisoformat(until) if until else None
    except (OSError, ValueError, TypeError):
        return None
    if at and at > datetime.now():
        return f"Claude usage limit reached until {at.strftime('%H:%M')}"
    return None


def group_images(g: dict) -> list[dict]:
    out, seen = [], set()
    for adw_id in [*(g.get("earlier_adw_ids") or []), g.get("adw_id")]:
        if not adw_id:
            continue
        for e in messages.read_all(str(adw_file(adw_id, messages.IMAGES))):
            url = str(e.get("url") or "")
            if url.startswith(("http://", "https://")) and url not in seen:
                seen.add(url)
                out.append({"label": str(e.get("label") or "Screenshot"), "url": url})
    return out


def run_usage(run: Run, parts_: list[dict]) -> dict:
    total = dict(run.s.get("usage") or {})
    for p in parts_:
        if p.get("usage"):
            total = messages.add_usage(total, p["usage"]) if total else dict(p["usage"])
    return messages.protocol_usage(total) if total else {}


def parts(run: Run) -> list[dict]:
    return parts_of(run, run.s["groups"])


def parts_of(run: Run, groups: list[dict]) -> list[dict]:
    out = []
    open_asks = {a["group"] for a in run.s.get("asks") or [] if a["state"] == "open"}
    for g in groups:
        links = [[f"Issue #{g['issue_number']}", g["issue_url"]]] if g.get("issue_url") else []
        if g.get("pr_url"):
            links.append([f"Pull request #{g['pr_url'].rsplit('/', 1)[-1]}", g["pr_url"]])
        label = g["title"] + (f" · #{g['issue_number']}" if g.get("issue_url") else "")
        part = {"key": g["title"], "label": label, "status": g["status"], "message": "", "progress": None,
                "links": links, "items": [str(i) for i in g.get("item_ids") or []]}
        part.update(flow(g))                 # first: it brings progress and phase up to date from the steps
        msg = g.get("message", "")
        if g.get("phase") and g["status"] == "running" and not msg.lower().startswith(g["phase"].lower()):
            msg = f"{g['phase']}: {msg}"
        waiting = usage_waiting(g)
        if waiting:
            msg = waiting
        elif g["status"] == "running" and g.get("paused"):
            msg = f"Paused (send resume to continue): {msg}".rstrip(": ")
        elif g["status"] == "running" and (g.get("check") or {}).get("state") in ("waiting", "running"):
            msg = f"Full check: {g['check'].get('note') or 'waiting'}"

        if g["status"] == "running" and g["title"] in open_asks:
            part["status"] = "input"
            msg = "Waiting for your answer: " + next(a["question"] for a in run.s["asks"]
                                                     if a["group"] == g["title"] and a["state"] == "open")
        part.update(message=msg[:300], progress=1.0 if g["status"] == "done" else g.get("progress"))
        usage = group_usage(g)
        if usage:
            part["usage"] = usage
        images = group_images(g)
        if images:
            part["images"] = images
        text = workflow_report(g)
        if text:
            part["report"] = text
        if g.get("prep"):
            part["gates"] = gates(run, g)
        if g.get("notes"):
            part["notes"] = list(g["notes"])
        out.append(part)
    return out


def workflow_report(g: dict) -> str | None:
    """The orchestrator's report of a finished workflow (adw_report.py result --report-file)."""
    if not g.get("adw_id") or g.get("status") not in ("done", "failed"):
        return None
    try:
        return adw_file(g["adw_id"], messages.REPORT).read_text(encoding="utf-8")[:messages.REPORT_LIMIT].strip() or None
    except OSError:
        return None


def uses_registry(run: Run) -> bool:
    """Real and simulated workflows take slots and leases from the machine-wide registry; dry runs don't."""
    return resources.enabled() and not run.s.get("dry_run")


def give_back(run: Run, g: dict) -> None:
    """The workflow is over: free its slot and lease (the ADW frees them itself too; this covers a crash)."""
    if uses_registry(run) and g.get("adw_id"):
        try:
            resources.release(g["adw_id"])
        except Exception as e:  # noqa: BLE001
            log(f"Couldn't release the resources of {g['adw_id']}: {e}")


def requeue(run: Run, g: dict, why: str) -> None:
    """Back to the queue (same issue, a fresh ADW next time), after a short delay: resources ran out."""
    give_back(run, g)
    keep = g.get("continue_adw")                 # a workflow that continues keeps its ADW (and worktree)
    for key in RETRY_RESET:
        g.pop(key, None)
    if keep:
        g["next_adw_id"] = keep
    g.update(status="queued", message=f"Waiting for free resources: {why}"[:300],
             not_before=time.time() + REQUEUE_DELAY)


def workflow_label(g: dict) -> tuple[str, int | None]:
    """How the machine view names the group's workflow: ("#26 Get tickets", 26), or (title, None) before its issue."""
    issue = int(g["issue_number"]) if str(g.get("issue_number") or "").isdigit() else None
    title = g.get("issue_title") or g["title"]
    return (f"#{issue} {title}" if issue else title), issue


def claim_slot(run: Run, g: dict) -> str | None:
    """A machine-wide workflow slot for the group's next ADW: its adw_id, or None (the group's message says why)."""
    adw_id = g.get("next_adw_id") or make_adw_id()
    g["next_adw_id"] = adw_id
    if not uses_registry(run):
        return adw_id
    try:
        room = resources.capacity()
        if not room["ports"] or not room["redis"]:
            what = "ports" if not room["ports"] else "Redis databases"
            g["message"] = f"Waiting for free {what}: all leased by workflows on {MACHINE}"
            return None
        label, issue = workflow_label(g)
        if resources.try_acquire_slot(resources.WORKFLOW, adw_id, adw_id=adw_id, label=label, issue=issue):
            return adw_id
        resources.note_waiting(adw_id, label=label, issue=issue)          # Ore's machine view lists the queue
        used, _cap = resources.slot_usage(resources.WORKFLOW)
    except Exception as e:  # noqa: BLE001 - the registry unreadable: say so, try again next round
        g["message"] = f"Waiting: the resource registry can't be read ({e})"[:300]
        return None
    g["message"] = f"Waiting for a free slot: {used} workflow{'s' if used != 1 else ''} running on {MACHINE}"
    return None


def workflows(run: Run) -> None:
    last = None
    for a in run.s.get("asks") or []:
        if a["state"] == "open":             # resumed: ask it again (the same id reopens it in Ore)
            a["state"] = "queued"
    _while_waiting[:] = []
    while True:
        handle_messages(run)
        groups = run.s["groups"]
        for g in groups:
            if g["status"] == "running":
                if fake(run):
                    simulate(run, g)
                place_design(run, g)
                read_progress(g)
                poll_outbox(run, g)
                running, code = alive(g) if not fake(run) else (not g.get("completed"), 0)
                if not running:
                    read_progress(g)
                    if code == EXIT_NO_RESOURCES and not g.get("pr_url"):
                        requeue(run, g, "no free ports or Redis database when it started")
                        continue
                    ok = g.get("completed") or code == 0 or (g.get("pr_url") and not g.get("round"))
                    poll_outbox(run, g)
                    g.update(status="done" if ok else "failed", progress=1.0 if ok else g.get("progress"),
                             ended_at=time.time(), paused=False,
                             message=g.get("message") if ok else
                             f"Stopped{f' with exit code {code}' if code else ''}: {g.get('message', '')}".strip(": "))
                    give_back(run, g)
                    if ok:
                        ready_again(run, g)
        active = sum(g["status"] == "running" for g in groups)
        if active < MAX_PARALLEL and any(g["status"] == "queued" for g in groups) and not fake(run) \
                and time.time() - _auth_checked[0] > 600:
            check_claude_auth()          # a queued ADW would fail on every Claude call if the login has lapsed
            _auth_checked[0] = time.time()
        for g in groups:
            if g["status"] == "queued" and active < MAX_PARALLEL and time.time() >= g.get("not_before", 0):
                adw_id = None
                try:
                    if not g.get("issue_number"):
                        g["message"] = "Creating the issue"
                        create_issue(run, g)
                        run.save()
                    adw_id = claim_slot(run, g)
                    if not adw_id:
                        continue
                    start_adw(run, g, g.pop("next_adw_id"))
                    active += 1
                except resources.ResourcesExhausted as e:
                    requeue(run, g, str(e))
                except Exception as e:
                    if adw_id and uses_registry(run):
                        resources.release(adw_id)
                    g.update(status="failed", message=str(e)[:300], ended_at=time.time())
                run.save()
        full_checks(run)
        if not run.s.get("stages", {}).get("issues", {}).get("ended") and \
                all(g.get("issue_number") or g["status"] == "failed" for g in groups):
            stage_end(run, "issues")
        poll_asks(run)
        current = parts(run)
        snapshot = json.dumps([current, stages(run)])
        counts = {k: sum(g["status"] == k for g in groups) for k in ("running", "queued", "done", "failed")}
        if snapshot != last:
            run.save()
            summary = ", ".join(f"{n} {k}" for k, n in counts.items() if n)
            overall = sum((g.get("progress") or 0) for g in groups) / max(1, len(groups))
            report(run, f"{len(groups)} workflow{'s' if len(groups) != 1 else ''}: {summary}", progress=overall,
                   parts=current)
            last = snapshot
        if not counts["running"] and not counts["queued"]:
            break
        pause = 1 if run.s.get("simulate") else 2 if run.s["dry_run"] else 5
        end = time.time() + pause
        while time.time() < end:             # react to messages and answers within a moment
            time.sleep(0.25 if IO.enabled else pause)
            if IO.messages or any(a["state"] == "open" and a["id"] in IO.answers for a in run.s.get("asks") or []):
                break
    if run.s.get("check"):                   # every workflow stopped while their check ran: nobody waits for it
        _stop(run.s["check"].get("pid"), group=True)
        run.s["check"] = None
    run.s["phase"] = "done"
    stage_end(run, "workflows")
    run.save()
    handle_messages(run)
    report(run, f"{len(run.s['groups'])} workflow{'s' if len(run.s['groups']) != 1 else ''} finished",
           progress=1.0, parts=parts(run))
    links = []
    for g in run.s["groups"]:
        if g.get("pr_url"):
            links.append((f"{g['title']}: PR #{g['pr_url'].rsplit('/', 1)[-1]}", g["pr_url"]))
        elif g.get("issue_url"):
            links.append((f"{g['title']}: issue #{g['issue_number']}", g["issue_url"]))
    failed = [g for g in run.s["groups"] if g["status"] == "failed"]
    if failed:
        # Failing the run (rather than a result) is what makes Ore offer Resume, which reruns these.
        names = "; ".join(f"{g['title']}" + (f" (#{g['issue_number']})" if g.get("issue_url") else "") for g in failed)
        error(f"{len(failed)} of {len(run.s['groups'])} workflow{'s' if len(run.s['groups']) != 1 else ''} failed: "
              f"{names}. Resume runs {'it' if len(failed) == 1 else 'them'} again on the same "
              f"issue{'s' if len(failed) != 1 else ''}; the finished ones are left alone.")
    n = len(run.s["groups"])
    result(f"{n} workflow{'s' if n != 1 else ''} finished", links=links)


# ---- the batch's full check (8.) ------------------------------------------------------------

CHECK_MAX_WAIT = int(os.getenv("ORE_CHECK_MAX_WAIT_MIN", "30") or 30) * 60
CHECK_TRIES = 2                          # a check process that dies without a result is started once more


def group_name(g: dict) -> str:
    return f"#{g['issue_number']}" if g.get("issue_url") or str(g.get("issue_number") or "").isdigit() else g["title"]


def check_note(g: dict, note: str, status: str = "running") -> None:
    """The group's step "check" (and part message), recorded when it changes."""
    chk = g.setdefault("check", {})
    if chk.get("note") == note and chk.get("note_status") == status:
        return
    chk.update(note=note, note_status=status)
    if g.get("adw_id"):
        steps.record(g["adw_id"], "check", status, label="Full check", note=note)


def _check_alive(cur: dict) -> bool:
    proc = _children.get(f"check-{cur['n']}")
    if proc is not None:
        return proc.poll() is None
    try:
        os.kill(int(cur.get("pid") or 0), 0)
        return bool(cur.get("pid"))
    except (OSError, ValueError):
        return False


def _launch_check(run: Run, cur: dict) -> None:
    d = Path(cur["dir"])
    with open(d / "check.log", "a") as fh:
        proc = subprocess.Popen(["uv", "run", str(ADWS_DIR / "adw_batch_check.py"), str(d)], cwd=REPO_ROOT,
                                env=get_safe_subprocess_env(), stdout=fh, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
    _children[f"check-{cur['n']}"] = proc
    cur["pid"] = proc.pid


def start_check(run: Run, waiting: list[dict]) -> None:
    """adw_batch_check.py on the waiting groups' branches, in the background."""
    n = len(run.s.get("checks") or []) + 1
    d = run.dir / "checks" / str(n)
    d.mkdir(parents=True, exist_ok=True)
    tree = batch_check.worktree_path(run.s["run_id"], str(REPO_ROOT))
    request = {"n": n, "run_id": run.s["run_id"], "worktree": tree,
               "branches": [{"adw_id": g["adw_id"], "issue": g.get("issue_number"),
                             "title": g.get("issue_title") or g["title"], "branch": g["check"].get("branch"),
                             "sha": g["check"]["sha"], "ask": g["check"]["n"]} for g in waiting]}
    batch_check.write_json(str(d / "request.json"), request)
    cur = {"n": n, "dir": str(d), "started": time.time(), "groups": [g["adw_id"] for g in waiting], "tries": 1}
    run.s["check"], run.s["check_worktree"] = cur, tree
    _launch_check(run, cur)
    for g in waiting:
        others = [group_name(o) for o in waiting if o is not g]
        g["check"].update(state="running", batch=n)
        check_note(g, "Starting" + (f", together with {', '.join(others)}" if others else ""))
    run.save()


def deliver_check(run: Run, cur: dict, result: dict) -> None:
    """Each group's part of a finished check into its inbox (adw_report.py check is waiting for it)."""
    request = json.loads((Path(cur["dir"]) / "request.json").read_text(encoding="utf-8"))
    asks = {b["adw_id"]: b.get("ask") for b in request.get("branches") or []}
    for adw_id in cur["groups"]:
        g = next((x for x in run.s["groups"] if x.get("adw_id") == adw_id), None)
        entry = (result.get("branches") or {}).get(adw_id) or {"status": "error"}
        status_ = entry.get("status") or "error"
        msg = {"type": "check_result", "n": asks.get(adw_id), "batch": cur["n"], "status": status_,
               **{k: entry[k] for k in ("yours", "combined", "preexisting", "unknown", "conflict", "report")
                  if entry.get(k)}}
        if status_ == "error":
            msg["error"] = result.get("error") or "the check stopped without a result"
        messages.append(str(adw_file(adw_id, messages.INBOX)), msg)
        if not g:
            continue
        if (g.get("check") or {}).get("n") == asks.get(adw_id):
            g["check"].update(state="done", result=status_)
        counts = {k: len(entry.get(k) or []) for k in ("yours", "combined", "preexisting", "unknown")}
        extra = "; ".join(f"{n} {k}" for k, n in counts.items() if n)
        if status_ == "green":
            check_note(g, "Green" + (f" ({extra})" if extra else ""), "done")
        elif status_ == "conflict":
            c = entry.get("conflict") or {}
            check_note(g, f"Conflicts with {', '.join(c.get('with') or []) or 'another branch'}: checked on its own "
                          "next")
        elif status_ == "error":
            check_note(g, f"The batch check couldn't run ({msg['error'][:120]}): running the full suites on the branch")
        else:
            check_note(g, f"Failures: {extra}", "failed")


def poll_check(run: Run, cur: dict) -> None:
    d = Path(cur["dir"])
    if _check_alive(cur):
        try:
            st = json.loads((d / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        note = st.get("phase", "") + (f": {st['note']}" if st.get("note") else "")
        for g in run.s["groups"]:
            if g.get("adw_id") in cur["groups"] and (g.get("check") or {}).get("state") == "running":
                check_note(g, note)
        return
    try:
        result = json.loads((d / "result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result = None
    if result is None and cur.get("tries", 1) < CHECK_TRIES:
        cur["tries"] = cur.get("tries", 1) + 1
        log(f"The full check {cur['n']} stopped without a result; starting it again")
        _launch_check(run, cur)
        run.save()
        return
    if result is None:
        try:
            last = (d / "check.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1]
        except (OSError, IndexError):
            last = ""
        result = {"error": f"the check stopped without a result ({last[:200]})", "branches": {}}
    deliver_check(run, cur, result)
    run.s.setdefault("checks", []).append({"n": cur["n"], "groups": cur["groups"], "ok": bool(result.get("ok")),
                                           "error": result.get("error"), "started": iso(cur["started"]),
                                           "ended": now_iso()})
    run.s["check"] = None
    run.save()


def full_checks(run: Run) -> None:
    """Start the batch's full check when it's time, follow the running one, and deliver its results."""
    if fake(run):
        return
    if run.s.get("check"):
        poll_check(run, run.s["check"])
        return
    groups = run.s["groups"]
    waiting = [g for g in groups if g["status"] == "running" and (g.get("check") or {}).get("state") == "waiting"]
    if not waiting:
        return
    working = [g for g in groups if g["status"] == "running" and g not in waiting
               and g.get("workflow", "orchestrated") == "orchestrated"]
    oldest = min(g["check"]["since"] if g["check"].get("since") is not None else time.time() for g in waiting)
    if working and not any(g["check"].get("solo") for g in waiting) and time.time() - oldest < CHECK_MAX_WAIT:
        names = ", ".join(group_name(g) for g in working)
        for g in waiting:
            check_note(g, f"Waiting for {names} to finish (the full suites run once for the batch)")
        return
    start_check(run, waiting)


RETRY_RESET = ("adw_id", "pid", "progress", "phase", "pr_url", "completed", "offset", "started_at", "cleaned",
               "closed", "simulated", "ended_at", "log", "ports", "not_before", "next_adw_id", "paused", "sim_elapsed",
               "sim_tick", "sim_asked", "sim_waiting_ask", "sim_inbox", "design_placed")


def can_continue(run: Run, g: dict) -> bool:
    """A stopped orchestrated workflow whose worktree and orchestrator session are still there continues (same
    adw_id: no cleanup, `claude --resume`) instead of starting over."""
    if fake(run) or g.get("workflow") != "orchestrated" or not g.get("adw_id"):
        return False
    state = adw_state(g["adw_id"])
    worktree = state.get("worktree_path")
    return bool(state.get("orchestrator_session_id") and worktree and Path(worktree).is_dir())


def retry_failed(run: Run) -> int:
    """On Resume: queue the failed workflows again, on the same issues, and the ones Ore's closing interrupted
    (still "running", but their process is gone). An orchestrated workflow that got past setup continues where it
    stopped (can_continue: same ADW, same worktree, the session resumed). The others start over with a fresh ADW,
    after removing what the old one left behind locally (worktree, local branch, database, ports). Issues and any
    PRs stay. Before the workflows start (Ore closed while the questions or the groups waited for the user), the
    groups have no status yet: nothing to rerun, and the run goes on from its phase."""
    if run.s.get("phase") not in ("workflows", "done"):
        return 0
    stale = []
    for g in run.s["groups"]:
        if g.get("status") == "running" and not fake(run) and not alive(g)[0]:
            read_progress(g)
            if not (g.get("completed") or g.get("pr_url")):      # (a finished one is marked done by workflows())
                stale.append(g)
    failed = [g for g in run.s["groups"] if g.get("status") == "failed"] + stale
    if run.s.get("check") and not _check_alive(run.s["check"]):      # the check died with Ore: run it again
        run.s["check"]["tries"] = 1
        _launch_check(run, run.s["check"])
    for g in failed:
        if can_continue(run, g):
            adw_id = g["adw_id"]
            give_back(run, g)                     # whatever the stopped process still held; it re-acquires them
            for key in RETRY_RESET:
                g.pop(key, None)
            g.update(status="queued", message="Waiting to continue where it stopped", next_adw_id=adw_id,
                     continue_adw=adw_id)
            continue
        if g.get("adw_id"):
            usage = group_usage(g)
            if usage:
                g["usage_before"] = usage         # what the failed ADW used still counts
            for problem in clean_group(run, g, on_github=False):
                log(f"Before rerunning, couldn't clean up everything: {problem}")
        for key in RETRY_RESET:
            g.pop(key, None)
        g.pop("continue_adw", None)
        g.update(status="queued", message="Waiting to run again")
    if failed:
        run.s["phase"] = "workflows"
        stage_start(run, "workflows")
        run.save()
    return len(failed)


# ---- cleanup: Ore's Delete ------------------------------------------------
GITHUB_OPTION = "github"
CLOSED_NOTE = "Closed from Ore: the run that created this was deleted."


def _running(pid: int) -> str:
    """The process's command line, or "" when it isn't running."""
    p = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def _stop(pid: int | None, group: bool = False, looks_like: str | None = None) -> None:
    """SIGTERM, then SIGKILL if it's still there after 5 s. A single process only when its command line
    contains looks_like (the pid may have been reused); a group (an ADW, started in its own session) always."""
    if not pid or pid == os.getpid():
        return
    if not group and (looks_like or "") not in _running(pid):
        return
    kill = os.killpg if group else os.kill
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            kill(pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        for _ in range(50):
            time.sleep(0.1)
            try:
                kill(pid, 0)
            except (ProcessLookupError, PermissionError):
                return


def _cmd(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)


def close_on_github(g: dict, branch: str | None) -> list[str]:
    """Close the group's open pull requests (deleting their branches) and its issue."""
    problems = []
    prs = {g["pr_url"]} if g.get("pr_url") else set()
    if branch:
        p = _cmd("gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url", "-q", ".[].url")
        prs |= {u for u in p.stdout.split() if u}
    for url in prs:
        if _cmd("gh", "pr", "view", url, "--json", "state", "-q", ".state").stdout.strip() != "OPEN":
            continue                          # merged or closed already: leave it
        p = _cmd("gh", "pr", "close", url, "--comment", CLOSED_NOTE, "--delete-branch")
        if p.returncode:
            problems.append(f"closing {url}: {p.stderr.strip()}")
    if branch and not prs and _cmd("git", "ls-remote", "--exit-code", "--heads", "origin", branch).returncode == 0:
        p = _cmd("git", "push", "origin", "--delete", branch)
        if p.returncode:
            problems.append(f"deleting the branch {branch} on GitHub: {p.stderr.strip()}")
    issue = str(g["issue_number"])
    if _cmd("gh", "issue", "view", issue, "--json", "state", "-q", ".state").stdout.strip() == "OPEN":
        p = _cmd("gh", "issue", "close", issue, "--reason", "not planned", "--comment", CLOSED_NOTE)
        if p.returncode:
            problems.append(f"closing issue #{issue}: {p.stderr.strip()}")
    return problems


def clean_group(run: Run, g: dict, on_github: bool) -> list[str]:
    """Undo one workflow. Marks what's done in the group, so a retry only repeats what failed."""
    adw_id, problems = g.get("adw_id"), []
    state = ADWState.load(adw_id) if adw_id and not fake(run) else None
    data = state.data if state else {}
    branch = data.get("branch_name")
    if adw_id and not g.get("cleaned"):
        if not fake(run):
            from adw_modules.utils import setup_logger
            from adw_modules.worktree_ops import remove_worktree
            _stop(data.get("workflow_pgid") or g.get("pid"), group=True)
            ok, err = remove_worktree(adw_id, setup_logger(adw_id, "ore_cleanup"),
                                      data.get("backend_port"), data.get("frontend_port"))
            if not ok:
                return [f"{g['title']}: {err}"]
        if resources.enabled():
            resources.release(adw_id)          # its lease and workflow slot (a simulated one's too)
        g["cleaned"] = True
        run.save()
    if on_github and g.get("issue_url") and not g.get("closed"):
        problems = close_on_github(g, branch)
        if problems:
            return [f"{g['title']}: {p}" for p in problems]
        g["closed"] = True
        run.save()
    if branch and _cmd("git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0:
        p = _cmd("git", "branch", "-D", branch)
        if p.returncode:
            return [f"{g['title']}: deleting the local branch {branch}: {p.stderr.strip()}"]
    if adw_id:
        shutil.rmtree(REPO_ROOT / "agents" / adw_id, ignore_errors=True)
    if g.get("issue_number") and (fake(run) or g.get("closed")):
        progress_file(g).unlink(missing_ok=True)
    return []


def clean(run_dir: Path, options: set[str]) -> None:
    run = Run(run_dir)
    if not run.s:
        shutil.rmtree(run_dir, ignore_errors=True)
        result("Nothing left to clean up")
        return
    status("Stopping the run")
    _stop(run.s.get("trigger_pid"), looks_like="trigger_ore")
    on_github = GITHUB_OPTION in options and not fake(run)
    groups, problems = all_groups(run), []
    for n, g in enumerate(groups):
        status(f"Cleaning up: {g['title']}", progress=n / len(groups))
        try:
            problems += clean_group(run, g, on_github)
        except Exception as e:
            problems.append(f"{g['title']}: {type(e).__name__}: {e}")
    cur = run.s.get("check")
    if cur and cur.get("pid"):
        _stop(cur["pid"], group=True)
    tree = run.s.get("check_worktree")
    if tree and not fake(run):
        problem = batch_check.remove_worktree(tree, str(REPO_ROOT))
        if problem:
            problems.append(f"Full-check worktree: {problem}")
    if problems:
        error("Not everything could be cleaned up:\n" + "\n".join(f"- {p}" for p in problems))
    if run.s.get("run_id"):                 # the prototypes and the files the user attached to answers
        for folder in ("designs", "runs"):
            shutil.rmtree(REPO_ROOT / ".ore" / folder / str(run.s["run_id"]), ignore_errors=True)
    shutil.rmtree(run_dir, ignore_errors=True)
    n = len(groups)
    result(f"Cleaned up {n} workflow{'s' if n != 1 else ''}" + (" and closed them on GitHub" if on_github and n else ""))


def announce_cleanup(run: Run) -> None:
    """Tell Ore how to undo this run if the user deletes it."""
    if run.s.get("simulate"):
        cleanup("--cleanup", str(run.dir), description="Removes this simulated run's saved state and frees the "
                "resources it leased. A simulation creates nothing on GitHub and starts no real workflows.")
        return
    if run.s["dry_run"]:
        cleanup("--cleanup", str(run.dir), description="Removes this dry run's saved state. A dry run creates "
                "nothing on GitHub and starts no workflows.")
        return
    cleanup("--cleanup", str(run.dir),
            description="Stops the workflows, then removes their worktrees, local branches, isolated databases and "
                        "port reservations, the full check's worktree, and this run's saved state. Work that wasn't "
                        "pushed is lost.",
            options=[{"key": GITHUB_OPTION, "label": "Also close the issues and open pull requests on GitHub, and "
                      "delete the branches there", "default": False}])


# ---- Ore's project board: taking items out while planning (withdraw), planning again (--ore-replan) -------------

def all_groups(run: Run) -> list[dict]:
    """Every group the run holds work for: its workflows, those it keeps aside while it plans again, and earlier
    ones whose work a replan kept without reusing it (their branches and draft pull requests)."""
    return (run.s.get("groups") or []) + (run.s.get("kept_groups") or []) + (run.s.get("previous_groups") or [])


def withdraw(run: Run, msg: dict) -> None:
    """Ore's stdin {"type": "withdraw", "id", "items": [positions], "reason"}: the user moved those items back to
    review on Ore's board. Only while the run plans (questions, groups check); they leave the plan and the groups,
    Claude is told at its next turn, and an open groups check is asked again without them."""
    mid = str(msg.get("id") or f"w{int(time.time())}")
    reason = str(msg.get("reason") or "").strip()
    if run_phase(run) != "planning":
        reply(mid, "The workflows have started, so items can't be taken out of this run any more. Send the work "
                   "back to planning first.")
        return
    planned = {it["id"]: it for it in planned_items(run)}
    take = list(dict.fromkeys(i for i in (item_id(r) for r in msg.get("items") or []) if i in planned))
    if not take:
        reply(mid, "None of those items are in this run's plan.")
        return
    if len(take) == len(planned):
        reply(mid, "That would take out every item. Stop the run instead.")
        return
    withdrawn = run.s.setdefault("withdrawn", {})
    for i in take:
        withdrawn[i] = reason
    for g in run.s.get("groups") or []:
        g["item_ids"] = [i for i in g["item_ids"] if i not in take]
    run.s["groups"] = [g for g in run.s.get("groups") or [] if g["item_ids"]]
    names = " and ".join(f"item {i} ({planned[i]['title']})" for i in take)
    run.s.setdefault("planning_notes", []).append(
        f"The user took {names} out of this run{f': {reason}' if reason else ''}. Leave "
        f"{'it' if len(take) == 1 else 'them'} out of the questions, the plan and the groups.")
    run.save()
    reply(mid, "Took out " + " and ".join(f"“{planned[i]['title']}”" for i in take) + ".")
    if run.s.get("phase") == "review" and (run.s.get("pending") or {}).get("key") and IO.enabled:
        # the groups check is open: the same id again replaces it in Ore, without the items
        emit({"type": "input_request", "id": run.s["pending"]["key"], "prompt": review_prompt(run), "kind": "groups",
              "groups": review_payload(run)})
    report(run, _last_status[0] or "Planning")


def replan(run: Run, req: dict) -> None:
    """Ore's --ore-replan {id, reason, keep_work, items, prs}: the user moved a building (or finished) card back to
    approved. The workflows holding those items (every workflow when items is empty) go back to planning, with the
    reason as new input to Claude's questions; the others are left alone and rejoin when the new groups start.
    keep_work: their worktrees, branches and orchestrator sessions stay and their open pull requests become drafts;
    a new group with exactly the items of one of them continues it (carry_on). Otherwise they're undone as Delete
    would (stopped, worktrees and branches removed, pull requests and issues closed) and planned from scratch.
    Restart-safe: the request is saved first and finished on the next --resume if the run stops half-way."""
    run.s["replan"] = req
    run.save()
    reason = str(req.get("reason") or "").strip()
    keep = bool(req.get("keep_work"))
    want = {item_id(i) for i in req.get("items") or []}
    groups = run.s.get("groups") or []
    affected = [g for g in groups if want & set(g.get("item_ids") or [])] if want else list(groups)
    affected = affected or list(groups)
    kept = [g for g in groups if not any(g is a for a in affected)]
    if not kept and (run.s.get("check") or {}).get("pid"):      # nothing left for the batch's full check to check
        _stop(run.s["check"]["pid"], group=True)
        run.s["check"] = None
    if keep:
        problems = keep_for_replan(run, affected, req)
    else:
        problems = []
        for g in affected:
            try:
                problems += clean_group(run, g, on_github=True)
            except Exception as e:  # noqa: BLE001
                problems.append(f"{g['title']}: {type(e).__name__}: {e}")
    if problems:
        error("Couldn't clear the work so far before planning again:\n" + "\n".join(f"- {p}" for p in problems)
              + "\nTry again.")
        return
    titles = {g["title"] for g in affected}
    run.s["asks"] = [a for a in run.s.get("asks") or [] if a.get("group") not in titles]
    if kept:
        run.s["kept_groups"] = kept
        run.s["scope"] = [i for g in affected for i in g.get("item_ids") or []]
    else:
        run.s.pop("kept_groups", None)
        run.s.pop("scope", None)
    if keep:
        run.s["previous_groups"] = (run.s.get("previous_groups") or []) + affected
    stages_ = run.s.setdefault("stages", {})
    for key in ("review", "issues", "workflows"):
        stages_.pop(key, None)
    stages_.get("clarify", {}).pop("ended", None)
    stages_.get("clarify", {}).pop("note", None)
    run.s.update(groups=[], phase="clarify", pending=None, replan_reason=reason, replanning=True,
                 replans=int(run.s.get("replans") or 0) + 1)
    run.s["next_message"] = replan_message(run, reason, affected, keep)
    run.s.pop("replan", None)
    run.save()
    report(run, f"Planning again: {reason}"[:300] if reason else "Planning again")


def keep_for_replan(run: Run, groups: list[dict], req: dict) -> list[str]:
    """Planning again with the work kept: stop the workflows (worktrees, branches and orchestrator sessions stay)
    and turn the open pull requests into drafts (`gh pr ready <n> --undo`), so nobody merges them meanwhile. A pull
    request that can't become a draft (merged, closed) is only logged."""
    numbers = {str(n).lstrip("#") for n in req.get("prs") or [] if str(n).lstrip("#").isdigit()}
    by_number = {}
    for g in groups:
        if g.get("status") == "running" and g.get("adw_id") and not fake(run):
            _stop(adw_state(g["adw_id"]).get("workflow_pgid") or g.get("pid"), group=True)
        give_back(run, g)
        if g.get("status") in ("running", "queued"):
            g.update(status="stopped", ended_at=time.time())
        if g.get("pr_url"):
            n = g["pr_url"].rstrip("/").rsplit("/", 1)[-1]
            by_number[n] = g
            numbers.add(n)
    if fake(run):
        return []
    for n in sorted(numbers, key=int):
        p = _cmd("gh", "pr", "ready", n, "--undo")
        if p.returncode == 0:
            if n in by_number:
                by_number[n]["drafted"] = True
        else:
            log(f"Couldn't turn pull request #{n} into a draft: {p.stderr.strip()}")
    return []


def replan_message(run: Run, reason: str, groups: list[dict], keep: bool) -> str:
    """Claude's next turn after a replan: why, what exists, which items to plan again."""
    items = planned_items(run)
    lines = [f"The user sent this work back to planning. Their reason: {reason or '(none given)'}"]
    if keep and groups:
        lines.append("The work so far is kept (its pull requests are drafts now):")
        for g in groups:
            branch = adw_state(g.get("adw_id")).get("branch_name")
            lines.append(f"- {g['title']} (items {', '.join(g.get('item_ids') or [])})"
                         + (f", branch {branch}" if branch else "") + (f", {g['pr_url']}" if g.get("pr_url") else ""))
        lines.append("A group with exactly the items of one of these continues on its branch and pull request with "
                     "the new plan; any other group starts again from main.")
    elif any(g.get("adw_id") or g.get("issue_url") for g in groups):
        lines.append("The work so far was thrown away (pull requests and issues closed, branches deleted): plan "
                     "these items from scratch.")
    lines.append(f"Plan item{'s' if len(items) != 1 else ''} {', '.join(it['id'] for it in items)} again. Ask if "
                 "you need to, then propose the groups again.")
    text = "\n".join(lines)
    if not run.s.get("session_id"):
        text = items_prompt(items, Path(run.s.get("items_file") or "the batch").name) + "\n\n" + text
    return text


def carry_on(run: Run, g: dict) -> None:
    """After a replan that kept the work: a new group with exactly the items of an earlier workflow that can
    continue (worktree and orchestrator session still there) continues it on its issue, branch and pull request,
    with the new plan as a follow-up round. Earlier workflows nothing continues keep their branches and drafts."""
    previous = run.s.get("previous_groups") or []
    old = next((o for o in previous if sorted(o.get("item_ids") or []) == sorted(g["item_ids"])
                and can_continue(run, o)), None)
    if old is None:
        return
    previous.remove(old)
    n = int(old.get("follow_ups") or 0) + 1
    for key in ("issue_number", "issue_url", "pr_url", "workflow", "usage_before", "drafted"):
        if old.get(key):
            g[key] = old[key]
    reason = run.s.get("replan_reason") or "no reason given"
    g.update(follow_ups=n, continue_adw=old["adw_id"], next_adw_id=old["adw_id"],
             message="Waiting to continue with the new plan",
             follow_up={"n": n, "id": f"replan-{run.s.get('replans') or n}",
                        "text": f"This work went back to planning ({reason}). The plan for this workflow now:\n\n"
                                + g["issue_body"],
                        "from": os.getenv("ORE_USER_NAME") or "the user"})


def ready_again(run: Run, g: dict) -> None:
    """A workflow whose pull request a replan turned into a draft finished again: ready for review once more."""
    if not g.pop("drafted", False) or not g.get("pr_url") or fake(run):
        return
    p = _cmd("gh", "pr", "ready", g["pr_url"])
    if p.returncode:
        log(f"Couldn't mark {g['pr_url']} ready for review again: {p.stderr.strip()}")


# ---- --simulate: the whole run without Claude or GitHub ---------------------------------

SIM_BATCH = """---
workspace: Simulation
items: 3
---

- [ ] Show the order status on the orders page
  Customers keep asking where their order is; show the status and the last update on the orders page.
  Size: M

- [ ] Fix the typo in the checkout button
  It says "Chekout".
  Size: S

- [ ] Add CSV export to the orders page
  Finance wants the filtered orders list as CSV.
  Size: M
"""

SIM_QUESTIONS = [
    {"question": "Which order statuses should the orders page show?", "header": "Statuses", "multiSelect": False,
     "options": [{"label": "All statuses", "description": "pending, paid, shipped, delivered, cancelled"},
                 {"label": "Open orders only", "description": "everything except delivered and cancelled"}]},
    {"question": "Which columns go into the CSV export?", "header": "CSV columns", "multiSelect": True,
     "options": [{"label": "Order number", "description": "the public order reference"},
                 {"label": "Customer", "description": "name and email"},
                 {"label": "Totals", "description": "amount, VAT and currency"}]},
]


def sim_speed() -> float:
    try:
        return max(0.01, float(os.getenv("ORE_SIM_SPEED", "1")))
    except ValueError:
        return 1.0


def simulated_groups(run: Run) -> list[dict]:
    """Groups as Claude would propose them: consecutive items together, no more groups than free slots; the first
    one with significant screen changes."""
    items = planned_items(run)
    k = max(1, min(free_workflow_slots(), len(items), (len(items) + 1) // 2))
    size = -(-len(items) // k)
    groups = []
    for n in range(0, len(items), size):
        chunk = items[n:n + size]
        groups.append({"title": chunk[0]["title"][:60] + (f" (+{len(chunk) - 1})" if len(chunk) > 1 else ""),
                       "summary": "Same pages and modules" if len(chunk) > 1 else "Independent change",
                       "item_ids": [it["id"] for it in chunk],
                       # the first group changes a page (a prototype); the others nothing visible
                       "frontend": "significant" if n == 0 else "none"})
    return groups


def simulated_turn(run: Run, message: str) -> dict:
    """What Claude would answer in a clarification turn, canned: one round of questions, then groups, then issues."""
    time.sleep(min(3.0, 3.0 / sim_speed()))
    run.s["slots_free"] = free_workflow_slots()
    if run.s.get("phase") == "issues":
        by_id = {it["id"]: it for it in run.s["items"]}
        return {"status": "issues", "groups": [
            {"title": g["title"], "item_ids": g["item_ids"], "issue_title": g["title"],
             "issue_body": "## Context\nSimulated issue (trigger_ore.py --simulate).\n\n## What to do\n"
                           + "\n".join(f"- {by_id[i]['title']}" for i in g["item_ids"] if i in by_id)}
            for g in run.s["groups"]]}
    if not run.s.get("question_rounds"):
        return {"status": "questions", "questions": SIM_QUESTIONS}
    return {"status": "ready", "groups": simulated_groups(run),
            "grouping_reason": "Simulated: consecutive items share pages and modules"}


def sim_lease(run: Run, g: dict) -> None:
    """A simulated workflow holds a real lease (ports, Redis database) and slot, so the registry is exercised;
    nothing is started on them."""
    if not uses_registry(run):
        return
    lease = resources.acquire(g["adw_id"], hold="process", pid=os.getpid())
    resources.try_acquire_slot(resources.WORKFLOW, g["adw_id"], adw_id=g["adw_id"], pid=os.getpid())
    g["ports"] = [lease["backend_port"], lease["frontend_port"]]


# ---- queries (Ore's Home page; Ore's docs/script-protocol.md §8) ----------------------------------------------
#
# Ore runs this script with `--ore-query <name> [args...]` (env ORE_QUERY=<name>), no stdin, and reads one line:
# {"type": "answer", "query": <name>, "data": {...}}, exit 0; or {"type": "error", "message": ...}, exit 1.
# Queries never start workflows; only `ask`, `items` and `consult` call Claude (read-only). `merge` and `revert` write to
# GitHub (`revert` in a temporary worktree of its own, never in the main checkout). The run's status messages say
# which queries this script answers.

QUERIES = ("machine", "prs", "merge", "merge_run", "ask", "items", "consult",
           "revert")                                      # merge_run: not a query (--ore-merge)
ASK_MODEL = os.getenv("ADW_ASK_MODEL", "sonnet")
ASK_TIMEOUT = 8 * 60                       # Ore waits 10 minutes for an `ask`
ASK_RULES = """You answer a question about this codebase from someone on the team, who asked it in a chat (Telegram)
through Ore. Find the answer in the repository: start from CLAUDE.md and the project's own docs and context
(e.g. ai_docs/, docs/, app_docs/, specs/, .claude/) before searching the code, so you answer fast. You are read-only:
never change, create or delete files, and don't run anything that does.
Answer for a chat message: plain text (no Markdown tables, no headings), short and direct (a few sentences, or a
short list), with the file paths or names that back it up when they help. If the repository doesn't say, say so
plainly and say where you looked; don't guess. If the question is really a request for a change, answer what you
can and say that Ore can turn it into work when they send it as a request."""
ITEMS_MODEL = os.getenv("ADW_ITEMS_MODEL", ASK_MODEL)
# Read-only history, to tell whether an item is already done and by which commit / pull request
ITEMS_HISTORY = ("Bash(git log:*)", "Bash(git show:*)", "Bash(git remote get-url:*)", "Bash(gh pr list:*)",
                 "Bash(gh pr view:*)")
# The consult sessions may also read pull requests' diffs and checks (the PR reviewer, merge planner and closer)
CONSULT_TOOLS = (*ITEMS_HISTORY, "Bash(git diff:*)", "Bash(gh pr diff:*)", "Bash(gh pr checks:*)")
ITEMS_MINUTES = 9                          # unless the request says (Ore waits a minute longer than it asks for)
CONSULT_MODEL = os.getenv("ADW_CONSULT_MODEL", ITEMS_MODEL)
CONSULT_MINUTES = 15                       # unless the request says
SPECIALIST_NAME = re.compile(r"[a-z0-9_-]+")
# Used when the repository has no adws/specialists/<name>.md (keep them in step with those files)
_SPECIALIST_RULES = """
"messages" is what you say on an item's card in Ore ({"item": "<id>", "text": "..."}): use it only when there is
something worth telling the user; most runs need none. If the request has a "message", the user wrote to you on a
card (read their attached files with Read; Office documents have a .txt beside them): answer it in "messages" and
change your answer if what they say changes it.
Use the item ids exactly as given.
You are read-only: never edit, create or delete files, never commit, never push, and don't run anything that does.
Reply strictly in the given schema. Plain short sentences, no jargon."""
BACKLOG_FALLBACK = """You are the backlog keeper for this repository. Ore (a meeting assistant) sends you the open
action items of this workspace, the team's goals and a JSON schema for your answer. Read the repository (start with
CLAUDE.md and the project's docs) and review the items (ordering is not your job: Ore's planner does it):
1. Duplicates: items that ask for the same thing. Keep one (the clearest, or the one with the most detail), list the
   others to close, write the kept item's detail rewritten to cover everything the closed ones added, and give a
   one-line reason. "possible_duplicate_of" is only a hint.
2. Already done: an item is done only when the code clearly does what it asks. Check with git log / git show and
   gh pr list / gh pr view; cite the commit hash and the commit or pull request URL when you find them. If unsure,
   it is not done.
Never close an item marked "keep": true or "pinned": true (it may still be the kept item of a duplicate group).
""" + _SPECIALIST_RULES
TRIAGE_FALLBACK = """You are the triage specialist for this repository. Ore (a meeting assistant) sends you action
items of this workspace, the team's goals, Ore's "workspaces" and a JSON schema for your answer. Read the repository
(start with CLAUDE.md and the project's docs) so you know what it covers, then give every item one verdict:
- "dev": a change to this repository (code, tests, docs, configuration, build or deployment kept here). The usual one.
- "not_dev": not development work at all (an email, a call, a meeting, a purchase, admin). If a general workspace in
  "workspaces" fits, give its slug in "workspace".
- "other_workspace": development work for another codebase; its slug in "workspace", only from "workspaces".
- "split": clearly several separate tasks (built and reviewed apart): two to five "parts", each a short title and a
  detail that stands on its own. Not just because an item has several steps.
When unsure, choose "dev". "workspace" is empty and "parts" empty unless the verdict needs them. Give each a one-line
"reason" the user will read. Give exactly one entry per item.
""" + _SPECIALIST_RULES
PLANNER_FALLBACK = """You are the planner for this repository. Ore (a meeting assistant) sends you the open action
items of this workspace, the team's goals and a JSON schema for your answer. Read the repository (start with
CLAUDE.md and the project's docs, then the code where you need it), then:
1. Order: rank every item by what to build first, weighing the goals, the dependencies, urgency (priority, due) and
   size. Each gets a one-line reason and a size: S (a small change in one place), M (a few files or one feature,
   about a day), L (several parts of the code, a new feature or a migration). Pinned items are ranked too.
2. Links: real dependencies only (the item can't be built until blocked_by is done), each with a short reason.
   Links the user made are already in the item's "links"; don't repeat them.
3. Groups: items that belong in one run (one branch and pull request): the same part of the code, small, simpler
   together. Only when clearly better; each item in at most one group.
""" + _SPECIALIST_RULES
SCOPER_FALLBACK = """You are the scoper for this repository. Ore (a meeting assistant) sends you action items the user
wants built soon, the team's goals and a JSON schema for your answer. Read the repository (start with CLAUDE.md and
the project's docs, then the code the item touches), then decide for every item whether it is clear enough to build:
- Clear (a developer who knows this codebase could build it without asking): "clear": true and two to six acceptance
  "criteria", each specific and testable ("The refunds export has a date column in YYYY-MM-DD."). Keep the item's
  criteria that still hold.
- Not clear (something only the user can decide is missing): "clear": false and at most three concrete "questions",
  each answerable in a sentence. Don't ask what the repository or the conversation already answers; use the user's
  earlier answers.
Give every item a one-line "note". Ore posts your questions itself, so don't repeat them in "messages".
""" + _SPECIALIST_RULES
# After the build (request version 3): the run ("run") or the card ("card": its items with their criteria, its pull
# requests, the approved design's path, the test plan and the risks) is in the request.
_AFTER_BUILD_RULES = """
"messages" is what you say on the card in Ore (one entry per item it concerns, in the schema's shape): only when there
is something worth telling the user beyond your answer. If the request has a "message", the user wrote to you on the
card (read their attached files with Read; Office documents have a .txt beside them): answer it in "messages" and
change your answer if what they say changes it.
Use the item ids and pull request numbers exactly as given.
You are read-only: never edit, create or delete files, never commit, never push, never merge, comment on or close a
pull request, and don't run anything that changes the repository or GitHub.
Reply strictly in the given schema. Plain short sentences, no jargon."""
DOCTOR_FALLBACK = """You are the build doctor for this repository. A workflow that builds a card's work failed, or has
sent no news for a long time. Ore (a meeting assistant) sends you the "run" (its status, error, last message, phase,
the last lines of its log and its parts with their steps and links) and a JSON schema for your answer. Read the log
tail first, then the repository where it points (CLAUDE.md, the project's docs, the code and tests it names; git log /
git show / git diff, gh pr view / gh pr checks for its pull request). Then say plainly why it failed or stalled
("diagnosis": two to four sentences a non-developer can follow) and what to do ("action"):
- "resume": it stopped for a reason that is gone (a restart, a timeout, the machine was busy); carry on where it was.
- "retry": a transient failure (network, rate limit, a flaky test) in a step worth running again from the start.
- "follow_up": the workflow needs an instruction to get past it (a failing test it should fix, a wrong approach):
  give that instruction in "follow_up", specific enough to act on, and the part's key in "part" when one part failed.
- "none": nothing a run can fix (the user must decide something, or it is fine and only slow): say why.
""" + _AFTER_BUILD_RULES
PR_REVIEWER_FALLBACK = """You are the pull request reviewer for this repository. A card's pull requests are open with
their checks passing, ready to merge. Ore (a meeting assistant) sends you the "card": its action items with their
acceptance criteria, its pull requests (number, url, state, checks, review, head), the path of the approved design (an
HTML prototype in the repository) if there is one, the test plan and the accepted risks, and a JSON schema for your
answer. Read each pull request (gh pr view, gh pr diff, gh pr checks; git log / git show / git diff) and judge it
against what the items asked: does it do it, does it meet every criterion, does it match the approved design (open the
HTML with Read), does it add the tests the plan names, does it stay in scope (no unrelated changes) and handle the
risks as agreed? Give every pull request a "verdict": "pass", or "gaps" with each gap as one concrete line the
workflow can act on ("The export has no date column (criterion 2)."), and a one-line "note". Style nits are not gaps.
""" + _AFTER_BUILD_RULES
MERGE_PLANNER_FALLBACK = """You are the merge planner for this repository. A card has more than one open pull request
ready to merge. Ore (a meeting assistant) sends you the "card" (its items, its pull requests with number, url, state,
checks, review and head) and a JSON schema for your answer. Read each pull request (gh pr view, gh pr diff; git log /
git diff against the base branch) and give the merge "order" (every open pull request number once) that keeps
conflicts and broken builds to a minimum: what others depend on first (migrations, shared models, APIs), then the
rest; pull requests that touch the same files one after another, the smaller first. In "notes", one line per pull
request that needs something before or after its turn ("Bring it up to date with main after #212: both change
models.py."); leave out those that need nothing.
""" + _AFTER_BUILD_RULES
CLOSER_FALLBACK = """You are the closer for this repository. All of a card's pull requests are merged. Ore (a meeting
assistant) sends you the "card": its action items with their acceptance criteria, its merged pull requests, the
approved design's path and the test plan, and a JSON schema for your answer. Check each item against the merged work
(gh pr view / gh pr diff, git log / git show / git diff on the base branch, and the code as it is now): "done": true
only when the merged code clearly does what the item asks and meets its criteria; a one-line "note" either way (what
does it, or what is missing). List what is left over in "leftovers": work an item asked for that the merged pull
requests don't do, or a follow-up they clearly need (a short "title", a "detail" that stands on its own, and the
"item" id it comes from). Don't list nice-to-haves nobody asked for; an empty list is fine.
""" + _AFTER_BUILD_RULES
SPECIALIST_FALLBACKS = {"backlog": BACKLOG_FALLBACK, "triage": TRIAGE_FALLBACK, "planner": PLANNER_FALLBACK,
                        "scoper": SCOPER_FALLBACK, "doctor": DOCTOR_FALLBACK, "pr_reviewer": PR_REVIEWER_FALLBACK,
                        "merge_planner": MERGE_PLANNER_FALLBACK, "closer": CLOSER_FALLBACK}
# The question round's specialists (used when adws/specialists/<name>.md is missing; keep them in step)
_ROUND_RULES = """
When the user asks for changes, you continue this session: take their answer into account (read any files they
attached with Read; Office documents have a .txt beside them) and give your updated answer.
Reply strictly in the given schema. Plain short sentences, no jargon."""
_READ_ONLY = """
You are read-only: never edit, create or delete files, never commit, never push, and don't run anything that changes
the repository or GitHub."""
DESIGNER_FALLBACK = """You are the designer for this repository. Before a group of work is built, Ore (a meeting
assistant) asks you for a clickable prototype of what it changes on screen, so the user can click through it and
approve it before any code is written. The message gives you the group, the user's answers and the exact file to write.
First read CLAUDE.md, the project's docs and the frontend code the group touches (pages, shared layout, components,
styles and theme): the prototype must look like it belongs in this app, with its navigation, components, wording and
visual language.
The prototype is ONE self-contained HTML file at exactly the path in the message: inline CSS and JavaScript, images as
data: URIs or inline SVG, nothing loaded from the network. Realistic content from this app's domain (no lorem ipsum)
and the states that matter (empty, error, long lists, validation, success). The main flow is clickable with plain
JavaScript and fake data. Accessible: semantic HTML, visible keyboard focus, enough contrast, alt text, aria where
needed; it works at phone width too. A one-line note at the top says it is a prototype and what to try.
For changes, read the earlier version and write the next one as a complete file at the new path; leave earlier
versions as they are.
Write only that file, in the folder the message names; never edit, create or delete anything else, never commit or
push, and don't run anything. "summary": what it shows and what to click, in two or three sentences.
""" + _ROUND_RULES
RISK_FALLBACK = """You are the risk reviewer for this repository. Before a medium or large group of work is built, Ore
(a meeting assistant) asks you what could go wrong. Read CLAUDE.md, the project's docs and the code the group touches
(models, migrations, APIs, permissions, jobs, configuration), then list only real risks: data (migrations, data loss,
changes that can't be undone), security and privacy, breaking changes for users or other systems, operations
(performance, downtime, cost). Each has a title, a detail (what could go wrong, for whom), a severity (low, medium,
high) and a mitigation (how the build should handle it). needs_acceptance is true only when the user must decide before
building (data loss, a change that can't be undone, a breaking change, a security trade-off). An empty list is fine.
""" + _READ_ONLY + _ROUND_RULES
TESTS_FALLBACK = """You are the test planner for this repository. Before a group of work is built, Ore (a meeting
assistant) asks you how we'll know it works; the plan goes into the build instructions. Read CLAUDE.md, the project's
docs, the existing tests (folders, frameworks, fixtures) and the code the group touches. Cover every acceptance
criterion (or what the items ask for): name the automated tests to add or change in this repository's own test setup
(file, what each checks, unit / integration / end-to-end), the edge cases that matter, and a few manual checks only for
what tests can't see. Keep it proportionate. "summary" is one line, "plan" Markdown.
""" + _READ_ONLY + _ROUND_RULES
ROUND_FALLBACKS = {"designer": DESIGNER_FALLBACK, "risk": RISK_FALLBACK, "tests": TESTS_FALLBACK}
SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
QUERY_TIMEOUT = 20                         # per gh call; Ore gives the whole query about 45 s
RECENT_DAYS = 14                           # merged / closed ADW PRs this recent are listed too
ADW_BRANCH = re.compile(r"(?:^|[-/])issue-(\d+)-adw-(\d{14}-[0-9a-f]{12}|[0-9a-f]{8})(?:-|$)")
ADW_BODY = re.compile(r"ADW ID:\s*`?([0-9A-Za-z][0-9A-Za-z-]{6,40})`?")
CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)
PR_FIELDS = ("number,title,url,headRefName,body,closingIssuesReferences,statusCheckRollup,reviewDecision,state,"
             "mergedAt,closedAt,mergeable")


class QueryError(RuntimeError):
    """A query that can't be answered; the message is shown in Ore."""


def _gh(*args: str) -> str:
    from adw_modules.github import get_github_env
    env = {**os.environ, **(get_github_env() or {})}
    try:
        proc = subprocess.run(["gh", *args], cwd=REPO_ROOT, env=env, capture_output=True, text=True,
                              timeout=QUERY_TIMEOUT)
    except FileNotFoundError:
        raise QueryError(f"The GitHub CLI (gh) isn't installed on {socket.gethostname()}, or isn't on PATH")
    except subprocess.TimeoutExpired:
        raise QueryError(f"gh {args[0]} {args[1] if len(args) > 1 else ''} took longer than {QUERY_TIMEOUT}s")
    if proc.returncode != 0:
        raise QueryError(f"gh {' '.join(args[:2])} failed: {(proc.stderr or proc.stdout).strip()[-300:]}")
    return proc.stdout


def _repo() -> str:
    try:
        return extract_repo_path(get_repo_url(str(REPO_ROOT)))
    except Exception as e:  # noqa: BLE001
        raise QueryError(f"Can't tell this repository's GitHub remote: {e}")


def adw_pr_ids(pr: dict) -> tuple[int | None, str | None]:
    """(issue, adw_id) when the PR was made by an ADW (its branch is <type>-issue-<n>-adw-<id>-..., or its body
    names the ADW ID), else (None, None)."""
    m = ADW_BRANCH.search(pr.get("headRefName") or "")
    if m:
        return int(m.group(1)), m.group(2)
    b = ADW_BODY.search(pr.get("body") or "")
    if b:
        return None, b.group(1)
    return None, None


def check_state(rollup) -> str:
    """statusCheckRollup -> passing | failing | pending | none."""
    if not rollup:
        return "none"
    states = []
    for c in rollup:
        if not isinstance(c, dict):
            continue
        if c.get("__typename") == "StatusContext" or ("state" in c and "conclusion" not in c):
            s = str(c.get("state") or "").upper()            # SUCCESS FAILURE ERROR PENDING EXPECTED
            states.append("failing" if s in ("FAILURE", "ERROR") else "pending" if s in ("PENDING", "EXPECTED")
                          else "passing")
            continue
        status_ = str(c.get("status") or "").upper()
        conclusion = str(c.get("conclusion") or "").upper()
        if status_ and status_ != "COMPLETED":
            states.append("pending")
        elif conclusion in ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE", "STALE"):
            states.append("failing")
        elif conclusion in ("SUCCESS", "SKIPPED", "NEUTRAL"):
            states.append("passing")
        else:
            states.append("pending")
    if not states:
        return "none"
    return "failing" if "failing" in states else "pending" if "pending" in states else "passing"


def review_state(decision) -> str:
    return {"APPROVED": "approved", "REVIEW_REQUIRED": "requested",
            "CHANGES_REQUESTED": "changes"}.get(str(decision or "").upper(), "none")


def normalise_pr(pr: dict) -> dict:
    """One gh PR (gh pr list --json PR_FIELDS) in the prs query's shape."""
    issue, adw_id = adw_pr_ids(pr)
    closing = [r.get("number") for r in pr.get("closingIssuesReferences") or [] if isinstance(r, dict)]
    if closing and closing[0]:
        issue = int(closing[0])
    elif issue is None:
        m = CLOSES.search(pr.get("body") or "")
        issue = int(m.group(1)) if m else None
    out = {"number": pr.get("number"), "title": pr.get("title") or "", "url": pr.get("url") or "",
           "branch": pr.get("headRefName") or "", "checks": check_state(pr.get("statusCheckRollup")),
           "review": review_state(pr.get("reviewDecision")), "state": str(pr.get("state") or "open").lower()}
    if issue:
        out["issue"] = issue
    if adw_id:
        out["adw_id"] = adw_id
    if pr.get("mergedAt"):
        out["merged_at"] = pr["mergedAt"]
    if pr.get("closedAt") and out["state"] == "closed":
        out["closed_at"] = pr["closedAt"]
    mergeable = str(pr.get("mergeable") or "").upper()
    if out["state"] == "open" and mergeable in ("MERGEABLE", "CONFLICTING"):
        out["mergeable"] = mergeable == "MERGEABLE"
    return out


def query_prs() -> dict:
    """This repo's ADW pull requests: the open ones, and those merged or closed in the last RECENT_DAYS days."""
    repo = _repo()
    since = datetime.fromtimestamp(time.time() - RECENT_DAYS * 86400).strftime("%Y-%m-%d")
    open_ = json.loads(_gh("pr", "list", "-R", repo, "--state", "open", "--limit", "100", "--json", PR_FIELDS) or "[]")
    recent = json.loads(_gh("pr", "list", "-R", repo, "--state", "closed", "--limit", "100", "--search",
                            f"closed:>={since}", "--json", PR_FIELDS) or "[]")
    out, seen = [], set()
    for pr in [*open_, *recent]:
        if pr.get("number") in seen or adw_pr_ids(pr) == (None, None):
            continue
        seen.add(pr.get("number"))
        out.append(normalise_pr(pr))
    return {"prs": out}


def merge_method() -> str:
    """The repository's allowed merge method: squash when allowed, else merge, else rebase."""
    try:
        allowed = json.loads(_gh("repo", "view", _repo(), "--json",
                                 "squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed"))
    except (QueryError, ValueError):
        return "squash"
    for method, key in (("squash", "squashMergeAllowed"), ("merge", "mergeCommitAllowed"),
                        ("rebase", "rebaseMergeAllowed")):
        if allowed.get(key):
            return method
    raise QueryError("This repository allows no merge method (squash, merge or rebase)")


def query_merge(args: list[str]) -> dict:
    """Merge ADW pull request <number> (open ones only) with the repo's method, deleting its branch on GitHub. The
    workflow's worktree, if still on this machine, is left alone."""
    if not args or not args[0].lstrip("#").isdigit():
        raise QueryError("merge needs a pull request number")
    number = args[0].lstrip("#")
    repo = _repo()
    try:
        pr = json.loads(_gh("pr", "view", number, "-R", repo, "--json", "number,url,state,headRefName,body"))
    except ValueError:
        raise QueryError(f"gh returned no details for PR #{number}")
    if adw_pr_ids(pr) == (None, None):
        raise QueryError(f"PR #{number} wasn't made by an ADW; merge it on GitHub")
    if str(pr.get("state")).upper() != "OPEN":
        raise QueryError(f"PR #{number} is {str(pr.get('state')).lower()}, not open")
    method = merge_method()
    try:
        _gh("pr", "merge", number, "-R", repo, f"--{method}", "--delete-branch")
    except QueryError as e:
        # The merge can succeed while deleting the local branch fails (e.g. a worktree still has it checked out):
        # look again before reporting a failure.
        try:
            state = json.loads(_gh("pr", "view", number, "-R", repo, "--json", "state")).get("state")
        except (QueryError, ValueError):
            state = None
        if str(state).upper() != "MERGED":
            raise e
        branch = pr.get("headRefName")
        if branch:
            subprocess.run(["git", "push", "origin", "--delete", branch], cwd=REPO_ROOT, capture_output=True,
                           text=True, timeout=QUERY_TIMEOUT)
    return {"merged": True, "number": int(number), "url": pr.get("url") or "", "method": method}


def query_ask(args: list[str]) -> dict:
    """`ask <question> [<session id> [<file>...]]`: a read-only Claude Code session in the repository's root, so
    CLAUDE.md, the project's docs and .claude/ (and .mcp.json) are there to find the answer fast. With a session id it
    continues that conversation (a follow-up question). Files are what the asker attached (Ore copies them to
    .ore/questions/ in the repository; for Office documents it passes their text): the session reads them, still
    read-only. Returns {"answer", "session_id", "cost_usd"}."""
    question = (args[0] if args else "").strip()
    if not question:
        raise QueryError("ask needs a question")
    session = args[1].strip() if len(args) > 1 else ""
    files = [f for f in args[2:] if f.strip()]
    if files:
        question += ("\n\nAttached by the asker (read them with the Read tool; it reads images and PDFs directly, and "
                     "Office documents come as .txt files with their text):\n" + "\n".join(f"- {f}" for f in files))
    claude = os.getenv("CLAUDE_CODE_PATH", "claude")
    cmd = [claude, "-p", question, "--output-format", "json", "--model", ASK_MODEL,
           "--append-system-prompt", ASK_RULES, "--permission-mode", "plan",
           "--allowedTools", "Read", "Glob", "Grep", "--disallowedTools", "Edit", "Write", "NotebookEdit"]
    if session:
        cmd += ["--resume", session]
    for folder in sorted({str(Path(f).parent) for f in files} - {str(REPO_ROOT)}):
        if not folder.startswith(str(REPO_ROOT) + os.sep):
            cmd += ["--add-dir", folder]        # attachments outside the repository may be read too
    mcp = REPO_ROOT / ".mcp.json"
    if mcp.exists():
        cmd += ["--mcp-config", str(mcp)]
    try:
        proc = subprocess.run(cmd, cwd=REPO_ROOT, env=get_safe_subprocess_env(), capture_output=True, text=True,
                              timeout=ASK_TIMEOUT)
    except FileNotFoundError:
        raise QueryError(f"Claude Code (`claude`) isn't installed on {socket.gethostname()}, or isn't on PATH")
    except subprocess.TimeoutExpired:
        raise QueryError(f"Claude didn't answer within {ASK_TIMEOUT // 60} minutes")
    try:
        out = json.loads(proc.stdout or "{}")
    except ValueError:
        out = {}
    problem = auth_problem(out, proc.stderr) if (proc.returncode or out.get("is_error")) else None
    if problem:
        raise QueryError(problem)
    answer = str(out.get("result") or "").strip()
    if proc.returncode or out.get("is_error") or not answer:
        raise QueryError("Claude Code didn't answer: " + (proc.stderr.strip()[-300:] or answer or "no reply"))
    return {"answer": answer, "session_id": out.get("session_id") or session, "cost_usd": out.get("total_cost_usd")}


def query_items(args: list[str]) -> dict:
    """`items <request.json>`: Ore's action items for this workspace, read in a read-only Claude Code session in the
    repository's root (CLAUDE.md, the project's docs and .claude/ are there), so they come back in this codebase's own
    terms. The request (in .ore/items/<id>/, beside the transcript) holds the rules (added to the system prompt), the
    prompt, the JSON schema of the answer and a time limit. Returns {"items": <the structured output>, "cost_usd"}."""
    if not args or not args[0].strip():
        raise QueryError("items needs the request file")
    inbox = (REPO_ROOT / ".ore" / "items").resolve()
    path = Path(args[0]).expanduser().resolve()
    if inbox not in path.parents:
        raise QueryError("The request must be in this repository's .ore/items/")
    try:
        try:
            req = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise QueryError(f"Couldn't read the request: {e}")
        prompt, schema = str(req.get("prompt") or "").strip(), req.get("schema")
        if not prompt or not isinstance(schema, dict):
            raise QueryError("The request needs a prompt and a schema")
        try:
            minutes = min(30.0, max(1.0, float(req.get("minutes") or ITEMS_MINUTES)))
        except (TypeError, ValueError):
            minutes = ITEMS_MINUTES
        claude = os.getenv("CLAUDE_CODE_PATH", "claude")
        cmd = [claude, "-p", "--output-format", "json", "--model", ITEMS_MODEL, "--json-schema", json.dumps(schema),
               "--append-system-prompt", str(req.get("rules") or ""), "--permission-mode", "plan",
               "--no-session-persistence", "--allowedTools", "Read", "Glob", "Grep", *ITEMS_HISTORY,
               "--disallowedTools", "Edit", "Write", "NotebookEdit"]
        mcp = REPO_ROOT / ".mcp.json"
        if mcp.exists():
            cmd += ["--mcp-config", str(mcp)]
        try:
            # The prompt goes in on stdin: a long meeting's items don't fit a command line.
            proc = subprocess.run(cmd, input=prompt, cwd=REPO_ROOT, env=get_safe_subprocess_env(), capture_output=True,
                                  text=True, timeout=minutes * 60)
        except FileNotFoundError:
            raise QueryError(f"Claude Code (`claude`) isn't installed on {socket.gethostname()}, or isn't on PATH")
        except subprocess.TimeoutExpired:
            raise QueryError(f"Claude didn't read the items within {minutes:g} minutes")
    finally:
        if path.parent != inbox:
            shutil.rmtree(path.parent, ignore_errors=True)
    try:
        out = json.loads(proc.stdout or "{}")
    except ValueError:
        out = {}
    problem = auth_problem(out, proc.stderr) if (proc.returncode or out.get("is_error")) else None
    if problem:
        raise QueryError(problem)
    items = out.get("structured_output")
    if proc.returncode or out.get("is_error") or not isinstance(items, dict):
        raise QueryError("Claude Code didn't return the items: " + (proc.stderr.strip()[-300:]
                                                                    or str(out.get("result") or "no reply")[-300:]))
    return {"items": items, "cost_usd": out.get("total_cost_usd")}


def specialist_prompt(name: str, fallbacks: dict | None = None) -> str:
    """The specialist's prompt: adws/specialists/<name>.md in this repository, or the built-in one (backlog, triage,
    planner, scoper; designer, risk, tests for the question round with ROUND_FALLBACKS)."""
    fallbacks = SPECIALIST_FALLBACKS if fallbacks is None else fallbacks
    try:
        text = (REPO_ROOT / "adws" / "specialists" / f"{name}.md").read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if text:
        return text
    if name in fallbacks:
        return fallbacks[name]
    raise QueryError(f"This repository has no specialist {name!r} (adws/specialists/{name}.md)")


def _consult_files(req: dict, folder: Path) -> tuple[list[dict], list[str]]:
    """The files a consult request points at: (the user's attachments [{name, path, text_path}], the paths attached
    earlier in the items' conversations). Ore copies them into the request's folder (.ore/pm/<run id>/files/); any
    path outside it is refused, so a request can't point the session at other files."""
    files = (folder / "files").resolve()

    def inside(raw) -> str:
        p = Path(str(raw)).expanduser()
        p = (p if p.is_absolute() else REPO_ROOT / p).resolve()
        if files not in p.parents:
            raise QueryError("Attached files must be in the request's files/ folder (.ore/pm/<run id>/files/)")
        return str(p)

    message = req.get("message") if isinstance(req.get("message"), dict) else {}
    attached = []
    for a in message.get("attachments") or []:
        a = a if isinstance(a, dict) else {"path": a}
        if not a.get("path"):
            continue
        attached.append({"name": str(a.get("name") or Path(str(a["path"])).name), "path": inside(a["path"]),
                         "text_path": inside(a["text_path"]) if a.get("text_path") else None})
    earlier = []
    card = req.get("card") if isinstance(req.get("card"), dict) else {}
    for it in [*(req.get("items") or []), *(card.get("items") or [])]:
        for m in (it.get("conversation") or []) if isinstance(it, dict) else []:
            for a in (m.get("attachments") or []) if isinstance(m, dict) else []:
                raw = a.get("path") if isinstance(a, dict) else a
                if raw:
                    earlier.append(inside(raw))
    return attached, list(dict.fromkeys(earlier))


def consult_message(req: dict, attached: list[dict], earlier: list[str]) -> str:
    """The session's message: the user's message and attached files first (reply runs), then the request as JSON."""
    parts = []
    message = req.get("message") if isinstance(req.get("message"), dict) else {}
    said = str(message.get("text") or "").strip()
    if said or attached:
        parts.append("The user wrote to you on a card in Ore:\n\n" + (said or "(no text, only files)"))
    if attached:
        parts.append("Attached by the user (read each one with the Read tool; it reads images and PDFs directly, and "
                     "an Office document's text is in the .txt file named beside it):\n" + "\n".join(
                         f"- {a['name']}: {a['path']}" + (f" (text: {a['text_path']})" if a["text_path"] else "")
                         for a in attached))
    if earlier:
        parts.append("Files attached earlier in the items' conversations (read them with Read when they matter):\n"
                     + "\n".join(f"- {p}" for p in earlier))
    request = {k: req.get(k) for k in ("workspace", "goals", "items")}
    for k in ("workspaces", "run", "card"):           # triage: workspaces; version 3: run (doctor), card (the others)
        if req.get(k):
            request[k] = req[k]
    parts.append("Ore's request (answer it in the given schema):\n\n" + json.dumps(request, ensure_ascii=False, indent=1))
    return "\n\n".join(parts)


def query_consult(args: list[str]) -> dict:
    """`consult <specialist> <request.json>`: Ore asks a specialist (adws/specialists/<name>.md: backlog, triage,
    planner, scoper for Ore's project manager; doctor, pr_reviewer, merge_planner, closer after the build) for a
    structured answer. A read-only Claude Code session in the repository's root (Read, Glob, Grep, read-only git log /
    show / diff and gh pr list / view / diff / checks; plan mode) gets the specialist's prompt as its system prompt and
    the request (the user's message and attached files, if any, then workspace, goals, items and, when present,
    workspaces (triage), run (doctor) and card (pr_reviewer, merge_planner, closer)) as the message, and answers with
    the request's schema. With
    the request's `session_id` it continues that session (`--resume`, same flags); a session that's gone starts over.
    Attached files must be in the request's files/ folder. No cost cap. The request's folder (.ore/pm/<run id>/) is
    removed afterwards. Returns {"result": <the structured output>, "session_id", "cost_usd"}."""
    name = (args[0] if args else "").strip()
    if not SPECIALIST_NAME.fullmatch(name):
        raise QueryError("consult needs a specialist name (lower-case letters, digits, - and _)")
    if len(args) < 2 or not args[1].strip():
        raise QueryError("consult needs the request file")
    inbox = (REPO_ROOT / ".ore" / "pm").resolve()
    path = Path(args[1]).expanduser().resolve()
    if inbox not in path.parents:
        raise QueryError("The request must be in this repository's .ore/pm/")
    try:
        prompt = specialist_prompt(name)
        try:
            req = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise QueryError(f"Couldn't read the request: {e}")
        schema = req.get("schema") if isinstance(req, dict) else None
        if not isinstance(schema, dict):
            raise QueryError("The request needs a schema")
        try:
            minutes = min(60.0, max(1.0, float(req.get("minutes") or CONSULT_MINUTES)))
        except (TypeError, ValueError):
            minutes = CONSULT_MINUTES
        session = str(req.get("session_id") or "").strip()
        if session and not SESSION_ID.fullmatch(session):
            raise QueryError("The request's session_id isn't a Claude Code session id")
        attached, earlier = _consult_files(req, path.parent)
        text = consult_message(req, attached, earlier)
        claude = os.getenv("CLAUDE_CODE_PATH", "claude")
        cmd = [claude, "-p", "--output-format", "json", "--model", CONSULT_MODEL, "--json-schema", json.dumps(schema),
               "--append-system-prompt", prompt, "--permission-mode", "plan",
               "--allowedTools", "Read", "Glob", "Grep", *CONSULT_TOOLS,
               "--disallowedTools", "Edit", "Write", "NotebookEdit"]
        mcp = REPO_ROOT / ".mcp.json"
        if mcp.exists():
            cmd += ["--mcp-config", str(mcp)]

        def call(resume: str):
            # The request goes in on stdin: a long backlog doesn't fit a command line.
            return subprocess.run(cmd + (["--resume", resume] if resume else []), input=text, cwd=REPO_ROOT,
                                  env=get_safe_subprocess_env(), capture_output=True, text=True, timeout=minutes * 60)
        try:
            proc = call(session)
            if session and proc.returncode and "no conversation found" in f"{proc.stderr}{proc.stdout}".lower():
                session = ""                         # the session is gone (another machine, cleaned up): start over
                proc = call("")
        except FileNotFoundError:
            raise QueryError(f"Claude Code (`claude`) isn't installed on {socket.gethostname()}, or isn't on PATH")
        except subprocess.TimeoutExpired:
            raise QueryError(f"The {name} specialist didn't answer within {minutes:g} minutes")
    finally:
        if path.parent != inbox:
            shutil.rmtree(path.parent, ignore_errors=True)
    try:
        out = json.loads(proc.stdout or "{}")
    except ValueError:
        out = {}
    problem = auth_problem(out, proc.stderr) if (proc.returncode or out.get("is_error")) else None
    if problem:
        raise QueryError(problem)
    result = out.get("structured_output")
    if proc.returncode or out.get("is_error") or not isinstance(result, dict):
        raise QueryError(f"The {name} specialist didn't answer: " + (proc.stderr.strip()[-300:]
                                                                     or str(out.get("result") or "no reply")[-300:]))
    return {"result": result, "session_id": out.get("session_id") or session, "cost_usd": out.get("total_cost_usd")}


REVERT_GIT_TIMEOUT = 120                   # per git call of the revert query


def _git(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    from adw_modules.github import get_github_env
    env = {**os.environ, **(get_github_env() or {})}
    try:
        proc = subprocess.run(["git", *args], cwd=cwd or REPO_ROOT, env=env, capture_output=True, text=True,
                              timeout=REVERT_GIT_TIMEOUT)
    except FileNotFoundError:
        raise QueryError(f"git isn't installed on {socket.gethostname()}, or isn't on PATH")
    except subprocess.TimeoutExpired:
        raise QueryError(f"git {args[0]} took longer than {REVERT_GIT_TIMEOUT}s")
    if check and proc.returncode != 0:
        raise QueryError(f"git {' '.join(args[:2])} failed: {(proc.stderr or proc.stdout).strip()[-300:]}")
    return proc


def query_revert(args: list[str]) -> dict:
    """`revert <pr number>`: open a pull request that reverts merged PR <number>. Unlike the other queries this one
    writes: in a temporary worktree (trees/revert-pr-<n>) on a new branch revert-<n>-<short sha> from the PR's base
    branch, `git revert` of its merge commit (`-m 1` for a merge commit with two parents, plain for a squash or rebase
    merge), pushed, then `gh pr create`. The main checkout's working tree is never touched; the worktree and the local
    branch are removed afterwards, and on a failure the pushed branch too. An open revert PR from an earlier try is
    answered as it is. Refuses PRs that aren't merged and reverts that conflict. Returns {"number", "url"}."""
    if not args or not args[0].lstrip("#").isdigit():
        raise QueryError("revert needs a pull request number")
    number = args[0].lstrip("#")
    repo = _repo()
    try:
        pr = json.loads(_gh("pr", "view", number, "-R", repo, "--json",
                            "number,url,state,mergeCommit,title,baseRefName"))
    except ValueError:
        raise QueryError(f"gh returned no details for PR #{number}")
    state = str(pr.get("state") or "").upper()
    if state != "MERGED":
        raise QueryError(f"PR #{number} is {state.lower() or 'not merged'}, not merged: only a merged pull request "
                         "can be reverted")
    sha = str((pr.get("mergeCommit") or {}).get("oid") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{7,64}", sha):
        raise QueryError(f"GitHub didn't say which commit merged PR #{number}")
    base = str(pr.get("baseRefName") or "").strip()
    if not base:
        try:
            base = json.loads(_gh("repo", "view", repo, "--json", "defaultBranchRef"))["defaultBranchRef"]["name"]
        except (ValueError, KeyError, TypeError):
            raise QueryError("Can't tell which branch to open the revert pull request against")
    branch = f"revert-{number}-{sha[:7]}"
    try:
        existing = json.loads(_gh("pr", "list", "-R", repo, "--head", branch, "--state", "open", "--json",
                                  "number,url") or "[]")
    except ValueError:
        existing = []
    if existing:                                 # an earlier try opened it already
        return {"number": int(existing[0]["number"]), "url": existing[0].get("url") or ""}
    title = str(pr.get("title") or f"PR #{number}")
    path = REPO_ROOT / "trees" / f"revert-pr-{number}"
    pushed = done = False

    def drop_worktree() -> None:
        if path.exists():
            _git("worktree", "remove", "--force", str(path), check=False)
            shutil.rmtree(path, ignore_errors=True)
        _git("worktree", "prune", check=False)

    try:
        drop_worktree()                          # left over from an interrupted try
        _git("fetch", "-q", "origin", base)
        _git("worktree", "add", "-q", "-B", branch, str(path), f"origin/{base}")
        parents = _git("rev-list", "--parents", "-n", "1", sha, cwd=path).stdout.split()[1:]
        if not parents:
            raise QueryError(f"The commit that merged PR #{number} ({sha[:7]}) has no parent to go back to")
        proc = _git("revert", "--no-edit", *(["-m", "1"] if len(parents) > 1 else []), sha, cwd=path, check=False)
        if proc.returncode != 0:
            conflicted = _git("diff", "--name-only", "--diff-filter=U", cwd=path, check=False).stdout.split()
            _git("revert", "--abort", cwd=path, check=False)
            if conflicted:
                files = ", ".join(conflicted[:5]) + (f" and {len(conflicted) - 5} more" if len(conflicted) > 5 else "")
                raise QueryError(f"PR #{number} can't be reverted automatically: later changes on {base} conflict "
                                 f"with it in {files}. Revert it by hand.")
            raise QueryError(f"git revert failed: {(proc.stderr or proc.stdout).strip()[-300:]}")
        _git("push", "-q", "-u", "origin", branch, cwd=path)
        pushed = True
        body = (f"Reverts #{number}" + (f" ({pr['url']})" if pr.get("url") else "") + f": undoes its merge commit "
                f"{sha[:7]} on {base}.\n\nOpened from Ore, because the work was sent back for review.")
        out = _gh("pr", "create", "-R", repo, "--base", base, "--head", branch, "--title", f'Revert "{title}"',
                  "--body", body)
        m = re.search(r"https://\S+/pull/(\d+)", out)
        if not m:
            raise QueryError(f"gh pr create didn't give the new pull request's link: {out.strip()[-200:]}")
        done = True
        return {"number": int(m.group(1)), "url": m.group(0)}
    finally:
        drop_worktree()
        _git("branch", "-D", branch, check=False)
        if pushed and not done:
            _git("push", "-q", "origin", "--delete", branch, check=False)


def query_machine() -> dict:
    if not resources.enabled():
        raise QueryError("This codebase doesn't use the machine-wide resource registry (ADW_RESOURCES=static)")
    return resources.machine_view()


def run_query(name: str, args: list[str]) -> int:
    """Answer one Ore query on stdout (one line). Returns the exit code."""
    try:
        if name == "machine":
            data = query_machine()
        elif name == "prs":
            data = query_prs()
        elif name == "merge":
            data = query_merge(args)
        elif name == "ask":
            data = query_ask(args)
        elif name == "items":
            data = query_items(args)
        elif name == "consult":
            data = query_consult(args)
        elif name == "revert":
            data = query_revert(args)
        elif name == "merge_run":
            raise QueryError("merge_run isn't a query: start this script with --ore-merge <n>")
        else:
            raise QueryError(f"Unknown query {name!r}; this script answers {', '.join(QUERIES)}")
    except Exception as e:  # noqa: BLE001 - every problem becomes an error line
        emit({"type": "error", "message": str(e) or type(e).__name__})
        return 1
    emit({"type": "answer", "query": name, "data": data})
    return 0


def query_request(argv: list[str]) -> tuple[str, list[str]] | None:
    """(name, args) when Ore asked a query: `--ore-query <name> [args...]` anywhere in argv (Ore may put the
    workspace's own arguments first; ORE_QUERY names the query when argv doesn't). Else None."""
    if "--ore-query" not in argv:
        return None
    rest = argv[argv.index("--ore-query") + 1:]
    return (rest[0] if rest else os.getenv("ORE_QUERY", "")), rest[1:]


def merge_run(number: str, run_checks: bool = True) -> None:
    """Ore's Merge button: merge PR <number>, resolving conflicts with main first (adw_modules/pr_merge.py), as a
    run whose one part shows the steps."""
    from adw_modules import pr_merge
    from adw_modules.github import get_github_env
    nodes = {k: {"key": k, "label": label, "status": "pending", "note": ""} for k, label in pr_merge.STEPS}
    lines: list[dict] = []
    state = {"status": "running", "message": "Starting"}
    holder: dict = {}

    def send() -> None:
        pr = holder["m"].pr if "m" in holder else {}
        label = f"PR #{number}" + (f" · {pr['title']}" if pr.get("title") else "")
        links = [[f"Pull request #{number}", pr["url"]]] if pr.get("url") else []
        part = {"key": f"merge-{number}", "label": label, "status": state["status"], "message": state["message"],
                "route": {"type": "merge", "workflow": "Merge"}, "steps": list(nodes.values()), "log": lines[-10:],
                "links": links}
        emit({"type": "status", "message": state["message"], "progress": None, "parts": [part],
              "queries": list(QUERIES)})

    def on_step(key: str, status_: str, note: str = "") -> None:
        node = nodes.setdefault(key, {"key": key, "label": key, "status": "pending", "note": ""})
        if status_ == "running" and not node.get("started"):
            node["started"] = now_iso()
        if status_ in ("done", "failed", "skipped"):
            node["ended"] = now_iso()
        node["status"] = status_
        node["note"] = (note or node["note"]) if status_ == "running" else note
        node["note"] = node["note"][:300]
        if status_ in ("running", "failed") or note:
            state["message"] = f"{node['label']}: {note}" if note else node["label"]
        send()

    def log_line(text: str) -> None:
        lines.append({"time": now_iso(), "text": text[:400]})
        print(text, file=sys.stderr, flush=True)

    env = {k: v for k, v in os.environ.items() if v != ""}      # an empty ANTHROPIC_API_KEY= mustn't hide the login
    env.update(get_github_env() or {})
    holder["m"] = m = pr_merge.Merge(number, REPO_ROOT, on_step, log_line, env=env, run_checks=run_checks)
    send()
    try:
        out = m.run()
    except pr_merge.MergeError as e:
        state.update(status="failed", message=str(e)[:300])
        send()
        error(str(e))
        return
    state.update(status="done", message="Merged already" if out["already"] else f"Merged ({out['method']})")
    send()
    if out["already"]:
        summary = f"PR #{number} was merged already."
    elif out["resolved"]:
        n = len(out["resolved"])
        summary = (f"Merged PR #{number} ({out['method']}) after resolving conflicts with main in {n} "
                   f"file{'s' if n != 1 else ''}.\n\n{out['notes']}")
    else:
        summary = (f"Merged PR #{number} ({out['method']})" + (", after merging main into it" if out["updated"] else "")
                   + ".")
    pulled = out.get("pulled") or {}
    if pulled.get("skipped"):
        summary += f"\n\n{pulled['skipped']}."
    elif pulled.get("adws"):
        summary += (f"\n\nThe main checkout is now on {pulled['to']}, and the merge changed the ADW scripts: restart "
                    "Ore so the trigger uses them.")
    result(summary[:20000], links=[[f"Pull request #{number}", out["url"]]] if out["url"] else [], data=out)


def merge_request(argv: list[str]) -> str | None:
    """The PR number when Ore asked for a merge run: `--ore-merge <n>` anywhere in argv."""
    if "--ore-merge" not in argv:
        return None
    rest = argv[argv.index("--ore-merge") + 1:]
    if not rest or not rest[0].lstrip("#").isdigit():
        error("--ore-merge needs a pull request number")
    return rest[0].lstrip("#")


def main() -> None:
    global MODEL, MODEL_SET
    args = sys.argv[1:]
    query = query_request(args)                      # Ore's queries come before anything else
    if query:
        sys.exit(run_query(*query))
    number = merge_request(args)
    if number:
        merge_run(number, run_checks="--no-checks" not in args)
        return
    dry_run, simulate_run = "--dry-run" in args, "--simulate" in args
    args = [a for a in args if a not in ("--dry-run", "--simulate")]
    args, follow = follow_up_arg(args)
    args, replan_req = follow_up_arg(args, "--ore-replan")
    for flag in ("--model", "--model-set"):          # e.g. extra arguments on the Ore workspace
        if flag in args:
            i = args.index(flag)
            if flag == "--model":
                MODEL = args[i + 1]
            else:
                MODEL_SET = args[i + 1]
            del args[i:i + 2]
    if len(args) == 2 and args[0] == "--cleanup":
        clean(Path(args[1]), cleanup_options())
        return
    if len(args) == 2 and args[0] == "--resume":
        run = Run(Path(args[1]))
        if not run.s:
            error(f"No saved run in {args[1]}")
        MODEL, MODEL_SET = run.s.get("model", MODEL), run.s.get("model_set", MODEL_SET)
        if replan_req is not None or run.s.get("replan"):     # back to planning (or finishing one cut short)
            if replan_req == {}:
                error("Ore's request to plan again couldn't be read")
                return
            replan(run, replan_req or run.s["replan"])
        elif follow is not None:                       # Follow up on a finished workflow: only that one runs
            if not follow_up(run, follow) and run.s.get("phase") == "done":
                error("The follow-up couldn't start (see the reply on the workflow)")
                return
        elif retry_failed(run):
            report(run, "Running the failed workflows again")
    elif len(args) == 1 or (simulate_run and not args):
        run = Run.new(Path(args[0]) if args else None, dry_run and not simulate_run, simulate=simulate_run)
    else:
        error(__doc__)
        return
    use_ore_input()
    _while_waiting[:] = [lambda: handle_messages(run)]
    checkpoint("--resume", str(run.dir))
    run.s["trigger_pid"] = os.getpid()       # so a cleanup can stop this process
    if run.s.get("simulate"):
        for g in run.s.get("groups") or []:
            if g.get("status") == "running" and g.get("adw_id"):
                sim_lease(run, g)            # this process holds them now
    run.save()
    announce_cleanup(run)
    try:
        if run.s.get("simulate"):
            log("Simulated run: no Claude, no GitHub; workflows are simulated (resources are leased for real)")
        elif run.s["phase"] != "done":
            log(f"Claude Code is signed in with {check_claude_auth()}")
            _auth_checked[0] = time.time()
        while run.s["phase"] != "done":
            phase = run.s["phase"]
            if phase == "clarify":
                clarify(run)
            elif phase == "review":
                review(run)
            elif phase == "checks":
                checks(run)
            elif phase == "issues":
                write_issues(run)
            elif phase == "workflows":
                workflows(run)
    except ClaudeAuthError as e:
        error(str(e))
    except Exception as e:
        log(f"{type(e).__name__}: {e}")
        error(f"{e} (the run is saved; Resume continues from here)")


if __name__ == "__main__":
    main()
