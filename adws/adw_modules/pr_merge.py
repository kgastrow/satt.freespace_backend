"""Merge a pull request, with Claude resolving conflicts with main when there are any.

Steps (each reported through on_step(key, status, note), so the Ore trigger draws them and adw_merge_iso.py prints
them):
  pr       the PR's details; a merged PR is done already, a closed or draft one stops here.
  update   main merged into the PR's branch, only when GitHub says the PR conflicts (or can't tell). It happens in
           the workflow's own worktree when that is still here, clean and on the PR's commit (its dependencies
           are installed, so the agent can run the checks), else in trees/merge-pr-<n> (detached).
  resolve  conflicts: Claude (ADW_MERGE_MODEL, default claude-opus-5-5) resolves them in place with the issue,
           the PR, the workflow report (agents/<adw_id>/report.md or the PR's "Workflow report" comment) and what
           main changed in those files since the branch left it. When the worktree has the project's
           dependencies it runs the checks on the changed code too, unless the merge was started with
           run_checks=False (Ore's "Run the tests" left unticked): then it checks its resolution by reading.
           It writes its notes (what it kept from each side
           and why) to a file, or "CANNOT_RESOLVE: <why>" when the two sides can't be reconciled without a person.
           The merge commit is made only when no file is left unmerged and no conflict marker is left.
  push     the merge commit pushed to the PR's branch (never forced); the notes go on the PR as a comment.
  checks   the PR's checks: waited for while pending (ADW_MERGE_CHECKS_MIN, default 30). Failing checks stop the
           merge; a PR without checks goes on.
  merge    gh pr merge with the repository's method (squash when allowed, else merge, else rebase), deleting the
           branch on GitHub.
  cleanup  the temporary worktree removed (the workflow's own worktree is left for the run's cleanup).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from adw_modules import messages

MODEL = os.getenv("ADW_MERGE_MODEL", "claude-opus-5-5")
CHECKS_WAIT = float(os.getenv("ADW_MERGE_CHECKS_MIN", "30") or 30) * 60
CLAUDE_TIMEOUT = float(os.getenv("ADW_MERGE_CLAUDE_MIN", "40") or 40) * 60
GH_TIMEOUT = 60
POLL = 30
STEPS = [("pr", "Pull request"), ("update", "Update from main"), ("resolve", "Resolve conflicts"), ("push", "Push"),
         ("checks", "Checks"), ("merge", "Merge"), ("pull", "Update the main checkout"), ("cleanup", "Clean up")]
ADW_BRANCH = re.compile(r"(?:^|[-/])issue-(\d+)-adw-(\d{14}-[0-9a-f]{12}|[0-9a-f]{8})(?:-|$)")
ADW_BODY = re.compile(r"ADW ID:\s*`?([0-9A-Za-z][0-9A-Za-z-]{6,40})`?")
CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)
REPORT_MARK = "<!-- adw-workflow-report -->"
NOTES_MARK = "<!-- adw-merge-notes -->"
CANNOT = "CANNOT_RESOLVE:"
MARKER = re.compile(r"^(<{7}|>{7})( |$)|^={7}$", re.M)
PR_FIELDS = "number,title,body,url,state,isDraft,headRefName,headRefOid,baseRefName,mergeable,statusCheckRollup,comments"


class MergeError(RuntimeError):
    """The merge stopped; the message says why and what to do."""


def adw_ids(pr: dict) -> tuple[int | None, str | None]:
    """(issue, adw_id) of an ADW pull request (from its branch or its body), else what can be found."""
    m = ADW_BRANCH.search(pr.get("headRefName") or "")
    if m:
        return int(m.group(1)), m.group(2)
    b, c = ADW_BODY.search(pr.get("body") or ""), CLOSES.search(pr.get("body") or "")
    return (int(c.group(1)) if c else None), (b.group(1) if b else None)


def check_state(rollup) -> str:
    """statusCheckRollup -> passing | failing | pending | none."""
    states = []
    for c in rollup or []:
        s = str(c.get("conclusion") or c.get("state") or c.get("status") or "").upper()
        states.append(s)
    if not states:
        return "none"
    if any(s in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE") for s in states):
        return "failing"
    if any(s in ("", "PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "WAITING", "REQUESTED") for s in states):
        return "pending"
    return "passing"


class Merge:
    def __init__(self, number: int | str, repo_root: str | Path, on_step=None, log=print, env: dict | None = None,
                 run_checks: bool = True):
        self.number = str(number).lstrip("#")
        if not self.number.isdigit():
            raise MergeError(f"Not a pull request number: {number}")
        self.root = Path(repo_root)
        self.on_step = on_step or (lambda key, status, note="": None)
        self.log = log
        self.env = env or dict(os.environ)
        self.run_checks = run_checks
        self.dir = self.root / "agents" / "merges" / f"pr-{self.number}"
        self.pr: dict = {}
        self.wt: Path | None = None
        self.own = False             # True: trees/merge-pr-<n>, ours to remove
        self.notes = ""
        self.resolved: list[str] = []
        self.updated = False
        self.pulled: dict = {}       # what pull_main() did: {"from", "to", "adws"} or {"skipped": why}

    # ---- helpers ----------------------------------------------------------------------------
    def step(self, key: str, status: str, note: str = "") -> None:
        self.on_step(key, status, note)
        if note:
            self.log(f"{dict(STEPS).get(key, key)}: {note}")

    def gh(self, *args: str, check: bool = True, timeout: int = GH_TIMEOUT) -> str:
        try:
            p = subprocess.run(["gh", *args], cwd=self.root, env=self.env, capture_output=True, text=True,
                               timeout=timeout)
        except FileNotFoundError:
            raise MergeError("The GitHub CLI (gh) isn't installed here, or isn't on PATH")
        except subprocess.TimeoutExpired:
            raise MergeError(f"gh {' '.join(args[:2])} took longer than {timeout} s")
        if check and p.returncode != 0:
            raise MergeError(f"gh {' '.join(args[:2])} failed: {(p.stderr or p.stdout).strip()[-400:]}")
        return p.stdout

    def git(self, *args: str, cwd: Path | None = None, check: bool = True, timeout: int = 300):
        p = subprocess.run(["git", *args], cwd=cwd or self.wt or self.root, env=self.env, capture_output=True,
                           text=True, timeout=timeout)
        if check and p.returncode != 0:
            raise MergeError(f"git {' '.join(args[:2])} failed: {(p.stderr or p.stdout).strip()[-400:]}")
        return p

    def view(self) -> dict:
        try:
            return json.loads(self.gh("pr", "view", self.number, "--json", PR_FIELDS))
        except ValueError:
            raise MergeError(f"gh returned no details for PR #{self.number}")

    # ---- the steps ------------------------------------------------------------------------------
    def run(self) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            return self._run()
        finally:
            self.cleanup()

    def _run(self) -> dict:
        self.step("pr", "running")
        self.pr = pr = self.view()
        state = str(pr.get("state")).upper()
        if state == "MERGED":
            self.step("pr", "done", f"#{self.number} is merged already")
            for key, _ in STEPS[1:]:
                if key != "pull":
                    self.step(key, "skipped")
            self.pull_main()
            return self.outcome(merged=True, method="", already=True)
        if state != "OPEN":
            self.step("pr", "failed", f"#{self.number} is {state.lower()}")
            raise MergeError(f"PR #{self.number} is {state.lower()}, not open")
        if pr.get("isDraft"):
            self.step("pr", "failed", "a draft")
            raise MergeError(f"PR #{self.number} is a draft: mark it ready for review on GitHub first")
        self.step("pr", "done", f"#{self.number}: {pr.get('title')} ({pr['headRefName']} → {pr['baseRefName']})")

        mergeable = str(pr.get("mergeable") or "").upper()
        if mergeable == "MERGEABLE":
            for key in ("update", "resolve", "push"):
                self.step(key, "skipped", "No conflicts with main" if key == "update" else "")
        else:
            self.update()
        self.checks()
        method = self.merge()
        self.pull_main()
        return self.outcome(merged=True, method=method)

    def outcome(self, merged: bool, method: str, already: bool = False) -> dict:
        return {"merged": merged, "number": int(self.number), "url": self.pr.get("url") or "", "method": method,
                "title": self.pr.get("title") or "", "already": already, "updated": self.updated,
                "resolved": self.resolved, "notes": self.notes, "pulled": self.pulled}

    def worktree(self) -> None:
        """The workflow's own worktree when it is clean and on the PR's commit, else a detached one of ours."""
        head, base = self.pr["headRefName"], self.pr["baseRefName"]
        self.git("fetch", "-q", "origin", head, base, cwd=self.root)
        _issue, adw_id = adw_ids(self.pr)
        if adw_id:
            for line in self.git("worktree", "list", "--porcelain", cwd=self.root).stdout.split("\n\n"):
                fields = dict(l.split(" ", 1) for l in line.splitlines() if " " in l)
                path = fields.get("worktree")
                if path and fields.get("branch") == f"refs/heads/{head}" and Path(path).is_dir():
                    st = self.git("status", "--porcelain", cwd=Path(path), check=False)
                    sha = self.git("rev-parse", "HEAD", cwd=Path(path), check=False).stdout.strip()
                    if st.returncode == 0 and not st.stdout.strip() and sha == self.pr.get("headRefOid"):
                        self.wt = Path(path)
                        self.log(f"Working in the workflow's worktree: {path}")
                        return
        path = self.root / "trees" / f"merge-pr-{self.number}"
        if path.exists():
            self.git("worktree", "remove", "--force", str(path), cwd=self.root, check=False)
            shutil.rmtree(path, ignore_errors=True)
        self.git("worktree", "prune", cwd=self.root, check=False)
        self.git("worktree", "add", "-q", "--detach", str(path), f"origin/{head}", cwd=self.root)
        self.wt, self.own = path, True

    def update(self) -> None:
        self.step("update", "running", "Merging main into the PR's branch")
        self.worktree()
        base = self.pr["baseRefName"]
        p = self.git("merge", "--no-ff", "--no-edit", f"origin/{base}", check=False)
        conflicted = self.unmerged()
        if p.returncode == 0:
            up_to_date = "Already up to date" in (p.stdout + p.stderr)
            self.step("update", "done", "Up to date with main" if up_to_date else "Merged main without conflicts")
            self.step("resolve", "skipped")
            self.updated = not up_to_date
        elif not conflicted:
            self.git("merge", "--abort", check=False)
            self.step("update", "failed", (p.stderr or p.stdout).strip()[-300:])
            raise MergeError(f"Merging {base} into the branch failed: {(p.stderr or p.stdout).strip()[-300:]}")
        else:
            self.step("update", "done", f"{len(conflicted)} file{'s' if len(conflicted) != 1 else ''} conflict")
            self.resolve(conflicted)
            self.updated = True
        if self.updated:
            self.push()
        else:
            self.step("push", "skipped")

    def unmerged(self) -> list[str]:
        out = self.git("diff", "--name-only", "--diff-filter=U", check=False).stdout
        return [f for f in out.splitlines() if f.strip()]

    def resolve(self, files: list[str]) -> None:
        self.step("resolve", "running", f"Claude ({MODEL}) is resolving {', '.join(files[:6])}"
                  + (f" and {len(files) - 6} more" if len(files) > 6 else ""))
        notes_file = self.dir / "resolution.md"
        notes_file.unlink(missing_ok=True)
        prompt = self.prompt(files, notes_file)
        (self.dir / "prompt.md").write_text(prompt, encoding="utf-8")
        cmd = [os.getenv("CLAUDE_CODE_PATH", "claude"), "-p", prompt, "--model", MODEL, "--output-format", "json",
               "--dangerously-skip-permissions",
               "--disallowedTools", "Bash(git push:*)", "Bash(git reset --hard:*)", "Bash(git merge --abort:*)",
               "Bash(git checkout -- :*)", "Bash(gh pr merge:*)"]
        try:
            p = subprocess.run(cmd, cwd=self.wt, env=self.env, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.abort("resolve", f"Claude took longer than {CLAUDE_TIMEOUT / 60:.0f} minutes")
        except FileNotFoundError:
            self.abort("resolve", "Claude Code (claude) isn't installed here, or isn't on PATH")
        (self.dir / "claude_output.json").write_text(p.stdout or "", encoding="utf-8")
        final = ""
        try:
            final = str(json.loads(p.stdout or "{}").get("result") or "")
        except ValueError:
            pass
        notes = notes_file.read_text(encoding="utf-8").strip() if notes_file.exists() else final.strip()
        if CANNOT in notes or CANNOT in final:
            why = (notes if CANNOT in notes else final).split(CANNOT, 1)[1].strip()
            self.abort("resolve", f"Claude couldn't resolve the conflicts: {why[:600]}")
        if p.returncode != 0 and not notes:
            self.abort("resolve", f"Claude stopped (exit {p.returncode}): {(p.stderr or final).strip()[-300:]}")
        left = self.unmerged()
        marked = [f for f in files if (self.wt / f).is_file() and MARKER.search(
            (self.wt / f).read_text(encoding="utf-8", errors="replace"))]
        if marked:
            self.abort("resolve", f"Conflict markers are left in {', '.join(marked[:5])}")
        if left:
            self.git("add", "--", *left)          # resolved in the files but not staged
        if self.unmerged():
            self.abort("resolve", f"Files are still unmerged: {', '.join(self.unmerged()[:5])}")
        self.notes = notes or "(no notes)"
        self.resolved = files
        base, head = self.pr["baseRefName"], self.pr["headRefName"]
        self.git("commit", "--no-edit", "-q", "-m", f"Merge {base} into {head}: resolve conflicts in {len(files)} "
                 f"file{'s' if len(files) != 1 else ''}", "-m", self.notes[:6000], "--allow-empty")
        self.step("resolve", "done", f"{len(files)} file{'s' if len(files) != 1 else ''} resolved")

    def abort(self, key: str, why: str):
        self.git("merge", "--abort", check=False)
        self.step(key, "failed", why[:300])
        for k in ("push", "checks", "merge"):
            self.step(k, "skipped")
        raise MergeError(why + ". Nothing was pushed; resolve it on GitHub or locally, or press Merge again.")

    def report(self) -> str:
        """The workflow's report: agents/<adw_id>/report.md here, else the PR's "Workflow report" comment."""
        _issue, adw_id = adw_ids(self.pr)
        if adw_id:
            path = self.root / "agents" / adw_id / messages.REPORT
            if path.is_file():
                return path.read_text(encoding="utf-8", errors="replace")[:messages.REPORT_LIMIT]
        for c in self.pr.get("comments") or []:
            if REPORT_MARK in (c.get("body") or ""):
                return c["body"].replace(REPORT_MARK, "").strip()[:messages.REPORT_LIMIT]
        return ""

    def issue_text(self) -> str:
        issue, _ = adw_ids(self.pr)
        if not issue:
            return ""
        try:
            data = json.loads(self.gh("issue", "view", str(issue), "--json", "number,title,body"))
        except (MergeError, ValueError):
            return ""
        return f"#{data.get('number')}: {data.get('title')}\n\n{(data.get('body') or '')[:12000]}"

    def prompt(self, files: list[str], notes_file: Path) -> str:
        base, head = self.pr["baseRefName"], self.pr["headRefName"]
        mb = self.git("merge-base", "HEAD", f"origin/{base}", check=False).stdout.strip()
        incoming = self.git("log", "--format=%h %an: %s", f"{mb}..origin/{base}", "--", *files, check=False).stdout
        ours = self.git("log", "--format=%h %s", f"{mb}..HEAD", "--", *files, check=False).stdout
        toolchain = (self.wt / "app" / "backend" / ".venv").exists() or (self.wt / "app" / "frontend" / "node_modules").exists()
        suites = self.root / "adws" / "adw_run_suites.py"
        checks = (f"The project's dependencies are installed in this worktree: after resolving, run `uv run {suites} "
                  f"changed --base origin/{base}` and fix what the merge broke (only that; failures that also happen "
                  "on main aren't yours to fix). Run it again until it's clean or only shows failures from main."
                  if toolchain and suites.exists() and self.run_checks else
                  ("Don't run the test suites, the build or the linters: whoever started this merge chose not to. "
                   if self.run_checks is False else
                   "The project's dependencies aren't installed in this worktree, so the suites can't run here. ") +
                  "Check your resolution by reading: imports, names and signatures used on both sides must still "
                  "exist, and nothing from either side may be silently lost. The PR's CI runs after the push.")
        alembic = next((p.parent for p in (self.wt / "app" / "backend" / "alembic.ini", self.wt / "alembic.ini")
                        if p.exists()), None)
        if alembic is not None:
            exe = alembic / ".venv" / "bin" / "alembic"
            run = f"`{exe} heads`" if exe.exists() else "`alembic heads` (or `uv run alembic heads`)"
            checks += f"""

