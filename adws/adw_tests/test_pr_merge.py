"""Merging from Ore: adw_modules/pr_merge.py on real git repositories with stand-ins for gh and claude, the Ore
trigger's --ore-merge run, and the workflow report (adw_report.py result --report-file, the part's "report").

Run: uv run --with pytest --with pydantic --with python-dotenv pytest adws/adw_tests/test_pr_merge.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

ADWS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ADWS))

import adw_report  # noqa: E402
from adw_modules import messages, pr_merge, steps  # noqa: E402
from adw_triggers import trigger_ore as ae  # noqa: E402

BRANCH = "feat-issue-7-adw-20261104120000-abcdef123456-greeting"

# gh: answers from <state>/pr.json; records what it was asked to do in <state>/calls.jsonl.
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
state = os.environ["FAKE_STATE"]
args = sys.argv[1:]
with open(os.path.join(state, "calls.jsonl"), "a") as f:
    f.write(json.dumps(args) + "\n")
pr = json.load(open(os.path.join(state, "pr.json")))
if args[:2] == ["pr", "view"]:
    print(json.dumps(pr))
elif args[:2] == ["repo", "view"]:
    print(json.dumps({"squashMergeAllowed": True}))
elif args[:2] == ["issue", "view"]:
    print(json.dumps({"number": 7, "title": "Say hello properly", "body": "The greeting must name the user."}))
elif args[:2] == ["pr", "merge"]:
    pr["state"] = "MERGED"
    json.dump(pr, open(os.path.join(state, "pr.json"), "w"))
elif args[:2] == ["pr", "comment"]:
    pass
else:
    sys.exit("unexpected gh call: " + " ".join(args))
'''

# claude: FAKE_CLAUDE=resolve writes both sides into each conflicted file and the notes; cannot gives up; markers
# leaves the conflict as it is but writes notes.
FAKE_CLAUDE = r'''#!/usr/bin/env python3
import json, os, re, subprocess, sys
prompt = sys.argv[sys.argv.index("-p") + 1]
open(os.path.join(os.environ["FAKE_STATE"], "prompt.txt"), "w").write(prompt)
notes = re.search(r"write your notes to (\S+?) \(Markdown\)", prompt).group(1)
mode = os.environ.get("FAKE_CLAUDE", "resolve")
files = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"], capture_output=True, text=True).stdout.split()
if mode == "cannot":
    open(notes, "w").write("CANNOT_RESOLVE: main removed the greeting the issue asks to change")
elif mode == "markers":
    open(notes, "w").write("done")
else:
    for f in files:
        open(f, "w").write("Hello, dear user!\nBye from main\n")
        subprocess.run(["git", "add", f])
    open(notes, "w").write("greeting.txt: kept the branch's greeting and main's farewell.")
print(json.dumps({"type": "result", "result": "Resolved."}))
'''


def git(cwd, *args, check=True):
    out = subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t", *args], cwd=cwd, capture_output=True,
                         text=True)
    assert out.returncode == 0 or not check, out.stderr
    return out.stdout.strip()


@pytest.fixture
def world(tmp_path, monkeypatch):
    """origin (bare), the main checkout (root) and a PR branch; gh and claude stand-ins on PATH."""
    origin, root, state, bin_ = tmp_path / "origin.git", tmp_path / "root", tmp_path / "state", tmp_path / "bin"
    for d in (state, bin_):
        d.mkdir()
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(root))
    git(root, "config", "user.name", "T")
    git(root, "config", "user.email", "t@t")
    (root / "greeting.txt").write_text("Hello\nBye\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", "base")
    git(root, "push", "-q", "origin", "main")
    git(root, "checkout", "-qb", BRANCH)
    (root / "greeting.txt").write_text("Hello, dear user!\nBye\n")
    git(root, "commit", "-qam", "greet the user")
    git(root, "push", "-q", "origin", BRANCH)
    git(root, "checkout", "-q", "main")
    for name, text in (("gh", FAKE_GH), ("claude", FAKE_CLAUDE)):
        (bin_ / name).write_text(text)
        (bin_ / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_STATE", str(state))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "T")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "T")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    monkeypatch.setattr(pr_merge, "POLL", 0)

    def set_pr(**kw):
        sha = git(root, "rev-parse", f"origin/{BRANCH}")
        pr = {"number": 12, "title": "feat: #7 - Say hello properly", "body": "Greets the user.\n\nCloses #7\n\n"
              "ADW ID: `20261104120000-abcdef123456`", "url": "https://github.com/o/r/pull/12", "state": "OPEN",
              "isDraft": False, "headRefName": BRANCH, "headRefOid": sha, "baseRefName": "main",
              "mergeable": "MERGEABLE", "statusCheckRollup": [], "comments": [], **kw}
        (state / "pr.json").write_text(json.dumps(pr))

    def calls():
        p = state / "calls.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
    return types.SimpleNamespace(root=root, origin=origin, state=state, set_pr=set_pr, calls=calls)


def main_moves_on(w):
    """Another PR changed the same line on main: the PR now conflicts."""
    other = w.root.parent / "other"
    git(w.root.parent, "clone", "-q", str(w.origin), str(other))
    (other / "greeting.txt").write_text("Hello\nBye from main\n")
    git(other, "commit", "-qam", "Another PR: a warmer farewell")
    (other / "greeting.txt").write_text("Hi\nBye from main\n")
    git(other, "commit", "-qam", "Another PR: shorter hello")
    git(other, "push", "-q", "origin", "main")


def run_merge(w, **kw):
    seen = []
    m = pr_merge.Merge(12, w.root, lambda k, s, n="": seen.append((k, s, n)), log=lambda t: None, **kw)
    return m, seen, m.run


def test_a_mergeable_pr_is_merged_without_touching_the_branch(world):
    world.set_pr(statusCheckRollup=[{"name": "ci", "conclusion": "SUCCESS"}])
    m, seen, run = run_merge(world)
    out = run()
    assert out["merged"] and out["method"] == "squash" and not out["updated"]
    assert ["pr", "merge", "12", "--squash", "--delete-branch"] in world.calls()
    assert ("update", "skipped", "No conflicts with main") in seen and ("checks", "done", "Checks pass") in seen


def test_conflicts_are_resolved_with_the_context_pushed_and_merged(world):
    main_moves_on(world)
    world.set_pr(mergeable="CONFLICTING")
    report_dir = world.root / "agents" / "20261104120000-abcdef123456"
    report_dir.mkdir(parents=True)
    (report_dir / messages.REPORT).write_text("## Decisions\nThe greeting names the user (the issue says so).")
    m, seen, run = run_merge(world)
    out = run()
    assert out["merged"] and out["resolved"] == ["greeting.txt"] and "kept the branch" in out["notes"]
    prompt = (world.state / "prompt.txt").read_text()
    for part in ("Say hello properly", "The greeting must name the user", "The greeting names the user",
                 "Another PR: a warmer farewell", "greet the user", "Conflicted files: greeting.txt"):
        assert part in prompt
    git(world.root, "fetch", "-q", "origin")
    assert git(world.root, "show", f"origin/{BRANCH}:greeting.txt") == "Hello, dear user!\nBye from main"
    parents = git(world.root, "log", "-1", "--format=%P", f"origin/{BRANCH}").split()
    assert len(parents) == 2                                     # a real merge commit, pushed without force
    assert any(c[:2] == ["pr", "comment"] and "Conflicts resolved" in c[-1] for c in world.calls())
    assert ["pr", "merge", "12", "--squash", "--delete-branch"] in world.calls()
    assert not (world.root / "trees" / "merge-pr-12").exists()      # the temporary worktree is gone
    assert ("resolve", "done", "1 file resolved") in seen


def test_the_workflows_own_worktree_is_used_when_clean_and_on_the_prs_commit(world):
    main_moves_on(world)
    wt = world.root / "trees" / "20261104120000-abcdef123456"
    git(world.root, "worktree", "add", "-q", str(wt), BRANCH)
    world.set_pr(mergeable="CONFLICTING")
    m, seen, run = run_merge(world)
    run()
    assert m.wt == wt and not m.own and wt.exists()              # left for the run's cleanup
    assert (wt / "greeting.txt").read_text() == "Hello, dear user!\nBye from main\n"


def test_the_suites_are_run_unless_the_merge_was_started_without_them(world):
    """Small PRs: with Ore's "Run the tests" left unticked, Claude checks by reading even where it could run them."""
    (world.root / "app" / "backend" / ".venv").mkdir(parents=True)
    (world.root / "adws").mkdir(exist_ok=True)
    (world.root / "adws" / "adw_run_suites.py").touch()
    for run_checks in (True, False):
        m = pr_merge.Merge(12, world.root, log=lambda t: None, run_checks=run_checks)
        m.pr, m.wt = {"baseRefName": "main", "headRefName": BRANCH}, world.root
        prompt = m.prompt(["greeting.txt"], world.root / "notes.md")
        assert ("adw_run_suites.py changed --base origin/main" in prompt) is run_checks
        assert ("Don't run the test suites" in prompt) is not run_checks


