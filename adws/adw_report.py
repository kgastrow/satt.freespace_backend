#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic"]
# ///

"""
ADW progress reporting for agents: the orchestrator of adw_orchestrated_sdlc_iso.py calls this through Bash.

Usage (ADW_ID and ADW_ISSUE_NUMBER come from the environment the workflow sets, or --adw-id / --issue):
  uv run adws/adw_report.py step <key> <running|done|failed|skipped> [--label L] [--parent P] [--note N]
  uv run adws/adw_report.py plan --package api="Orders API" --package ui="Orders page:api" [--note N]
                                 (id=name[:after,after]; the work packages, in order, so pending ones show)
  uv run adws/adw_report.py comment "<text>" | --file <markdown file> [--agent orchestrator]
  uv run adws/adw_report.py pr --title "<title>" --body-file <file>
  uv run adws/adw_report.py reply <message-id> "<text>"
  uv run adws/adw_report.py ask "<question>" [--options "a,b"] | ask --wait <n>
  uv run adws/adw_report.py wait [--timeout-min 55]
  uv run adws/adw_report.py image "<label>" <png file | https url>
  uv run adws/adw_report.py check [--timeout-min 55]
  uv run adws/adw_report.py app
  uv run adws/adw_report.py result <pr_opened|failed|dropped> --summary "<1-3 sentences>" [--pr-url U] [--review-rounds N]
                                   [--reason R] [--blocker B ...] [--report-file <markdown file>] [--force]
  uv run adws/adw_report.py result --json '<object>'

- step: one event in agents/<adw_id>/steps.jsonl (adw_modules/steps.py), which Ore draws as the run's flow.
  Top-level keys: setup, plan, work, integrate, screens, review, docs, pr. Work packages: --parent work
  --label <name>. Running a step again after it failed adds an attempt (e.g. review rounds, full-suite runs).
- plan: records the packages under "work" and marks step "plan" done ("N packages").
- comment: an [ADW-AGENTS] comment on the issue (it also lands in agents/progress/issue-<n>.jsonl); --file posts
  a Markdown file (e.g. the plan).
- pr: pushes the worktree's branch, opens the pull request against main (or finds the open one), records step
  "pr", comments the link and prints the URL. Screenshots recorded with `image` are added to the body.
- reply: answers a user's message from Ore (agents/<adw_id>/outbox.jsonl; the Ore trigger relays it).
- ask: asks the user a question in Ore and blocks until the answer (printed), at most 55 minutes per call; the
  question stays open, so `ask --wait <n>` keeps waiting (only ADW_ASK_TIMEOUT_MIN makes it give up and decide).
  One question is open at a time per Ore run; others wait their turn.
- wait: after a pause message, blocks until a resume or amend message arrives (or a question: answer it with
  reply, then wait again). Returns after --timeout-min; run it again while still paused.
- image: uploads a screenshot (R2 when configured, else the repo's adw-screenshots branch; see
  adw_modules/image_upload.py), records it for Ore (agents/<adw_id>/images.jsonl) and prints its Markdown.
- check: the full check, once, when the work is done and committed (step "check"). In an Ore run the full suites
  run once for the whole batch: the Ore trigger merges the waiting workflows' branches onto origin/main, runs them
  and works out whose each failure is (adw_modules/batch_check.py); this asks for that check for HEAD and waits for
  this workflow's part (inbox "check_result"). Exit 0: green (failures already on main, or that couldn't be
  attributed, are listed for the PR); 1: failures to look at (the report file says which and why); 3: a merge
  conflict with another branch of the batch (checked on its own next: run it again); 4: still waiting after
  --timeout-min, run it again (same commit: it keeps waiting, nothing new is queued). Outside an Ore run, or when
  the batch check couldn't run, it runs `adw_run_suites.py full` on this branch instead.
- app: makes sure this worktree's app is running for the screenshots (backend answers, frontend listens) and
  restarts it by script when a server is down (adw_modules/env_setup.ensure_app). Exit 0: running (says whether it
  was restarted); 1: it couldn't be started (the reason and the end of the start log are printed). Agents never
  start or stop the dev servers themselves.
- result: the orchestrator's final result, checked against messages.RESULT_SCHEMA and written atomically to
  agents/<adw_id>/result.json. The workflow ends the session on it once no subagent or background command is
  running; reported while some still run, it is set aside and the orchestrator is told to wait for them.
  --force: give up now anyway, without waiting for them. --report-file: the orchestrator's report of the whole
  workflow (Markdown), kept as agents/<adw_id>/report.md for Ore and the merge workflow, and posted on the PR.
adw_modules/messages.py describes the files.

Never fails the caller for a reporting problem except `pr`, whose exit code says whether the PR exists, and
`result`, which refuses a result that doesn't fit the schema (exit 2, nothing written).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adw_modules import messages, steps  # noqa: E402

try:                                    # GITHUB_PAT etc. for comments and the PR, as the workflows load them
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

STATUSES = ("running", "done", "failed", "skipped")
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def adw_dir(adw_id: str) -> str:
    return os.path.dirname(steps.steps_path(adw_id))


def orchestrator_dir(adw_id: str) -> str:
    return os.path.join(adw_dir(adw_id), "orchestrator")


POLL_SECONDS = 2.0


def _issue(args) -> str | None:
    if args.issue:
        return str(args.issue)
    if os.environ.get("ADW_ISSUE_NUMBER"):
        return os.environ["ADW_ISSUE_NUMBER"]
    try:
        with open(os.path.join(os.path.dirname(steps.steps_path(args.adw_id)), "adw_state.json"), encoding="utf-8") as f:
            return json.load(f).get("issue_number")
    except (OSError, ValueError):
        return None


def cmd_step(args) -> int:
    if args.status not in STATUSES:
        print(f"status must be one of {', '.join(STATUSES)}", file=sys.stderr)
        return 2
    for value in (args.key, args.parent):
        if value is not None and not KEY.match(value):
            print(f"bad step key {value!r}: letters, digits, _ . - only", file=sys.stderr)
            return 2
    steps.record(args.adw_id, args.key, args.status, label=args.label, note=args.note or "", parent=args.parent)
    print(f"recorded {args.parent + '/' if args.parent else ''}{args.key}: {args.status}")
    return 0


def parse_package(spec: str) -> dict:
    """'api=Orders API:db,auth' -> {"id": "api", "name": "Orders API", "after": ["db", "auth"]}"""
    pid, _, rest = spec.partition("=")
    name, _, after = rest.rpartition(":") if ":" in rest else (rest, "", "")
    if after and (" " in after or not all(KEY.match(a) for a in after.split(",") if a)):
        name, after = rest, ""                      # a colon in the name, not a dependency list
    pid = pid.strip()
    if not KEY.match(pid):
        raise ValueError(f"bad package id {pid!r}")
    out = {"id": pid, "name": (name or pid).strip()}
    deps = [a.strip() for a in after.split(",") if a.strip()]
    if deps:
        out["after"] = deps
    return out


def cmd_plan(args) -> int:
    try:
        packages = [parse_package(p) for p in args.package]
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    steps.plan(args.adw_id, packages, key="work", label="Work")
    n = len(packages)
    steps.record(args.adw_id, "plan", "done", label="Plan",
                 note=args.note or f"{n} package{'s' if n != 1 else ''}")
    try:
        os.makedirs(orchestrator_dir(args.adw_id), exist_ok=True)
        with open(os.path.join(orchestrator_dir(args.adw_id), "plan.json"), "w", encoding="utf-8") as f:
            json.dump(packages, f, indent=1)
    except OSError:
        pass
    print(f"recorded plan: {', '.join(p['id'] for p in packages)}")
    return 0


def post_comment(adw_id: str, issue: str | None, text: str, agent: str = "orchestrator") -> bool:
    if not issue:
        print("no issue number (set ADW_ISSUE_NUMBER or --issue)", file=sys.stderr)
        return False
    from adw_modules.github import ADW_BOT_IDENTIFIER, make_issue_comment
    try:      # the format of workflow_ops.format_issue_message (not imported: it pulls in the whole agent stack)
        make_issue_comment(str(issue), f"{ADW_BOT_IDENTIFIER} {adw_id}_{agent}: {text}")
        return True
    except Exception as e:  # noqa: BLE001 - reporting must not stop the work
        print(f"comment not posted: {e}", file=sys.stderr)
        return False


def cmd_comment(args) -> int:
    text = args.text
    if args.file:
        try:
            with open(args.file, encoding="utf-8") as f:
                text = f.read().strip()
        except OSError as e:
            print(f"can't read {args.file}: {e}", file=sys.stderr)
            return 2
    if not (text or "").strip():
        print("nothing to post: give the text or --file", file=sys.stderr)
        return 2
    ok = post_comment(args.adw_id, _issue(args), text, args.agent)
    print("comment posted" if ok else "comment not posted (recorded locally if possible)")
    return 0


def _git(*a, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, timeout=120)


def cmd_pr(args) -> int:
    from adw_modules.git_ops import check_pr_exists_with_error, push_branch
    from adw_modules.github import extract_repo_path, get_repo_url, get_github_env

    adw_id, cwd = args.adw_id, os.getcwd()
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd).stdout.strip()
    if not branch or branch in ("HEAD", "main", "master"):
        print(f"refusing to open a PR from {branch or 'no branch'}", file=sys.stderr)
        return 2
    if _git("status", "--porcelain", cwd=cwd).stdout.strip():
        print("uncommitted changes: commit them first", file=sys.stderr)
        return 2
    steps.record(adw_id, "pr", "running", label="Pull request")
    ok, err = push_branch(branch, cwd=cwd)
    if not ok:
        steps.record(adw_id, "pr", "failed", label="Pull request", note=f"push failed: {err}")
        print(f"push failed: {err}", file=sys.stderr)
        return 1
    url, err = check_pr_exists_with_error(branch)
    if err:
        steps.record(adw_id, "pr", "failed", label="Pull request", note=err)
        print(err, file=sys.stderr)
        return 1
    if not url:
        with open(args.body_file, encoding="utf-8") as f:
            body = f.read()
        issue = _issue(args)
        if issue and f"#{issue}" not in body:
            body += f"\n\nCloses #{issue}"
        body += screenshots_section(adw_id, body)
        body += f"\n\nADW ID: `{adw_id}`"
        repo = extract_repo_path(get_repo_url(cwd))
        env = {**os.environ, **(get_github_env() or {})}
        proc = subprocess.run(["gh", "pr", "create", "-R", repo, "--base", "main", "--head", branch,
                               "--title", args.title, "--body", body], cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=120)
        found = re.search(r"https://github\.com/\S+/pull/\d+", proc.stdout + proc.stderr)
        if proc.returncode != 0 or not found:
            note = (proc.stderr or proc.stdout).strip()[-300:]
            steps.record(adw_id, "pr", "failed", label="Pull request", note=f"gh pr create failed: {note}")
            print(f"gh pr create failed: {note}", file=sys.stderr)
            return 1
        url = found.group(0)
        post_comment(adw_id, issue, f"✅ Pull request created: {url}", "ops")
    steps.record(adw_id, "pr", "done", label="Pull request", note=f"PR #{url.rstrip('/').rsplit('/', 1)[-1]}: {url}")
    try:
        os.makedirs(orchestrator_dir(adw_id), exist_ok=True)
        with open(os.path.join(orchestrator_dir(adw_id), "pr_url.txt"), "w", encoding="utf-8") as f:
            f.write(url + "\n")
    except OSError:
        pass
    print(url)
    return 0


def recorded_images(adw_id: str) -> list[dict]:
    return [e for e in messages.read_all(os.path.join(adw_dir(adw_id), messages.IMAGES)) if e.get("url")]


def screenshots_section(adw_id: str, body: str) -> str:
    """A Screenshots section for the PR body: the images recorded with `image` that the body doesn't show yet."""
    missing = [e for e in recorded_images(adw_id) if e["url"] not in body]
    if not missing:
        return ""
    return "\n\n## Screenshots\n\n" + "\n".join(f"**{e.get('label', '')}**\n\n![{e.get('label', '')}]({e['url']})\n"
                                                for e in missing)