Alembic: whatever the conflicts were, check that the migrations still have one head. In {alembic}, run {run}
(it reads only the migration scripts, no database; it isn't a test suite, so run it even when told not to run
the suites). If it can't run, work it out from the `revision` and `down_revision` values in the versions
folder. More than one head means main and the branch each added migrations on the same parent: re-parent the
branch's first new migration onto main's head (its `down_revision`, and the "Revises:" line in its docstring), so
the history is one line again. Don't add an `alembic merge` migration, and don't edit main's migrations. If the
branch's migration depends on something main's new migrations changed (the same table or column), adapt it.
Check again until there is exactly one head, and say in your notes which migration you re-parented."""
        return f"""You are merging `{base}` into the branch `{head}` of pull request #{self.number}, and git stopped
on conflicts. Resolve them in place, in this worktree ({self.wt}). The merge is in progress; don't abort it, don't
commit it (the workflow commits it after checking), don't push, and don't touch files that aren't part of the merge.

Use your own judgement. Both sides are intended changes: the branch delivers the issue below; main moved on with
other work (often another workflow's pull request). Keep both sides' intent: combine them, don't pick one side
wholesale unless the other side's change is truly superseded (say so in your notes). Where both sides changed the
same behaviour in incompatible ways, prefer what main now does for main's own feature, and adapt the branch's
change to it so the issue is still delivered. Lock files and generated files (package-lock.json, uv.lock, generated
API types) are regenerated from their sources rather than hand-merged when the tools are available; otherwise take
main's version and re-apply the branch's dependency changes. Migrations: never merge two migration files into one;
if both sides added migrations with clashing numbers or parents, renumber or re-parent the branch's.

Conflicted files: {', '.join(files)}

{checks}

When every conflict is resolved and `git add`ed, write your notes to {notes_file} (Markdown): per file, what each
side changed, what you kept and why, and anything a reviewer should look at. If the conflict can't be resolved
without a decision from a person (the two sides want contradictory behaviour and neither the issue nor the report
settles it), don't guess: leave the files as they are and write `{CANNOT} <what conflicts and the decision needed>`
to {notes_file}.

## The pull request
#{self.number}: {self.pr.get('title')}

{(self.pr.get('body') or '')[:12000]}

## The issue
{self.issue_text() or '(not found)'}

## The workflow's report (decisions, what's pending, caveats)
{self.report() or '(none)'}

## What main changed in these files since the branch left it
{incoming.strip() or '(nothing listed)'}

## What the branch changed in these files
{ours.strip() or '(nothing listed)'}
"""

    def push(self) -> None:
        head = self.pr["headRefName"]
        self.step("push", "running")
        p = self.git("push", "origin", f"HEAD:refs/heads/{head}", check=False)
        if p.returncode != 0:
            self.step("push", "failed", (p.stderr or p.stdout).strip()[-300:])
            raise MergeError(f"Pushing the merge to {head} failed (someone may have pushed meanwhile: press Merge "
                             f"again): {(p.stderr or p.stdout).strip()[-300:]}")
        self.step("push", "done", f"Pushed to {head}")
        if self.resolved:
            body = (f"{NOTES_MARK}\n## Merged `{self.pr['baseRefName']}` into this branch\n\nConflicts resolved in "
                    f"{', '.join(f'`{f}`' for f in self.resolved)} by Claude ({MODEL}).\n\n{self.notes}")
            self.gh("pr", "comment", self.number, "--body", body[:60000], check=False)

    def checks(self) -> None:
        self.step("checks", "running")
        deadline = time.time() + CHECKS_WAIT
        had_checks = bool(self.pr.get("statusCheckRollup"))
        first = True
        while True:
            pr = self.view() if (self.updated or not first) else self.pr
            first = False
            state = check_state(pr.get("statusCheckRollup"))
            if state == "none" and self.updated and had_checks:
                state = "pending"           # just pushed: the new commit's checks haven't started yet
            if state in ("passing", "none"):
                self.step("checks", "done" if state == "passing" else "skipped",
                          "Checks pass" if state == "passing" else "No checks on this PR")
                return
            if state == "failing":
                failing = [c.get("name") or c.get("context") or "?" for c in pr.get("statusCheckRollup") or []
                           if str(c.get("conclusion") or c.get("state") or "").upper() in
                           ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE")]
                self.step("checks", "failed", f"Failing: {', '.join(failing[:5])}")
                self.step("merge", "skipped")
                raise MergeError(f"PR #{self.number}'s checks fail ({', '.join(failing[:5])}): not merged. Fix them "
                                 "and press Merge again.")
            if time.time() > deadline:
                self.step("checks", "failed", f"Still pending after {CHECKS_WAIT / 60:.0f} minutes")
                self.step("merge", "skipped")
                raise MergeError(f"PR #{self.number}'s checks are still running after {CHECKS_WAIT / 60:.0f} "
                                 "minutes: not merged. Press Merge again once they finish.")
            self.step("checks", "running", "Waiting for the checks")
            time.sleep(POLL)

    def merge_method(self) -> str:
        try:
            allowed = json.loads(self.gh("repo", "view", "--json",
                                         "squashMergeAllowed,mergeCommitAllowed,rebaseMergeAllowed"))
        except (MergeError, ValueError):
            return "squash"
        for method, key in (("squash", "squashMergeAllowed"), ("merge", "mergeCommitAllowed"),
                            ("rebase", "rebaseMergeAllowed")):
            if allowed.get(key):
                return method
        raise MergeError("This repository allows no merge method (squash, merge or rebase)")

    def merge(self) -> str:
        self.step("merge", "running")
        method = self.merge_method()
        try:
            self.gh("pr", "merge", self.number, f"--{method}", "--delete-branch")
        except MergeError as e:
            # The merge can succeed while deleting the local branch fails (e.g. a worktree still has it checked
            # out): look again before reporting a failure.
            if str(self.view().get("state")).upper() != "MERGED":
                self.step("merge", "failed", str(e)[-300:])
                raise
            self.git("push", "origin", "--delete", self.pr["headRefName"], cwd=self.root, check=False)
        self.step("merge", "done", f"Merged ({method})")
        return method

    def pull_main(self) -> None:
        """Fast-forward the main checkout (where the trigger and the workflows run from) to the merged base branch,
        only when it is on that branch with no local changes. Never fails the merge: it has happened."""
        self.step("pull", "running")
        base = self.pr.get("baseRefName") or "main"

        def skip(why: str) -> None:
            self.pulled = {"skipped": why}
            self.step("pull", "skipped", why)
        try:
            branch = self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.root).stdout.strip()
            if branch != base:
                return skip(f"The main checkout is on {branch}, not {base}: not updated")
            if self.git("status", "--porcelain", "--untracked-files=no", cwd=self.root).stdout.strip():
                return skip(f"The main checkout has local changes: not updated (git pull --ff-only when ready)")
            before = self.git("rev-parse", "HEAD", cwd=self.root).stdout.strip()
            self.git("fetch", "-q", "origin", base, cwd=self.root)
            if self.git("merge", "--ff-only", "-q", f"origin/{base}", cwd=self.root, check=False).returncode:
                return skip(f"The main checkout has commits that aren't on origin/{base}: not updated")
            after = self.git("rev-parse", "HEAD", cwd=self.root).stdout.strip()
        except MergeError as e:
            return skip(f"Couldn't update the main checkout: {str(e)[-200:]}")
        adws = bool(before != after and self.git("diff", "--name-only", before, after, "--", "adws",
                                                 cwd=self.root).stdout.strip())
        self.pulled = {"from": before[:8], "to": after[:8], "adws": adws}
        if before == after:
            self.step("pull", "done", f"The main checkout is up to date ({after[:8]})")
        else:
            self.step("pull", "done", f"The main checkout is now on {after[:8]}" + (
                "; the ADW scripts changed: restart Ore so the trigger uses them" if adws else ""))

    def cleanup(self) -> None:
        if self.own and self.wt:
            self.git("worktree", "remove", "--force", str(self.wt), cwd=self.root, check=False)
            shutil.rmtree(self.wt, ignore_errors=True)
            self.git("worktree", "prune", cwd=self.root, check=False)
            self.on_step("cleanup", "done", "Removed the temporary worktree")
        else:
            self.on_step("cleanup", "skipped", "")
