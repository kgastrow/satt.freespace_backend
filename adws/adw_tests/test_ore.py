#!/usr/bin/env python3
"""Tests for the Ore trigger (adw_triggers/trigger_ore.py) and the progress sink in github.make_issue_comment.

Run: uv run --with pytest --with pydantic --with python-dotenv pytest adws/adw_tests/test_ore.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adw_triggers import trigger_ore as ae  # noqa: E402
from adw_modules import github  # noqa: E402

BATCH = """---
workspace: Nextcase
approved_at: 2026-11-03T13:44:45
items: 2
---

- [ ] Investigate mobile theatre list import failure
  In Nextcase, the mobile theatre list import is not creating cases.
  > "Nou, ons moet nou kerig daarna kyk" [00:34]

  Transcript:
  - 00:12 You: theaterluis imports, specifiek op mobile.

- [ ] Show the app version in the footer (due 2026-11-10)
  Support can't tell which version a user is on.
"""


def test_parse_markdown_batch(tmp_path):
    f = tmp_path / "batch.md"
    f.write_text(BATCH, encoding="utf-8")
    items = ae.parse_items(f)
    assert [i["id"] for i in items] == ["1", "2"]
    assert items[0]["title"] == "Investigate mobile theatre list import failure"
    assert items[0]["detail"] == "In Nextcase, the mobile theatre list import is not creating cases."
    assert "theaterluis imports" in items[0]["text"]          # the transcript goes to Claude too
    assert items[1]["title"].endswith("(due 2026-11-10)")


def test_parse_json_batch(tmp_path):
    f = tmp_path / "batch.json"
    f.write_text(json.dumps({"items": [{"title": "A", "detail": "d"}, {"title": "B"}]}), encoding="utf-8")
    assert [(i["id"], i["title"], i["detail"]) for i in ae.parse_items(f)] == [("1", "A", "d"), ("2", "B", "")]


class FakeRun:
    def __init__(self, n):
        self.s = {"items": [{"id": str(i), "title": f"Item {i}", "detail": "", "text": ""} for i in range(1, n + 1)]}


def test_groups_keep_every_item_exactly_once():
    run = FakeRun(4)
    groups = ae.normalise_groups(run, [{"title": "A", "item_ids": ["1", "2", "2", "99"]},
                                       {"title": "B", "item_ids": ["2", "3"]},
                                       {"title": "Empty", "item_ids": []}])
    assert [(g["title"], g["item_ids"]) for g in groups] == [("A", ["1", "2"]), ("B", ["3"]), ("Item 4", ["4"])]


def test_item_ids_can_be_written_as_item_n():
    groups = ae.normalise_groups(FakeRun(3), [{"title": "A", "summary": "s", "item_ids": ["Item 1", "#3"]}])
    assert [(g["title"], g["item_ids"]) for g in groups] == [("A", ["1", "3"]), ("Item 2", ["2"])]


def test_malformed_questions_are_dropped():
    qs = ae.valid_questions([
        {"question": "Broken", "header": "x", "options": {"0": None, "length": 3}, "multiSelect": False},
        {"question": "One option", "header": "x", "options": [{"label": "Only", "description": ""}]},
        {"question": "Good?", "header": "Good", "options": ["Yes", {"label": "No", "description": "nope"}],
         "multiSelect": False},
    ])
    assert qs == [{"question": "Good?", "header": "Good", "multiSelect": False,
                   "options": [{"label": "Yes", "description": ""}, {"label": "No", "description": "nope"}]}]


# Real `claude -p --output-format json` results (Claude Code 2.1.317), trimmed.
NOT_LOGGED_IN = {"type": "result", "is_error": True, "api_error_status": None, "result": "Not logged in · Please run /login"}
BAD_KEY = {"type": "result", "is_error": True, "api_error_status": 401, "result": "Invalid API key · Fix external API key"}
OVERLOADED = {"type": "result", "is_error": True, "api_error_status": 529, "result": "API Error: Overloaded"}


def test_sign_in_failures_are_recognised(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)      # e.g. set in the shell running the tests
    monkeypatch.setattr(ae.sys, "platform", "linux")                  # macOS has its own (Keychain) advice
    msg = ae.auth_problem(NOT_LOGGED_IN, "")
    assert "isn't signed in on" in msg and "/login" in msg and "setup-token" in msg and "Resume" in msg
    msg = ae.auth_problem(BAD_KEY, "")
    assert "rejected the API key" in msg and ".env" in msg
    assert ae.auth_problem(OVERLOADED, "") is None                # transient: retried, not an auth problem
    assert ae.auth_problem({}, "Error: Invalid API key") is not None  # no JSON, reason on stderr


def _fake_claude(tmp_path, monkeypatch, auth_status: dict, result: dict):
    calls = tmp_path / "calls"
    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\n"
                    f"echo CALL >> {calls}\n"
                    f"if [ \"$1\" = auth ]; then echo '{json.dumps(auth_status)}'; exit 0; fi\n"
                    f"echo '{json.dumps(result)}'; exit 1\n")
    fake.chmod(0o755)
    monkeypatch.setenv("CLAUDE_CODE_PATH", str(fake))
    monkeypatch.setattr(ae, "get_safe_subprocess_env", lambda: dict(os.environ))
    return calls


def test_turn_stops_at_once_when_not_signed_in(tmp_path, monkeypatch):
    calls = _fake_claude(tmp_path, monkeypatch, {"loggedIn": True, "authMethod": "claude.ai"}, NOT_LOGGED_IN)
    run = FakeRun(1)
    run.s.update(session_id=None)
    run.save = lambda: None
    try:
        ae.claude_turn(run, "hello")
        raise AssertionError("expected ClaudeAuthError")
    except ae.ClaudeAuthError as e:
        assert "/login" in str(e)
    assert len(calls.read_text().splitlines()) == 1             # no pointless retry


def test_auth_check_before_starting(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(ae.sys, "platform", "linux")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _fake_claude(tmp_path, monkeypatch, {"loggedIn": True, "authMethod": "claude.ai"}, {})
    assert ae.check_claude_auth() == "your Claude subscription"
    _fake_claude(tmp_path, monkeypatch, {"loggedIn": False, "authMethod": "none"}, {})
    try:
        ae.check_claude_auth()
        raise AssertionError("expected ClaudeAuthError")
    except ae.ClaudeAuthError as e:
        assert "isn't signed in" in str(e) or "API key" in str(e)


def test_progress_comments_become_phase_message_and_pr(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    g = {"issue_number": "42", "offset": 0}
    path = ae.progress_file(g)
    path.parent.mkdir(parents=True)
    comments = ["[ADW-AGENTS] 20260103-abc_ops: ✅ Building implementation plan",
                "[ADW-AGENTS] 20260103-abc_ops: ✅ Pull request created: https://github.com/o/r/pull/77",
                "[ADW-AGENTS] 20260103-abc_ops: ✅ SDLC workflow completed\n- [x] plan"]
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"comment": comments[0]}) + "\n")
    ae.read_progress(g)
    assert g["message"] == "✅ Building implementation plan" and g["phase"] in ("Planning", "Building")
    with open(path, "a", encoding="utf-8") as f:
        for c in comments[1:]:
            f.write(json.dumps({"comment": c}) + "\n")
    ae.read_progress(g)
    assert g["pr_url"] == "https://github.com/o/r/pull/77" and g["completed"] and g["progress"] == 1.0
    assert g["message"].startswith("✅ SDLC workflow completed")


def test_make_issue_comment_records_progress_even_when_github_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(github, "check_gh_auth", lambda: "not logged in")
    monkeypatch.setattr(github.os.path, "abspath", lambda p: str(tmp_path / "adws" / "adw_modules" / "github.py"))
    try:
        github.make_issue_comment("7", "✅ Plan committed")
    except RuntimeError:
        pass
    line = json.loads((tmp_path / "agents" / "progress" / "issue-7.jsonl").read_text(encoding="utf-8"))
    assert line["issue"] == "7" and line["comment"] == "✅ Plan committed"


def test_cleanup_of_a_dry_run_removes_its_state_and_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    run = ae.Run(tmp_path / "agents" / "ore" / "r1")
    run.dir.mkdir(parents=True)
    g = {"title": "Footer version", "status": "running", "issue_number": "dry-r1-1", "issue_url": None,
         "adw_id": "a1", "pid": None, "started_at": 0}
    run.s = {"run_id": "r1", "dry_run": True, "groups": [g], "phase": "workflows", "trigger_pid": None}
    run.save()
    (tmp_path / "agents" / "a1").mkdir()
    ae.progress_file(g).parent.mkdir(parents=True)
    ae.progress_file(g).write_text("{}\n", encoding="utf-8")
    out = []
    monkeypatch.setattr(ae, "result", lambda summary, **kw: out.append(summary))
    monkeypatch.setattr(ae, "status", lambda *a, **kw: None)
    ae.clean(run.dir, {"github"})               # GitHub is never touched for a dry run
    assert not run.dir.exists() and not (tmp_path / "agents" / "a1").exists()
    assert not ae.progress_file(g).exists()
    assert out == ["Cleaned up 1 workflow"]


def test_cleanup_failure_keeps_state_and_retries_only_what_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    run = ae.Run(tmp_path / "agents" / "ore" / "r2")
    run.dir.mkdir(parents=True)
    g = {"title": "Made to order", "status": "running", "issue_number": "23",
         "issue_url": "https://github.com/o/r/issues/23", "adw_id": None, "pid": None}
    run.s = {"run_id": "r2", "dry_run": False, "groups": [g], "phase": "workflows"}
    run.save()
    calls = []
    monkeypatch.setattr(ae, "close_on_github", lambda g, branch: calls.append(g["issue_number"]) or ["gh is down"])
    monkeypatch.setattr(ae, "status", lambda *a, **kw: None)

    class Failed(Exception):
        pass

    def fail(message, exit_code=1):
        raise Failed(message)

    monkeypatch.setattr(ae, "error", fail)
    try:
        ae.clean(run.dir, {"github"})
        raise AssertionError("expected the cleanup to fail")
    except Failed as e:
        assert "Made to order: gh is down" in str(e)
    assert run.dir.exists() and not ae.Run(run.dir).s["groups"][0].get("closed")
    monkeypatch.setattr(ae, "close_on_github", lambda g, branch: calls.append(g["issue_number"]) or [])
    monkeypatch.setattr(ae, "result", lambda summary, **kw: calls.append(summary))
    ae.clean(run.dir, {"github"})
    assert calls == ["23", "23", "Cleaned up 1 workflow and closed them on GitHub"] and not run.dir.exists()


def test_gh_auth_check_uses_only_the_active_account(monkeypatch):
    seen = []

    class P:
        returncode, stderr = 0, ""

    monkeypatch.setattr(github.subprocess, "run", lambda cmd, **kw: seen.append(cmd) or P())
    assert github.check_gh_auth() is None and seen == [["gh", "auth", "status", "--active"]]


def test_failed_workflows_fail_the_run_and_resume_reruns_only_them(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    run = ae.Run(tmp_path / "agents" / "ore" / "r3")
    run.dir.mkdir(parents=True)
    ok = {"title": "Footer", "status": "done", "issue_number": "dry-r3-1", "issue_url": None, "adw_id": "a-ok",
          "progress": 1.0}
    bad = {"title": "Made to order", "status": "failed", "issue_number": "dry-r3-2", "issue_url": None,
           "adw_id": "a-bad", "pid": None, "progress": 0.05, "phase": "Routing", "message": "Stopped with exit code 1"}
    run.s = {"run_id": "r3", "dry_run": True, "groups": [ok, bad], "phase": "workflows"}
    run.save()
    (tmp_path / "agents" / "a-bad").mkdir()
    monkeypatch.setattr(ae, "status", lambda *a, **kw: None)

    class Failed(Exception):
        pass

    def fail(message, exit_code=1):
        raise Failed(message)

    monkeypatch.setattr(ae, "error", fail)
    try:
        ae.workflows(run)
        raise AssertionError("expected the run to fail")
    except Failed as e:
        assert "1 of 2 workflows failed: Made to order" in str(e) and "Resume" in str(e)

    assert ae.retry_failed(run) == 1
    assert run.s["phase"] == "workflows" and ok["status"] == "done" and ok["adw_id"] == "a-ok"
    assert bad["status"] == "queued" and "adw_id" not in bad and "progress" not in bad
    assert bad["issue_number"] == "dry-r3-2"                  # same issue, no new one
    assert not (tmp_path / "agents" / "a-bad").exists()      # the failed ADW's leftovers are gone
    assert ae.retry_failed(run) == 0                          # nothing failed: nothing changes


def test_resume_before_the_workflows_start_goes_on_from_the_phase(tmp_path, monkeypatch):
    """Ore was restarted while the groups waited for the user to start them: their groups have no status yet."""
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    run = ae.Run(tmp_path / "agents" / "ore" / "r4")
    run.dir.mkdir(parents=True)
    group = {"title": "Home carousel", "summary": "Text below the cover", "item_ids": ["1"]}
    for phase in ("clarify", "review", "issues"):
        run.s = {"run_id": "r4", "groups": [dict(group)], "phase": phase, "pending": {"key": "k"}}
        assert ae.retry_failed(run) == 0
        assert run.s["phase"] == phase and "status" not in run.s["groups"][0]


def test_an_items_reference_images_reach_the_prompt_and_the_issue(tmp_path):
    f = tmp_path / "batch.md"
    f.write_text("- [ ] Match the mockup\n  Make the event page look like this.\n"
                 "  Image: /home/u/inbox/b-images/01-mockup.png\n\n- [ ] No picture\n", encoding="utf-8")
    items = ae.parse_items(f)
    assert items[0]["images"] == ["/home/u/inbox/b-images/01-mockup.png"] and items[1]["images"] == []
    assert items[0]["detail"] == "Make the event page look like this."
    assert "open them with Read" in ae.items_prompt(items, "a note")
    section = ae.images_section(items[0]["images"])
    assert "## Reference images" in section and "`/home/u/inbox/b-images/01-mockup.png`" in section
    assert ae.images_section([]) == ""
    j = tmp_path / "batch.json"
    j.write_text(json.dumps({"items": [{"title": "A", "images": ["/x/a.png"]}]}), encoding="utf-8")
    assert ae.parse_items(j)[0]["images"] == ["/x/a.png"]


def test_an_items_acceptance_criteria_reach_the_planning_prompt_and_the_issue(tmp_path):
    f = tmp_path / "batch.md"
    f.write_text("- [ ] Refund export\n  Export the refunds as CSV.\n  Acceptance criteria:\n"
                 "  - The CSV has a date column in YYYY-MM-DD.\n  - Cancelled refunds are left out.\n\n"
                 "  Transcript:\n  - 00:12 You: the refunds export.\n\n- [ ] No criteria\n", encoding="utf-8")
    items = ae.parse_items(f)
    assert items[0]["criteria"] == ["The CSV has a date column in YYYY-MM-DD.", "Cancelled refunds are left out."]
    assert items[0]["detail"] == "Export the refunds as CSV." and items[1]["criteria"] == []
    prompt = ae.items_prompt(items, "a meeting")
    assert prompt.count("Cancelled refunds are left out.") == 1 and "agreed with the user in Ore" in prompt
    assert "agreed with the user" not in ae.items_prompt(items[1:], "a meeting")
    j = tmp_path / "batch.json"
    j.write_text(json.dumps({"items": [{"title": "A", "criteria": ["Shows the version.", " "]}, {"title": "B"}]}),
                 encoding="utf-8")
    items = ae.parse_items(j)
    assert items[0]["criteria"] == ["Shows the version."] and items[1]["criteria"] == []
    prompt = ae.items_prompt(items, "a note")
    assert "Acceptance criteria:\n- Shows the version." in prompt and "agreed with the user in Ore" in prompt
    section = ae.criteria_section(["Shows the version."])
    assert "## Acceptance criteria agreed in Ore" in section and "- Shows the version." in section
    assert ae.criteria_section([]) == ""