# ---- messages from Ore: reply, ask, wait; screenshots -----------------------------------

def cmd_reply(args) -> int:
    text = str(args.text or "").strip()
    if not text:
        print("empty reply", file=sys.stderr)
        return 2
    messages.append(os.path.join(adw_dir(args.adw_id), messages.OUTBOX), {"type": "reply", "to": args.id, "text": text})
    print(f"reply to {args.id} sent")
    return 0


def _wait_inbox(adw_id: str, accept, timeout_s: float, start: int | None = None):
    """Block until accept(entry) holds for an inbox entry after byte `start` (default: the end now); the entry, or
    None after timeout_s."""
    path = os.path.join(adw_dir(adw_id), messages.INBOX)
    offset = messages.size(path) if start is None else start
    deadline = time.time() + timeout_s
    while True:
        entries, offset = messages.read_new(path, offset)
        for e in entries:
            if accept(e):
                return e
        if time.time() >= deadline:
            return None
        time.sleep(POLL_SECONDS)


def cmd_ask(args) -> int:
    """The question stays open in Ore until the user answers: each call blocks up to --wait-min (within a Bash
    call's limit), then says to run `ask --wait <n>` again. Only with --timeout-min (ADW_ASK_TIMEOUT_MIN) set does
    the agent give up after that long and decide itself."""
    out = os.path.join(adw_dir(args.adw_id), messages.OUTBOX)
    asked = [e for e in messages.read_all(out) if e.get("type") == "ask"]
    if args.wait is not None:
        ask = next((e for e in asked if e.get("n") == args.wait), None)
        if ask is None:
            print(f"no question {args.wait} was asked", file=sys.stderr)
            return 2
        n, start = args.wait, 0                       # the whole inbox: the answer may have come between calls
    else:
        if not (args.question or "").strip():
            print("give the question, or --wait <n> to keep waiting for one", file=sys.stderr)
            return 2
        n = 1 + len(asked)
        start = messages.size(os.path.join(adw_dir(args.adw_id), messages.INBOX))
        options = [o.strip() for o in (args.options or "").split(",") if o.strip()]
        ask = {"type": "ask", "n": n, "question": args.question.strip(), "options": options, "at": time.time()}
        messages.append(out, ask)
        print(f"Question {n} sent to the user.", flush=True)
    if any(e.get("type") == "ask_cancel" and e.get("n") == n for e in messages.read_all(out)):
        print(f"You stopped waiting for question {n} earlier; a late answer reaches you as a message.")
        return 0
    wait_s = args.wait_min * 60
    give_up = None
    if args.timeout_min:
        give_up = float(ask.get("at") or time.time()) + args.timeout_min * 60
        wait_s = max(0.0, min(wait_s, give_up - time.time()))
    print(f"Waiting for the answer to question {n}...", flush=True)
    answer = _wait_inbox(args.adw_id, lambda e: e.get("type") == "answer" and e.get("ask") == n, wait_s, start)
    if answer is not None:
        print(f"Answer: {answer.get('text', '')}")
        return 0
    if give_up is not None and time.time() >= give_up:
        messages.append(out, {"type": "ask_cancel", "n": n})
        print(f"No answer within {args.timeout_min:g} minutes. Decide yourself, note the assumption (it goes in the "
              "PR), and carry on. A late answer reaches you as a message.")
        return 0
    print(f"No answer yet; question {n} stays open in Ore (the time waiting doesn't count against the workflow's "
          f"limit). Run `ask --wait {n}` again to keep waiting. Don't decide it yourself and don't fail the workflow "
          "over it: the user answers when they can.")
    return 0