def test_the_prompt_asks_for_one_alembic_head_where_there_are_migrations(world):
    m = pr_merge.Merge(12, world.root, log=lambda t: None)
    m.pr, m.wt = {"baseRefName": "main", "headRefName": BRANCH}, world.root
    assert "Alembic" not in m.prompt(["greeting.txt"], world.root / "notes.md")
    (world.root / "app" / "backend").mkdir(parents=True, exist_ok=True)
    (world.root / "app" / "backend" / "alembic.ini").write_text("[alembic]")
    prompt = m.prompt(["greeting.txt"], world.root / "notes.md")
    assert "alembic heads" in prompt and "exactly one head" in prompt and "re-parent" in prompt


def test_claude_can_say_a_person_must_decide_and_nothing_is_pushed(world, monkeypatch):
    main_moves_on(world)
    world.set_pr(mergeable="CONFLICTING")
    monkeypatch.setenv("FAKE_CLAUDE", "cannot")
    before = git(world.root, "rev-parse", f"origin/{BRANCH}")
    m, seen, run = run_merge(world)
    with pytest.raises(pr_merge.MergeError, match="main removed the greeting"):
        run()
    git(world.root, "fetch", "-q", "origin")
    assert git(world.root, "rev-parse", f"origin/{BRANCH}") == before
    assert not any(c[:2] == ["pr", "merge"] for c in world.calls())
    assert ("merge", "skipped", "") in seen


