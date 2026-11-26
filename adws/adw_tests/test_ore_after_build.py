#!/usr/bin/env python3
"""Tests for Ore's project manager after the build (trigger_ore.py): the four specialists (doctor, pr_reviewer,
merge_planner, closer) through the consult query with version 3 requests, the read-only tools they get, and the
revert query (a revert pull request opened in a temporary worktree).

Run: uv run --with pytest --with pydantic --with python-dotenv pytest adws/adw_tests/test_ore_after_build.py
(conftest.py gives every test its own ~/.adw folder through ADW_SHARED_DIR.)
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adw_triggers import trigger_ore as ae  # noqa: E402

AFTER_BUILD = ("doctor", "pr_reviewer", "merge_planner", "closer")
TEMPLATE_ROOT = Path(__file__).resolve().parents[2]


def _lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]


# ---- the specialists ------------------------------------------------------------------------------------------

RUN = {"id": 17, "label": "Refund export", "status": "failed", "error": "Test failed", "message": "Testing",
       "phase": "building", "log_tail": ["pytest tests/test_refunds.py", "FAILED test_export_has_dates"],
       "parts": [{"key": "issue-41", "label": "Refund export", "status": "failed", "steps": "test failed",
                  "links": [["PR #212", "https://github.com/o/r/pull/212"]]}]}
CARD = {"id": "g-3", "title": "Refunds", "design": "specs/designs/refunds.html", "test_plan": "Test the CSV.",
        "risks": [{"title": "Large export", "severity": "low"}],
        "items": [{"id": "41", "title": "Refund export", "detail": "CSV", "criteria": ["Has a date column."],
                   "conversation": [{"author": "you", "text": "See the mock",
                                     "attachments": [{"path": ".ore/pm/9/files/mock.png"}]}]}],
        "prs": [{"number": 212, "url": "https://github.com/o/r/pull/212", "state": "open", "checks": "passing",
                 "review": "none", "head": "abc1234"}]}
ANSWERS = {
    "doctor": {"diagnosis": "The date test fails.", "action": "follow_up", "follow_up": "Add the date column.",
               "part": "issue-41", "messages": []},
    "pr_reviewer": {"prs": [{"number": 212, "verdict": "gaps", "gaps": ["No date column."], "note": "Close."}],
                    "messages": []},
    "merge_planner": {"order": [214, 212], "notes": [{"number": 212, "note": "Update after #214."}]},
    "closer": {"items": [{"id": "41", "done": False, "note": "No dates."}],
               "leftovers": [{"title": "Dates in the export", "detail": "Add a date column.", "item": "41"}]},
}


def _request(tmp_path, monkeypatch, name: str) -> Path:
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    folder = tmp_path / ".ore" / "pm" / "9"
    (folder / "files").mkdir(parents=True)
    (folder / "files" / "mock.png").write_bytes(b"png")
    req = {"specialist": name, "version": 3, "workspace": {"name": "OneFan", "slug": "onefan"}, "goals": "Refunds.",
           "schema": {"type": "object"}, "minutes": 10}
    if name == "doctor":
        req["run"] = RUN
    else:
        req["card"] = CARD
    (folder / "request.json").write_text(json.dumps(req), encoding="utf-8")
    return folder / "request.json"


def _fake_claude(calls, out):
    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return type("P", (), {"returncode": 0, "stdout": json.dumps(out), "stderr": ""})()
    return fake_run


@pytest.mark.parametrize("name", AFTER_BUILD)
def test_each_specialist_has_a_built_in_prompt_and_a_repo_prompt(name, monkeypatch, tmp_path):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)                 # no adws/specialists/: the built-in copy
    fallback = ae.specialist_prompt(name)
    assert fallback == ae.SPECIALIST_FALLBACKS[name] and "read-only" in fallback and "schema" in fallback
    monkeypatch.setattr(ae, "REPO_ROOT", TEMPLATE_ROOT)            # the template's own adws/specialists/<name>.md
    text = ae.specialist_prompt(name)
    assert text != fallback and "never commit" in text and "given schema" in text


@pytest.mark.parametrize("name", AFTER_BUILD)
def test_the_version_3_request_reaches_the_session(name, tmp_path, monkeypatch, capsys):
    path = _request(tmp_path, monkeypatch, name)
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude(calls, {
        "type": "result", "structured_output": ANSWERS[name], "session_id": "s-3", "total_cost_usd": 0.2}))
    assert ae.run_query("consult", [name, str(path)]) == 0
    assert _lines(capsys) == [{"type": "answer", "query": "consult", "data": {
        "result": ANSWERS[name], "session_id": "s-3", "cost_usd": 0.2}}]
    cmd, kw = calls[0]
    assert cmd[cmd.index("--append-system-prompt") + 1] == ae.SPECIALIST_FALLBACKS[name]
    assert kw["timeout"] == 10 * 60 and kw["cwd"] == tmp_path
    text = kw["input"]
    sent = json.loads(text[text.index("Ore's request"):][text[text.index("Ore's request"):].index("{"):])
    if name == "doctor":
        assert sent["run"] == RUN and "card" not in sent
        assert "FAILED test_export_has_dates" in text
    else:
        assert sent["card"] == CARD and "run" not in sent
        assert sent["card"]["items"][0]["criteria"] == ["Has a date column."]
        assert sent["card"]["design"] == "specs/designs/refunds.html" and sent["card"]["prs"][0]["number"] == 212
        # files attached earlier in a card item's conversation are pointed out (and must be in the request's folder)
        assert str((tmp_path / ".ore" / "pm" / "9" / "files" / "mock.png").resolve()) in text
    assert "schema" not in sent and sent["workspace"]["slug"] == "onefan"
    assert not path.parent.exists()


def test_the_consult_session_may_read_pull_requests_but_change_nothing(tmp_path, monkeypatch, capsys):
    path = _request(tmp_path, monkeypatch, "pr_reviewer")
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude(calls, {"structured_output": ANSWERS["pr_reviewer"]}))
    assert ae.run_query("consult", ["pr_reviewer", str(path)]) == 0
    cmd, _kw = calls[0]
    allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")]
    for tool in ("Bash(gh pr diff:*)", "Bash(gh pr checks:*)", "Bash(gh pr view:*)", "Bash(gh pr list:*)",
                 "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)"):
        assert tool in allowed
    assert not any(a.startswith(("Bash(gh pr merge", "Bash(gh pr create", "Bash(gh pr comment", "Bash(git push",
                                 "Bash(git commit")) or a == "Bash" for a in allowed)
    assert cmd[cmd.index("--permission-mode") + 1] == "plan"
    assert {"Edit", "Write"} <= set(cmd[cmd.index("--disallowedTools"):])


# ---- revert ---------------------------------------------------------------------------------------------------

MERGE_SHA = "0123456789abcdef0123456789abcdef01234567"


class FakeGh:
    def __init__(self, pr: dict, existing: list | None = None, create_fails: bool = False):
        self.pr, self.existing, self.create_fails, self.calls = pr, existing or [], create_fails, []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("pr", "view"):
            return json.dumps(self.pr)
        if args[:2] == ("pr", "list"):
            return json.dumps(self.existing)
        if args[:2] == ("pr", "create"):
            if self.create_fails:
                raise ae.QueryError("gh pr create failed: no permission")
            return "https://github.com/o/r/pull/230\n"
        raise AssertionError(f"unexpected gh call {args}")


class FakeGit:
    """Stands in for subprocess.run for git: records each call and its cwd; `worktree add` creates the folder."""

    def __init__(self, root: Path, parents: int = 1, conflict: bool = False):
        self.root, self.parents, self.conflict, self.calls = root, parents, conflict, []

    def __call__(self, cmd, **kw):
        assert cmd[0] == "git", cmd
        args, cwd = cmd[1:], Path(kw["cwd"])
        self.calls.append((args, cwd))
        out, code = "", 0
        if args[:2] == ["worktree", "add"]:
            Path(args[-2]).mkdir(parents=True)
        elif args[:2] == ["worktree", "remove"]:
            import shutil
            shutil.rmtree(args[-1], ignore_errors=True)
        elif args[0] == "rev-list":
            out = " ".join([MERGE_SHA] + ["f" * 40, "e" * 40][:self.parents]) + "\n"
        elif args[0] == "revert" and "--abort" not in args and self.conflict:
            code = 1
        elif args[:2] == ["diff", "--name-only"]:
            out = "app/models.py\napp/views.py\n" if self.conflict else ""
        return type("P", (), {"returncode": code, "stdout": out, "stderr": "CONFLICT" if code else ""})()

    def ran(self, *prefix) -> list:
        return [(a, c) for a, c in self.calls if tuple(a[:len(prefix)]) == prefix]


def _merged_pr(**extra) -> dict:
    return {"number": 212, "url": "https://github.com/o/r/pull/212", "state": "MERGED", "title": "Refund export",
            "mergeCommit": {"oid": MERGE_SHA}, "baseRefName": "main", **extra}


@pytest.fixture
def revert_env(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(ae, "_repo", lambda: "o/r")

    def setup(pr: dict, **git_kw):
        gh, git = FakeGh(pr, **{k: git_kw.pop(k) for k in ("existing", "create_fails") if k in git_kw}), \
            FakeGit(tmp_path, **git_kw)
        monkeypatch.setattr(ae, "_gh", gh)
        monkeypatch.setattr(ae.subprocess, "run", git)
        return gh, git
    return setup


def test_revert_is_advertised():
    assert "revert" in ae.QUERIES


def test_revert_opens_a_pull_request_from_a_temporary_worktree(tmp_path, revert_env, capsys):
    gh, git = revert_env(_merged_pr(), parents=1)               # a squash merge: one parent
    assert ae.run_query("revert", ["212"]) == 0
    assert _lines(capsys) == [{"type": "answer", "query": "revert",
                               "data": {"number": 230, "url": "https://github.com/o/r/pull/230"}}]
    tree = tmp_path / "trees" / "revert-pr-212"
    branch = f"revert-212-{MERGE_SHA[:7]}"
    (add, cwd), = git.ran("worktree", "add")
    assert add == ["worktree", "add", "-q", "-B", branch, str(tree), "origin/main"] and cwd == tmp_path
    (rev, cwd), = git.ran("revert")
    assert rev == ["revert", "--no-edit", MERGE_SHA] and cwd == tree     # no -m for a single-parent commit
    (push, cwd), = git.ran("push")
    assert push == ["push", "-q", "-u", "origin", branch] and cwd == tree
    # everything that changes files happens in the worktree, never in the main checkout
    assert all(c == tree for a, c in git.calls if a[0] in ("revert", "push", "commit", "checkout", "reset"))
    create = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    assert create[create.index("--title") + 1] == 'Revert "Refund export"'
    assert create[create.index("--head") + 1] == branch and create[create.index("--base") + 1] == "main"
    body = create[create.index("--body") + 1]
    assert "#212" in body and "https://github.com/o/r/pull/212" in body
    assert not tree.exists() and git.ran("worktree", "remove") and git.ran("branch", "-D", branch)
    assert not git.ran("push", "-q", "origin", "--delete")


def test_a_merge_commit_is_reverted_against_its_first_parent(revert_env, capsys):
    _gh, git = revert_env(_merged_pr(), parents=2)
    assert ae.run_query("revert", ["#212"]) == 0
    (rev, _cwd), = git.ran("revert")
    assert rev == ["revert", "--no-edit", "-m", "1", MERGE_SHA]


@pytest.mark.parametrize("state", ["OPEN", "CLOSED"])
def test_revert_refuses_a_pull_request_that_isnt_merged(state, revert_env, capsys):
    _gh, git = revert_env(_merged_pr(state=state, mergeCommit=None))
    assert ae.run_query("revert", ["212"]) == 1
    line = _lines(capsys)[0]
    assert line["type"] == "error" and "not merged" in line["message"] and state.lower() in line["message"]
    assert not git.calls                                          # nothing touched


def test_revert_needs_a_number(revert_env, capsys):
    revert_env(_merged_pr())
    assert ae.run_query("revert", []) == 1
    assert "pull request number" in _lines(capsys)[0]["message"]


def test_a_conflicting_revert_is_refused_and_cleaned_up(tmp_path, revert_env, capsys):
    gh, git = revert_env(_merged_pr(), parents=2, conflict=True)
    assert ae.run_query("revert", ["212"]) == 1
    msg = _lines(capsys)[0]["message"]
    assert "can't be reverted automatically" in msg and "app/models.py" in msg and "by hand" in msg
    assert git.ran("revert", "--abort")
    assert not git.ran("push") and not any(c[:2] == ("pr", "create") for c in gh.calls)
    assert not (tmp_path / "trees" / "revert-pr-212").exists()
    assert git.ran("branch", "-D", f"revert-212-{MERGE_SHA[:7]}")


def test_a_failed_pull_request_removes_the_pushed_branch(tmp_path, revert_env, capsys):
    _gh, git = revert_env(_merged_pr(), create_fails=True)
    assert ae.run_query("revert", ["212"]) == 1
    assert "no permission" in _lines(capsys)[0]["message"]
    branch = f"revert-212-{MERGE_SHA[:7]}"
    assert git.ran("push", "-q", "origin", "--delete", branch)
    assert not (tmp_path / "trees" / "revert-pr-212").exists()


def test_an_open_revert_from_an_earlier_try_is_answered_as_it_is(revert_env, capsys):
    _gh, git = revert_env(_merged_pr(), existing=[{"number": 229, "url": "https://github.com/o/r/pull/229"}])
    assert ae.run_query("revert", ["212"]) == 0
    assert _lines(capsys)[0]["data"] == {"number": 229, "url": "https://github.com/o/r/pull/229"}
    assert not git.calls