def cmd_wait(args) -> int:
    path = os.path.join(adw_dir(args.adw_id), messages.INBOX)
    if not messages.paused(messages.read_all(path)):
        print("Not paused (a resume or amend message arrived already): continue the work.")
        return 0
    print("Paused; waiting for a resume or amend message...", flush=True)
    msg = _wait_inbox(args.adw_id, lambda e: e.get("type") == "message" and e.get("mode") in ("resume", "amend", "ask"),
                      args.timeout_min * 60)
    if msg is None:
        print(f"Still paused after {args.timeout_min:g} minutes: run `wait` again.")
    elif msg.get("mode") == "ask":
        print(f"A question from {messages.sender(msg)} (id {msg.get('id')}): {msg.get('text', '')}\n"
              f"Answer it with `reply {msg.get('id')} \"...\"`, then run `wait` again: you are still paused.")
    else:
        print(f"{msg['mode'].capitalize()} from {messages.sender(msg)} (id {msg.get('id')}): {msg.get('text', '')}\n"
              + ("Continue the work, with this change." if msg["mode"] == "amend" else "Continue the work."))
    return 0


def cmd_image(args) -> int:
    target = args.target
    how = "url"
    if target.startswith(("http://", "https://")):
        url = target
    else:
        if not os.path.isfile(target):
            print(f"no such file: {target}", file=sys.stderr)
            return 2
        from adw_modules import image_upload
        url, how = image_upload.upload(os.path.abspath(target), args.adw_id, os.getcwd())
        if not url:
            print("upload failed (R2 isn't configured and the screenshot branch couldn't be pushed); not recorded",
                  file=sys.stderr)
            return 1
    messages.append(os.path.join(adw_dir(args.adw_id), messages.IMAGES), {"label": args.label, "url": url})
    print(f"![{args.label}]({url})" + ("" if how == "url" else f"   (uploaded to {how})"))
    return 0