def test_leftover_conflict_markers_stop_the_merge(world, monkeypatch):
    main_moves_on(world)
    world.set_pr(mergeable="CONFLICTING")
    monkeypatch.setenv("FAKE_CLAUDE", "markers")
    m, seen, run = run_merge(world)
    with pytest.raises(pr_merge.MergeError, match="Conflict markers are left in greeting.txt"):
        run()


def test_failing_checks_stop_it_and_merged_or_draft_prs_are_handled(world):
    world.set_pr(statusCheckRollup=[{"name": "tests", "conclusion": "FAILURE"}])
    with pytest.raises(pr_merge.MergeError, match=r"checks fail \(tests\)"):
        run_merge(world)[2]()
    world.set_pr(state="MERGED")
    assert run_merge(world)[2]()["already"]
    world.set_pr(isDraft=True)
    with pytest.raises(pr_merge.MergeError, match="draft"):
        run_merge(world)[2]()


def test_after_merging_the_main_checkout_is_fast_forwarded(world):
    world.set_pr()
    out = run_merge(world)[2]()
    head = git(world.root, "rev-parse", "HEAD")[:8]
    assert out["pulled"] == {"from": out["pulled"]["from"], "to": head, "adws": False}
    assert git(world.root, "rev-parse", "HEAD") == git(world.root, "rev-parse", "origin/main")


def test_the_main_checkout_is_left_alone_when_it_has_local_changes_or_another_branch(world):
    world.set_pr()
    before = git(world.root, "rev-parse", "HEAD")
    (world.root / "greeting.txt").write_text("edited here\n")
    m, seen, run = run_merge(world)
    out = run()
    assert out["merged"] and "local changes" in out["pulled"]["skipped"]
    assert git(world.root, "rev-parse", "HEAD") == before and (world.root / "greeting.txt").read_text() == "edited here\n"
    assert any(k == "pull" and s == "skipped" for k, s, _ in seen)
    git(world.root, "checkout", "-q", "greeting.txt")
    git(world.root, "checkout", "-qb", "mine")
    world.set_pr(state="MERGED")
    assert "is on mine, not main" in run_merge(world)[2]()["pulled"]["skipped"]