CHECK_WAITING = 4


def _state(adw_id: str) -> dict:
    try:
        with open(os.path.join(adw_dir(adw_id), "adw_state.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def check_text(entry: dict) -> str:
    """What the orchestrator reads about its part of a batch check."""
    status = entry.get("status")
    counts = {k: len(entry.get(k) or []) for k in ("yours", "combined", "preexisting", "unknown")}
    lines = []
    if status == "green":
        lines.append(f"FULL CHECK GREEN (check {entry.get('n')}): the full suites pass with your branch merged onto "
                     "origin/main together with the batch's other branches. Go on to the pull request.")
    elif status == "conflict":
        c = entry.get("conflict") or {}
        lines.append(f"Your branch conflicts with {', '.join(c.get('with') or []) or 'another branch'} in "
                     f"{', '.join(c.get('files') or [])}. It is checked on its own next: run `check` again. Note the "
                     "conflict in the PR (the second of the two PRs to be merged needs it resolved).")
    else:
        lines.append(f"FULL CHECK FAILED (check {entry.get('n')}): {counts['yours']} failure(s) caused by your branch, "
                     f"{counts['combined']} that only appear with the batch's other branches merged.")
        lines.append("Fix yours (yourself or with an implementer: give it the report file), check them with "
                     "`adw_run_suites.py targeted`, commit, and run `check` again. For the combined ones, fix them "
                     "if the failing code or test is in files your branch changed; otherwise list them in the PR.")
    if counts["preexisting"]:
        lines.append(f"{counts['preexisting']} failure(s) already fail on origin/main: not yours, don't fix them here; "
                     "list them in the PR.")
    if counts["unknown"]:
        lines.append(f"{counts['unknown']} suite(s) stopped without naming failures (timeout or crash): list them in "
                     "the PR.")
    for key in ("yours", "combined", "preexisting", "unknown"):
        for it in (entry.get(key) or [])[:15]:
            lines.append(f"  [{key}] {it.get('text')}")
    if entry.get("report"):
        lines.append(f"Details and output: {entry['report']}")
    return "\n".join(lines)


def _check_local(args) -> int:
    """No batch to join (not an Ore run, or the batch check couldn't run): the full suites on this branch."""
    steps.record(args.adw_id, "check", "running", label="Full check", note="Full suites on this branch")
    suites = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adw_run_suites.py")
    proc = subprocess.run(["uv", "run", "--quiet", suites, "full", "--no-record", "--regen-types"],
                          capture_output=True, text=True)
    print((proc.stdout or "") + (proc.stderr or ""))
    last = next((ln for ln in reversed((proc.stdout or "").splitlines()) if ln.strip()), "")
    ok = proc.returncode == 0
    steps.record(args.adw_id, "check", "done" if ok else "failed", label="Full check",
                 note="Full suites on this branch: " + ("green" if ok else last[:200]))
    print("FULL CHECK GREEN: go on to the pull request." if ok else
          "FULL CHECK FAILED: fix the failures your branch caused, commit, and run `check` again. Failures in code "
          "your branch didn't touch may already fail on main: confirm that from the diff, then list them in the PR.")
    return 0 if ok else 1


def cmd_check(args) -> int:
    cwd = os.getcwd()
    if _git("status", "--porcelain", cwd=cwd).stdout.strip():
        print("uncommitted changes: commit everything first (the check runs on the commit, not the files)",
              file=sys.stderr)
        return 2
    sha = _git("rev-parse", "HEAD", cwd=cwd).stdout.strip()
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=cwd).stdout.strip()
    if not sha:
        print("not in a git worktree", file=sys.stderr)
        return 2
    if not _state(args.adw_id).get("ore_run_dir") or os.environ.get("ADW_CHECK_LOCAL") == "1":
        return _check_local(args)
    outbox = os.path.join(adw_dir(args.adw_id), messages.OUTBOX)
    inbox = os.path.join(adw_dir(args.adw_id), messages.INBOX)
    asked = [e for e in messages.read_all(outbox) if e.get("type") == "check"]
    last = asked[-1] if asked else None
    answered = {e.get("n"): e for e in messages.read_all(inbox) if e.get("type") == "check_result"}
    conflict = answered.get(last["n"]) if last and last.get("sha") == sha else None
    if conflict and conflict.get("status") == "conflict":     # checked again, on its own (the trigger runs it at once)
        print(check_text(conflict) + "\n", flush=True)
    if last and last.get("sha") == sha and not (conflict and conflict.get("status") == "conflict"):
        n = last["n"]                                    # asked already for this commit: its answer, or keep waiting
    else:
        n = 1 + len(asked)
        messages.append(outbox, {"type": "check", "n": n, "sha": sha, "branch": branch})
        steps.record(args.adw_id, "check", "running", label="Full check",
                     note=f"Check {n}: waiting for the batch's full check")
    print(f"Full check {n} for {sha[:10]}: it runs once for the whole batch, when the other workflows are ready "
          f"too. Waiting up to {args.timeout_min:g} minutes...", flush=True)
    found = answered.get(n)
    if found is None:
        found = _wait_inbox(args.adw_id, lambda e: e.get("type") == "check_result" and e.get("n") == n,
                            args.timeout_min * 60, start=0)
    if found is None:
        print(f"Still waiting after {args.timeout_min:g} minutes (the other workflows aren't ready yet, or the check is "
              "running). Run `check` again: same commit, so it keeps waiting and nothing new is queued.")
        return CHECK_WAITING
    if found.get("status") == "error":
        print(f"The batch's full check couldn't run ({found.get('error', 'unknown error')}); running the full suites on "
              "this branch instead.", flush=True)
        return _check_local(args)
    print(check_text(found))
    return 0 if found.get("status") == "green" else 3 if found.get("status") == "conflict" else 1


def cmd_result(args) -> int:
    if args.json is not None:
        if args.status or args.summary or args.pr_url or args.review_rounds is not None or args.reason or args.blocker:
            print("give either --json or the fields, not both", file=sys.stderr)
            return 2
        try:
            result = json.loads(args.json)
        except ValueError as e:
            print(f"--json isn't valid JSON: {e}", file=sys.stderr)
            return 2
        if isinstance(result, dict) and "force" in result:
            args.force = args.force or bool(result.pop("force"))
    else:
        result = {k: v for k, v in (("status", args.status), ("summary", args.summary), ("pr_url", args.pr_url),
                                    ("review_rounds", args.review_rounds), ("reason", args.reason),
                                    ("open_blockers", args.blocker or None)) if v is not None}
    errors = messages.schema_errors(result)
    report = None
    if args.report_file:
        try:
            with open(args.report_file, encoding="utf-8") as f:
                report = f.read().strip()
        except OSError as e:
            errors.append(f"can't read --report-file: {e}")
        else:
            if not report:
                errors.append("--report-file is empty")
    if errors:
        print("result not recorded: " + "; ".join(errors), file=sys.stderr)
        return 2
    if report:
        save_report(args.adw_id, report, result.get("pr_url") or recorded_pr(args.adw_id))
    path = os.path.join(adw_dir(args.adw_id), messages.RESULT)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({**result, **({"force": True} if args.force else {})}, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)                   # atomic: the workflow never reads half a file
    print(f"result recorded: {result['status']}. The workflow ends the session once no subagent is running; "
          "end your turn now.")
    return 0


REPORT_MARK = "<!-- adw-workflow-report -->"


def recorded_pr(adw_id: str) -> str | None:
    try:
        with open(os.path.join(orchestrator_dir(adw_id), "pr_url.txt"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def save_report(adw_id: str, report: str, pr_url: str | None) -> None:
    """Keep the workflow report for Ore and the merge workflow, and post it on the PR (best effort): once per
    version, so a resumed session reporting again doesn't post it twice, and a follow-up's report is posted too."""
    report = report[:messages.REPORT_LIMIT]
    path = os.path.join(adw_dir(adw_id), messages.REPORT)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    if not pr_url:
        return
    from adw_modules.github import get_github_env
    env = {**os.environ, **(get_github_env() or {})}
    try:
        seen = subprocess.run(["gh", "pr", "view", pr_url, "--json", "comments", "--jq", ".comments[].body"],
                              env=env, capture_output=True, text=True, timeout=60)
        if report in seen.stdout:
            return                      # posted already (a resumed session reports again)
        title = "Workflow report (updated)" if REPORT_MARK in seen.stdout else "Workflow report"
        subprocess.run(["gh", "pr", "comment", pr_url, "--body", f"{REPORT_MARK}\n## {title}\n\n{report}"],
                       env=env, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"couldn't post the report on the PR: {e}", file=sys.stderr)


def cmd_app(args) -> int:
    import logging
    from adw_modules import env_setup
    state = _state(args.adw_id)
    worktree, backend, frontend = state.get("worktree_path"), state.get("backend_port"), state.get("frontend_port")
    if not (worktree and backend and frontend):
        print("no worktree or ports in this workflow's state: the app can't be checked", file=sys.stderr)
        return 1
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    logger = logging.getLogger("adw_report.app")
    try:
        note = env_setup.ensure_app(worktree, int(backend), int(frontend), logger,
                                    log_path=os.path.join(orchestrator_dir(args.adw_id), "app_start.log"))
    except Exception as e:  # noqa: BLE001 - SetupError, or anything unexpected: the reason is what matters
        print(f"APP NOT RUNNING: {e}")
        return 1
    print(note)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="adw_report.py", description="Report ADW progress (steps, plan, comments, PR, "
                                "replies, questions, screenshots, the full check, the final result)")
    p.add_argument("--adw-id", default=os.environ.get("ADW_ID"))
    p.add_argument("--issue", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("step")
    s.add_argument("key")
    s.add_argument("status")
    s.add_argument("--label")
    s.add_argument("--parent")
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_step)
    s = sub.add_parser("plan")
    s.add_argument("--package", action="append", default=[], required=True,
                   help='id=name[:after,after], in execution order')
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_plan)
    s = sub.add_parser("comment")
    s.add_argument("text", nargs="?", default="")
    s.add_argument("--file", help="post this Markdown file instead")
    s.add_argument("--agent", default="orchestrator")
    s.set_defaults(func=cmd_comment)
    s = sub.add_parser("pr")
    s.add_argument("--title", required=True)
    s.add_argument("--body-file", required=True)
    s.set_defaults(func=cmd_pr)
    s = sub.add_parser("reply")
    s.add_argument("id")
    s.add_argument("text")
    s.set_defaults(func=cmd_reply)
    s = sub.add_parser("ask")
    s.add_argument("question", nargs="?", default="")
    s.add_argument("--options", default="", help="comma-separated choices")
    s.add_argument("--wait", type=int, help="keep waiting for the answer to question N (asked before)")
    s.add_argument("--wait-min", type=float, default=55.0, help="how long this call blocks")
    s.add_argument("--timeout-min", type=float, default=float(os.getenv("ADW_ASK_TIMEOUT_MIN") or 0),
                   help="give up after this long and decide yourself (0, the default: wait for the answer)")
    s.set_defaults(func=cmd_ask)
    s = sub.add_parser("wait")
    s.add_argument("--timeout-min", type=float, default=55.0)
    s.set_defaults(func=cmd_wait)
    s = sub.add_parser("image")
    s.add_argument("label")
    s.add_argument("target", help="a PNG/JPEG file (uploaded) or an https URL")
    s.set_defaults(func=cmd_image)
    s = sub.add_parser("check", help="the full check once the work is done (the batch's, in an Ore run)")
    s.add_argument("--timeout-min", type=float, default=55.0)
    s.set_defaults(func=cmd_check)
    s = sub.add_parser("app", help="the app running for the screenshots: restarted by script when a server is down")
    s.set_defaults(func=cmd_app)
    s = sub.add_parser("result", help="the final result: ends the run once no subagent is running")
    s.add_argument("status", nargs="?", default=None, help="pr_opened | failed | dropped")
    s.add_argument("--summary", help="what was delivered, in 1-3 sentences")
    s.add_argument("--pr-url")
    s.add_argument("--review-rounds", type=int)
    s.add_argument("--reason", help="why it failed, or why there's nothing to do (dropped)")
    s.add_argument("--blocker", action="append", help="an open blocker (repeat)")
    s.add_argument("--report-file", help="the workflow report (Markdown): decisions, not done, pending, caveats")
    s.add_argument("--json", help="the whole result as one JSON object instead of the fields")
    s.add_argument("--force", action="store_true", help="give up now even though subagents are still running")
    s.set_defaults(func=cmd_result)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not args.adw_id:
        print("no ADW id (set ADW_ID or pass --adw-id)", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