def test_a_merge_that_changes_the_adws_says_to_restart_ore(world, monkeypatch):
    git(world.root, "checkout", "-q", BRANCH)
    (world.root / "adws").mkdir()
    (world.root / "adws" / "x.py").write_text("print(1)\n")
    git(world.root, "add", ".")
    git(world.root, "commit", "-qm", "adws change")
    git(world.root, "push", "-q", "origin", BRANCH)
    git(world.root, "checkout", "-q", "main")
    world.set_pr()
    # gh's merge stand-in only flips the state: land the branch on main the way GitHub would
    real = pr_merge.Merge.merge

    def merge(self):
        method = real(self)
        other = world.root.parent / "landing"
        git(world.root.parent, "clone", "-q", str(world.origin), str(other))
        git(other, "merge", "-q", "--ff-only", f"origin/{BRANCH}")
        git(other, "push", "-q", "origin", "main")
        return method
    monkeypatch.setattr(pr_merge.Merge, "merge", merge)
    sent, results = [], []
    monkeypatch.setattr(ae, "REPO_ROOT", world.root)
    monkeypatch.setattr(ae, "emit", sent.append)
    monkeypatch.setattr(ae, "result", lambda summary, links=(), actions=(), data=None: results.append(summary))
    ae.merge_run("12")
    assert (world.root / "adws" / "x.py").exists()
    assert "restart Ore" in results[0]
    assert {s["key"]: s["status"] for s in sent[-1]["parts"][0]["steps"]}["pull"] == "done"


def test_check_state():
    assert pr_merge.check_state([]) == "none"
    assert pr_merge.check_state([{"conclusion": "SUCCESS"}, {"state": "PENDING"}]) == "pending"
    assert pr_merge.check_state([{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}]) == "failing"
    assert pr_merge.check_state([{"conclusion": "SUCCESS"}, {"conclusion": "SKIPPED"}]) == "passing"


# ---- the Ore trigger --------------------------------------------------------------------------

def test_ore_merge_runs_the_merge_as_a_run_with_steps(world, monkeypatch):
    world.set_pr()
    sent, results = [], []
    monkeypatch.setattr(ae, "REPO_ROOT", world.root)
    monkeypatch.setattr(ae, "emit", sent.append)
    monkeypatch.setattr(ae, "result", lambda summary, links=(), actions=(), data=None: results.append((summary, links)))
    assert ae.merge_request(["--model", "opus", "--ore-merge", "12"]) == "12"
    assert ae.merge_request(["items.md"]) is None
    assert ae.merge_request(["--ore-merge", "12", "--no-checks"]) == "12"
    ae.merge_run("12")
    last = sent[-1]["parts"][0]
    assert last["status"] == "done" and last["label"].startswith("PR #12 · feat: #7")
    assert {s["key"]: s["status"] for s in last["steps"]}["merge"] == "done"
    assert "merge_run" in sent[-1]["queries"]
    assert results[0][0].startswith("Merged PR #12 (squash)")


def test_the_report_is_kept_and_shown_on_the_part(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(steps, "steps_path", lambda adw_id: str(ae.steps_file(adw_id)))
    report = tmp_path / "r.md"
    report.write_text("## Summary\nDone.\n\n## Pending\n- 2 failures already on main")
    args = adw_report.build_parser().parse_args(["--adw-id", "a1", "result", "pr_opened", "--summary", "Done",
                                                 "--report-file", str(report)])
    assert adw_report.cmd_result(args) == 0
    assert (tmp_path / "agents" / "a1" / messages.REPORT).read_text().startswith("## Summary")
    assert ae.workflow_report({"adw_id": "a1", "status": "done"}).endswith("already on main")
    assert ae.workflow_report({"adw_id": "a1", "status": "running"}) is None
    report.write_text("  ")
    args.report_file = str(report)
    assert adw_report.cmd_result(args) == 2                      # an empty report isn't recorded
