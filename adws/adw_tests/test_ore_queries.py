#!/usr/bin/env python3
"""Tests for Ore's queries to the trigger (trigger_ore.py --ore-query machine|prs|merge|ask|items|consult), the machine view and the
machine-wide Claude usage file (adw_modules/resources.py), and the items each part carries.

Run: uv run --with pytest --with pydantic --with python-dotenv pytest adws/adw_tests/test_ore_queries.py
(conftest.py gives every test its own ~/.adw folder through ADW_SHARED_DIR.)
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adw_modules import agent, messages, resources  # noqa: E402
from adw_triggers import trigger_ore as ae  # noqa: E402

# Real rate_limit_events from `claude -p --output-format stream-json` (Claude Code 2.1), and the five-hour shape.
SEVEN_DAY = {"type": "rate_limit_event", "rate_limit_info": {
    "status": "allowed", "resetsAt": 1794214800, "rateLimitType": "seven_day", "overageStatus": "allowed",
    "overageResetsAt": 1796083200, "isUsingOverage": False,
    "unifiedWindows": {"seven_day": {"utilization": 0.31, "resetsAt": 1794214800, "status": "allowed"}}}}
FIVE_HOUR = {"type": "rate_limit_event", "rate_limit_info": {
    "status": "allowed_warning", "resetsAt": 1794146400, "rateLimitType": "five_hour",
    "unifiedWindows": {"five_hour": {"utilization": 0.785, "resetsAt": 1794146400, "status": "allowed_warning"},
                       "seven_day": {"utilization": 0.55, "resetsAt": 1794214800, "status": "allowed"}}}}
NOW = 1794140000                         # before both resets


def _lines(capsys) -> list[dict]:
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def _no_redis_server(monkeypatch):
    monkeypatch.setattr(resources, "_redis_count", [16])


# ---- dispatch ----------------------------------------------------------------

def test_query_request_is_found_before_anything_else(monkeypatch):
    monkeypatch.delenv("ORE_QUERY", raising=False)
    assert ae.query_request(["--ore-query", "merge", "47"]) == ("merge", ["47"])
    assert ae.query_request(["--model", "opus", "--ore-query", "prs"]) == ("prs", [])   # workspace args first
    assert ae.query_request(["batch.md"]) is None
    monkeypatch.setenv("ORE_QUERY", "machine")
    assert ae.query_request(["--ore-query"]) == ("machine", [])


def test_answer_is_one_line(monkeypatch, capsys):
    monkeypatch.setattr(ae, "query_machine", lambda: {"name": "Mac mini", "workflows": {"used": 1, "max": 4}})
    assert ae.run_query("machine", []) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert json.loads(out) == {"type": "answer", "query": "machine",
                               "data": {"name": "Mac mini", "workflows": {"used": 1, "max": 4}}}


def test_problems_are_an_error_line(monkeypatch, capsys):
    assert ae.run_query("weather", []) == 1
    err = _lines(capsys)
    assert len(err) == 1 and err[0]["type"] == "error" and "machine, prs, merge" in err[0]["message"]

    def boom():
        raise ae.QueryError("gh pr list failed: HTTP 502")
    monkeypatch.setattr(ae, "query_prs", boom)
    assert ae.run_query("prs", []) == 1
    assert _lines(capsys) == [{"type": "error", "message": "gh pr list failed: HTTP 502"}]


def test_main_answers_a_query_without_a_batch(monkeypatch, capsys):
    monkeypatch.setattr(ae.sys, "argv", ["trigger_ore.py", "--ore-query", "prs"])
    monkeypatch.setattr(ae, "query_prs", lambda: {"prs": []})
    with pytest.raises(SystemExit) as exit_:
        ae.main()
    assert exit_.value.code == 0
    assert _lines(capsys) == [{"type": "answer", "query": "prs", "data": {"prs": []}}]


# ---- prs ---------------------------------------------------------------------

# gh pr list --json ... (trimmed from Ayzer-ai/OneFan)
GH_PRS = [
    {"number": 35, "title": "feat: #25 - Add manufacture-to-order option", "url": "https://github.com/o/r/pull/35",
     "headRefName": "feature-issue-25-adw-20261104084824-5d3393cca422-made-to-order-physical-products",
     "body": "## Summary\n...\nCloses #25\n\nADW ID: `20261104084824-5d3393cca422`",
     "closingIssuesReferences": [{"number": 25, "url": "https://github.com/o/r/issues/25"}],
     "statusCheckRollup": [], "reviewDecision": "", "state": "OPEN", "mergedAt": None, "closedAt": None,
     "mergeable": "MERGEABLE"},
    {"number": 36, "title": "fix: footer", "url": "https://github.com/o/r/pull/36",
     "headRefName": "bug-issue-27-adw-20261104131547-6456c2525e39-footer-version", "body": "",
     "closingIssuesReferences": [],
     "statusCheckRollup": [
         {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS", "name": "backend-test"},
         {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": "", "name": "frontend-test"}],
     "reviewDecision": "REVIEW_REQUIRED", "state": "OPEN", "mergedAt": None, "closedAt": None,
     "mergeable": "CONFLICTING"},
    {"number": 22, "title": "Merge bughunt", "url": "https://github.com/o/r/pull/22", "headRefName": "bughunt/2026-07-26",
     "body": "14 commits of fixes", "closingIssuesReferences": [],
     "statusCheckRollup": [{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}],
     "reviewDecision": "", "state": "MERGED", "mergedAt": "2026-07-28T15:47:51Z", "mergeable": "UNKNOWN"},
]
GH_RECENT = [
    {"number": 33, "title": "feat: tickets", "url": "https://github.com/o/r/pull/33",
     "headRefName": "feature-issue-26-adw-a1b2c3d4-get-tickets", "body": "", "closingIssuesReferences": [],
     "statusCheckRollup": [
         {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"},
         {"__typename": "StatusContext", "state": "SUCCESS", "context": "vercel"},
         {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "NEUTRAL"}],
     "reviewDecision": "APPROVED", "state": "MERGED", "mergedAt": "2026-11-03T10:00:00Z",
     "closedAt": "2026-11-03T10:00:00Z", "mergeable": "UNKNOWN"},
    {"number": 34, "title": "chore: copy", "url": "https://github.com/o/r/pull/34", "headRefName": "my-branch",
     "body": "Done by hand from ADW.\n\nADW ID: `20261101090000-abcdefabcdef`\nFixes #24",
     "closingIssuesReferences": [],
     "statusCheckRollup": [{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "TIMED_OUT"}],
     "reviewDecision": "CHANGES_REQUESTED", "state": "CLOSED", "mergedAt": None,
     "closedAt": "2026-11-02T10:00:00Z", "mergeable": "UNKNOWN"},
    GH_PRS[1],                                       # listed once only
]


def test_check_and_review_mapping():
    assert ae.check_state([]) == "none" and ae.check_state(None) == "none"
    assert ae.check_state([{"status": "COMPLETED", "conclusion": "SUCCESS"},
                           {"status": "COMPLETED", "conclusion": "SKIPPED"}]) == "passing"
    assert ae.check_state([{"status": "COMPLETED", "conclusion": "SUCCESS"},
                           {"status": "QUEUED", "conclusion": ""}]) == "pending"
    assert ae.check_state([{"status": "IN_PROGRESS"}, {"status": "COMPLETED", "conclusion": "CANCELLED"}]) == "failing"
    assert ae.check_state([{"__typename": "StatusContext", "state": "PENDING"}]) == "pending"
    assert ae.check_state([{"__typename": "StatusContext", "state": "ERROR"}]) == "failing"
    assert [ae.review_state(d) for d in ("APPROVED", "REVIEW_REQUIRED", "CHANGES_REQUESTED", "", None)] == \
        ["approved", "requested", "changes", "none", "none"]


def test_prs_lists_adw_prs_normalised(monkeypatch):
    calls = []

    def gh(*args):
        calls.append(args)
        return json.dumps(GH_PRS if "open" in args else GH_RECENT)
    monkeypatch.setattr(ae, "_gh", gh)
    monkeypatch.setattr(ae, "_repo", lambda: "o/r")
    prs = ae.query_prs()["prs"]
    assert len(calls) == 2
    assert any(a[:2] == ("pr", "list") and "closed" in a and any(str(x).startswith("closed:>=") for x in a)
               for a in calls)
    by = {p["number"]: p for p in prs}
    assert sorted(by) == [33, 34, 35, 36]                         # #22 isn't an ADW PR; #36 only once
    assert by[35] == {"number": 35, "title": "feat: #25 - Add manufacture-to-order option",
                      "url": "https://github.com/o/r/pull/35", "issue": 25, "adw_id": "20261104084824-5d3393cca422",
                      "branch": GH_PRS[0]["headRefName"], "checks": "none", "review": "none", "state": "open",
                      "mergeable": True}
    assert (by[36]["issue"], by[36]["checks"], by[36]["review"], by[36]["mergeable"]) == (27, "pending", "requested",
                                                                                          False)
    assert (by[33]["state"], by[33]["checks"], by[33]["review"], by[33]["merged_at"], by[33]["issue"]) == \
        ("merged", "passing", "approved", "2026-11-03T10:00:00Z", 26)
    assert "mergeable" not in by[33]
    assert (by[34]["state"], by[34]["checks"], by[34]["review"], by[34]["issue"], by[34]["adw_id"]) == \
        ("closed", "failing", "changes", 24, "20261101090000-abcdefabcdef")


# ---- merge (gh mocked) --------------------------------------------------------

class FakeGh:
    def __init__(self, pr: dict, allowed: dict | None = None, merge_fails: bool = False, merged_anyway: bool = False):
        self.pr, self.calls, self.merge_fails, self.merged_anyway = pr, [], merge_fails, merged_anyway
        self.allowed = allowed or {"squashMergeAllowed": True, "mergeCommitAllowed": True, "rebaseMergeAllowed": True}

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("repo", "view"):
            return json.dumps(self.allowed)
        if args[:2] == ("pr", "view"):
            if "state" == args[-1]:
                return json.dumps({"state": "MERGED" if self.merged_anyway else self.pr["state"]})
            return json.dumps(self.pr)
        if args[:2] == ("pr", "merge"):
            if self.merge_fails:
                raise ae.QueryError("gh pr merge failed: failed to delete local branch")
            return ""
        raise AssertionError(args)


ADW_PR = {"number": 35, "url": "https://github.com/o/r/pull/35", "state": "OPEN",
          "headRefName": "feature-issue-25-adw-20261104084824-5d3393cca422-made-to-order", "body": ""}


def test_merge_squashes_an_open_adw_pr(monkeypatch, capsys):
    gh = FakeGh(dict(ADW_PR))
    monkeypatch.setattr(ae, "_gh", gh)
    monkeypatch.setattr(ae, "_repo", lambda: "o/r")
    assert ae.run_query("merge", ["35"]) == 0
    assert _lines(capsys) == [{"type": "answer", "query": "merge", "data": {
        "merged": True, "number": 35, "url": "https://github.com/o/r/pull/35", "method": "squash"}}]
    merge = next(c for c in gh.calls if c[:2] == ("pr", "merge"))
    assert merge == ("pr", "merge", "35", "-R", "o/r", "--squash", "--delete-branch")


def test_merge_uses_the_allowed_method(monkeypatch):
    gh = FakeGh(dict(ADW_PR), allowed={"squashMergeAllowed": False, "mergeCommitAllowed": True})
    monkeypatch.setattr(ae, "_gh", gh)
    monkeypatch.setattr(ae, "_repo", lambda: "o/r")
    assert ae.query_merge(["#35"])["method"] == "merge"
    assert ("pr", "merge", "35", "-R", "o/r", "--merge", "--delete-branch") in gh.calls


def test_merge_refuses_other_prs(monkeypatch, capsys):
    monkeypatch.setattr(ae, "_repo", lambda: "o/r")
    for pr, why in (({**ADW_PR, "headRefName": "bughunt/2026-07-26"}, "wasn't made by an ADW"),
                    ({**ADW_PR, "state": "MERGED"}, "is merged, not open")):
        gh = FakeGh(pr)
        monkeypatch.setattr(ae, "_gh", gh)
        assert ae.run_query("merge", ["35"]) == 1
        assert why in _lines(capsys)[0]["message"]
        assert not any(c[:2] == ("pr", "merge") for c in gh.calls)
    assert ae.run_query("merge", []) == 1
    assert "needs a pull request number" in _lines(capsys)[0]["message"]


def test_merge_that_only_failed_to_delete_the_local_branch_counts(monkeypatch):
    pushed = []
    monkeypatch.setattr(ae, "_gh", FakeGh(dict(ADW_PR), merge_fails=True, merged_anyway=True))
    monkeypatch.setattr(ae, "_repo", lambda: "o/r")
    monkeypatch.setattr(ae.subprocess, "run", lambda cmd, **kw: pushed.append(cmd))
    assert ae.query_merge(["35"])["merged"] is True
    assert pushed == [["git", "push", "origin", "--delete", ADW_PR["headRefName"]]]
    monkeypatch.setattr(ae, "_gh", FakeGh(dict(ADW_PR), merge_fails=True, merged_anyway=False))
    with pytest.raises(ae.QueryError, match="failed to delete"):
        ae.query_merge(["35"])


# ---- usage.json ----------------------------------------------------------------

def test_rate_limit_events_are_recorded_machine_wide(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(resources, "claude_account", lambda: "Claude Max")
    assert resources.record_rate_limit(SEVEN_DAY["rate_limit_info"])
    data = json.loads(Path(resources.usage_path()).read_text(encoding="utf-8"))
    assert data["windows"]["seven_day"]["used_percent"] == 31
    assert datetime.fromisoformat(data["windows"]["seven_day"]["resets_at"]).timestamp() == 1794214800
    assert datetime.fromisoformat(data["as_of"]).utcoffset() is not None          # with the UTC offset
    assert resources.record_rate_limit(FIVE_HOUR["rate_limit_info"])             # both windows at once
    view = resources.usage_view(t=NOW)
    assert view["account"] == "Claude Max" and view["as_of"]
    assert [(w["kind"], w["used_percent"]) for w in view["windows"]] == [("five_hour", 78.5), ("seven_day", 55)]
    assert datetime.fromisoformat(view["windows"][0]["resets_at"]).timestamp() == 1794146400
    # a window whose reset has passed shows 0%
    later = resources.usage_view(t=1794150000)
    assert [(w["kind"], w["used_percent"], "resets_at" in w) for w in later["windows"]] == \
        [("five_hour", 0, False), ("seven_day", 55, True)]
    assert not resources.record_rate_limit({"status": "allowed"})                # nothing to record
    assert not resources.record_rate_limit("junk")


def test_every_stream_reader_records_usage(tmp_path):
    tracker = messages.UsageTracker(str(tmp_path / "usage.json"))
    tracker.on_message(SEVEN_DAY)                                     # the orchestrated workflow's stream
    assert resources.read_usage()["windows"]["seven_day"]["used_percent"] == 31
    stream = "\n".join(json.dumps(m) for m in (
        {"type": "system", "subtype": "init"}, FIVE_HOUR,
        {"type": "result", "is_error": False, "session_id": "s1", "structured_output": {"status": "ready"}}))
    out = ae.turn_result(stream)                                      # the trigger's own clarification turns
    assert out["structured_output"] == {"status": "ready"} and out["session_id"] == "s1"
    assert resources.read_usage()["windows"]["five_hour"]["used_percent"] == 78.5
    assert ae.turn_result('{"type": "result", "result": "x"}')["result"] == "x"   # a single-JSON reply still works
    assert ae.turn_result("not json") == {}
    agent.record_rate_limits([{"type": "assistant"}, {**SEVEN_DAY, "rate_limit_info": {
        **SEVEN_DAY["rate_limit_info"], "unifiedWindows": {"seven_day": {"utilization": 0.4, "resetsAt": 1794214800}}}}])
    assert resources.read_usage()["windows"]["seven_day"]["used_percent"] == 40       # the classic ADW agents


def test_claude_account_from_the_cli_config(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert resources.claude_account() is None
    (tmp_path / ".claude.json").write_text(json.dumps({"oauthAccount": {"organizationType": "claude_max"}}))
    assert resources.claude_account() == "Claude Max"
    (tmp_path / ".claude.json").write_text(json.dumps({"oauthAccount": {"planDisplayName": "Ultra"}}))
    assert resources.claude_account() == "Claude Ultra"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert resources.claude_account() == "API key"


# ---- machine -------------------------------------------------------------------

def test_machine_view_reads_the_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("ADW_BACKEND_PORTS", "39300-39304")
    monkeypatch.setenv("ADW_FRONTEND_PORTS", "39400-39404")
    monkeypatch.setenv("ADW_REDIS_DBS", "2-6")
    monkeypatch.setenv("ADW_MAX_WORKFLOWS", "2")
    monkeypatch.setattr(resources, "claude_account", lambda: "Claude Max")
    onefan, nextcase = tmp_path / "OneFan", tmp_path / "nextcase"
    # an Ore workflow (labelled slot) in OneFan, a classic one in nextcase (its state knows the issue)
    resources.acquire("20261104091200-aaaaaaaaaaaa", root=str(onefan))
    assert resources.try_acquire_slot(resources.WORKFLOW, "20261104091200-aaaaaaaaaaaa", label="#26 Get Tickets",
                                      issue=26)
    resources.acquire("20261104100000-bbbbbbbbbbbb", hold="worktree", root=str(nextcase))
    (nextcase / "agents" / "20261104100000-bbbbbbbbbbbb").mkdir(parents=True)
    (nextcase / "agents" / "20261104100000-bbbbbbbbbbbb" / "adw_state.json").write_text(
        json.dumps({"adw_id": "20261104100000-bbbbbbbbbbbb", "issue_number": "8"}))
    assert resources.try_acquire_slot(resources.WORKFLOW, "20261104100000-bbbbbbbbbbbb")
    # a third one waits for a slot
    assert not resources.try_acquire_slot(resources.WORKFLOW, "20261104101500-cccccccccccc")
    resources.note_waiting("20261104101500-cccccccccccc", label="#27 Event wizard: time picker", issue=27)
    resources.record_rate_limit(FIVE_HOUR["rate_limit_info"])
    m = resources.machine_view()
    assert m["name"] and m["host"]
    assert m["workflows"] == {"used": 2, "max": 2} and m["suites"] == {"used": 0, "max": 2}
    first, second = m["leases"]
    assert first["project"] == "OneFan" and first["workflow"] == "#26 Get Tickets" and first["issue"] == 26
    assert first["adw_id"] == "20261104091200-aaaaaaaaaaaa" and first["ports"] == "39300 / 39400"
    assert first["redis"] == 2 and datetime.fromisoformat(first["since"]).utcoffset() is not None
    assert (second["project"], second["workflow"], second["issue"]) == ("nextcase", "#8", 8)
    assert [(q["project"], q["workflow"], q["issue"]) for q in m["queue"]] == \
        [(resources.codebase()["name"], "#27 Event wizard: time picker", 27)]      # the waiting trigger's codebase
    assert m["free"] == {"ports": 3, "ports_total": 5, "redis": 3, "redis_total": 5}
    assert m["config"].endswith("config.json")
    assert [w["kind"] for w in m["usage"]["windows"]] == ["five_hour", "seven_day"]
    assert m["usage"]["account"] == "Claude Max"
    json.dumps(m)                                                    # plain JSON
    # the waiter is gone once it gets its slot, and a released workflow's waiting record too
    resources.release("20261104100000-bbbbbbbbbbbb")
    assert resources.try_acquire_slot(resources.WORKFLOW, "20261104101500-cccccccccccc", label="#27 x", issue=27)
    m = resources.machine_view()
    assert m["queue"] == [] and {x["workflow"] for x in m["leases"]} == {"#26 Get Tickets", "#27 x"}


def test_waiters_of_a_dead_trigger_are_dropped():
    resources.note_waiting("w1", label="#1 a", pid=99999999)
    resources.note_waiting("w2", label="#2 b")
    assert [q["workflow"] for q in resources.machine_view()["queue"]] == ["#2 b"]
    data = json.loads(Path(resources.registry_path()).read_text(encoding="utf-8"))
    data["waiting"]["w2"]["heartbeat"] = time.time() - resources.WAIT_TTL - 5
    Path(resources.registry_path()).write_text(json.dumps(data), encoding="utf-8")
    assert resources.machine_view()["queue"] == []


def test_claim_slot_labels_the_slot_and_records_the_wait(tmp_path, monkeypatch):
    monkeypatch.setenv("ADW_MAX_WORKFLOWS", "1")
    monkeypatch.setenv("ADW_BACKEND_PORTS", "39310-39311")
    monkeypatch.setenv("ADW_FRONTEND_PORTS", "39410-39411")
    run = type("R", (), {"s": {"dry_run": False}})()
    a = {"title": "Get tickets", "issue_title": "Get Tickets", "issue_number": "26", "next_adw_id": "a1"}
    b = {"title": "Time picker", "issue_number": "27", "next_adw_id": "b1"}
    assert ae.claim_slot(run, a) == "a1"
    assert ae.claim_slot(run, b) is None
    m = resources.machine_view()
    assert [(x["workflow"], x.get("issue")) for x in m["leases"]] == [("#26 Get Tickets", 26)]
    assert [(q["workflow"], q["issue"]) for q in m["queue"]] == [("#27 Time picker", 27)]


# ---- items on parts --------------------------------------------------------------

def test_parts_carry_their_items(monkeypatch):
    monkeypatch.setattr(ae, "flow", lambda g: {})
    run = type("R", (), {"s": {"groups": [
        {"title": "Tickets", "item_ids": ["1", "3"], "status": "queued", "message": ""},
        {"title": "Footer", "item_ids": ["2"], "status": "running", "message": "Building", "issue_number": "9",
         "issue_url": "https://github.com/o/r/issues/9"}]}})()
    parts = ae.parts(run)
    assert [(p["key"], p["items"]) for p in parts] == [("Tickets", ["1", "3"]), ("Footer", ["2"])]


# ---- ask: a read-only Claude session in the repo's root ---------------------------

def test_ask_runs_a_read_only_claude_session_in_the_repo_root(monkeypatch, capsys):
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        out = {"type": "result", "result": "Prices live in app/backend/src/pricing.py.", "session_id": "s-1",
               "total_cost_usd": 0.02, "is_error": False}
        return type("P", (), {"returncode": 0, "stdout": json.dumps(out), "stderr": ""})()
    monkeypatch.setattr(ae.subprocess, "run", fake_run)
    assert ae.run_query("ask", ["Where are prices worked out?"]) == 0
    assert _lines(capsys) == [{"type": "answer", "query": "ask", "data": {
        "answer": "Prices live in app/backend/src/pricing.py.", "session_id": "s-1", "cost_usd": 0.02}}]
    cmd, kw = calls[0]
    assert kw["cwd"] == ae.REPO_ROOT and cmd[1:3] == ["-p", "Where are prices worked out?"]
    assert "--resume" not in cmd and cmd[cmd.index("--permission-mode") + 1] == "plan"
    assert "Edit" in cmd[cmd.index("--disallowedTools"):] and "CLAUDE.md" in cmd[cmd.index("--append-system-prompt") + 1]
    # a follow-up continues the session
    assert ae.run_query("ask", ["And discounts?", "s-1"]) == 0
    assert calls[1][0][calls[1][0].index("--resume") + 1] == "s-1"
    # attachments: listed for the session to read; one outside the repository gets --add-dir
    inside = str(ae.REPO_ROOT / ".ore" / "questions" / "7" / "spec.pdf")
    assert ae.run_query("ask", ["Does the code match?", "", inside, "/elsewhere/prices.xlsx.txt"]) == 0
    cmd = calls[2][0]
    assert f"- {inside}" in cmd[2] and "- /elsewhere/prices.xlsx.txt" in cmd[2]
    assert cmd[cmd.index("--add-dir") + 1] == "/elsewhere" and cmd.count("--add-dir") == 1


def test_ask_reports_claude_problems(monkeypatch, capsys):
    out = {"type": "result", "result": "Not logged in", "is_error": True}
    monkeypatch.setattr(ae.subprocess, "run", lambda cmd, **kw: type("P", (), {
        "returncode": 1, "stdout": json.dumps(out), "stderr": ""})())
    assert ae.run_query("ask", ["Q?"]) == 1
    assert "Not logged in" in _lines(capsys)[0]["message"]      # the sign-in advice (it depends on the machine)
    assert ae.run_query("ask", []) == 1
    assert "needs a question" in _lines(capsys)[0]["message"]


# ---- items: Ore's action items, read in the repo's root -----------------------------------

def _items_request(tmp_path, monkeypatch, **extra) -> Path:
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    folder = tmp_path / ".ore" / "items" / "7-abc"
    folder.mkdir(parents=True)
    (folder / "transcript.txt").write_text("[1] 00:01 Ann: fix the refund export\n", encoding="utf-8")
    req = {"rules": "You are in the repository of OneFan.", "prompt": "First-pass items: ...",
           "schema": {"type": "object", "properties": {"items": {"type": "array"}}},
           "transcript": str(folder / "transcript.txt"), **extra}
    (folder / "request.json").write_text(json.dumps(req), encoding="utf-8")
    return folder / "request.json"


def test_items_are_read_in_a_read_only_session_and_the_request_is_removed(tmp_path, monkeypatch, capsys):
    path = _items_request(tmp_path, monkeypatch, minutes=10)
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        out = {"type": "result", "result": "", "structured_output": {"items": [{"title": "Add the end time"}],
                                                                     "not_ours": []},
               "total_cost_usd": 0.31, "is_error": False}
        return type("P", (), {"returncode": 0, "stdout": json.dumps(out), "stderr": ""})()
    monkeypatch.setattr(ae.subprocess, "run", fake_run)
    assert ae.run_query("items", [str(path)]) == 0
    assert _lines(capsys) == [{"type": "answer", "query": "items", "data": {
        "items": {"items": [{"title": "Add the end time"}], "not_ours": []}, "cost_usd": 0.31}}]
    cmd, kw = calls[0]
    assert kw["cwd"] == tmp_path and kw["input"] == "First-pass items: ..." and kw["timeout"] == 600
    assert cmd[cmd.index("--permission-mode") + 1] == "plan" and "Edit" in cmd[cmd.index("--disallowedTools"):]
    assert json.loads(cmd[cmd.index("--json-schema") + 1])["type"] == "object"
    allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")]
    assert "Bash(git log:*)" in allowed and "Bash(gh pr view:*)" in allowed
    assert not any(a.startswith("Bash(") and not a.startswith(("Bash(git log", "Bash(git show", "Bash(git remote get-url",
                                                               "Bash(gh pr list", "Bash(gh pr view")) for a in allowed)
    assert cmd[cmd.index("--append-system-prompt") + 1] == "You are in the repository of OneFan."
    assert not path.parent.exists() and (tmp_path / ".ore" / "items").exists()


def test_items_refuses_a_request_outside_the_inbox_and_reports_problems(tmp_path, monkeypatch, capsys):
    path = _items_request(tmp_path, monkeypatch)
    outside = tmp_path / "request.json"
    outside.write_text("{}", encoding="utf-8")
    assert ae.run_query("items", [str(outside)]) == 1
    assert ".ore/items" in _lines(capsys)[0]["message"] and outside.exists()
    assert ae.run_query("items", []) == 1
    assert "needs the request" in _lines(capsys)[0]["message"]
    out = {"type": "result", "result": "Not logged in", "is_error": True}
    monkeypatch.setattr(ae.subprocess, "run", lambda cmd, **kw: type("P", (), {
        "returncode": 1, "stdout": json.dumps(out), "stderr": ""})())
    assert ae.run_query("items", [str(path)]) == 1
    assert "Not logged in" in _lines(capsys)[0]["message"] and not path.parent.exists()


# ---- consult: Ore's specialists (adws/specialists/<name>.md), read-only in the repo's root ---------------------

BACKLOG_ANSWER = {"duplicates": [{"keep": "41", "close": ["37"], "detail": "Export refunds as CSV, with dates.",
                                  "reason": "Both ask for the refund export."}],
                  "done": [{"id": "12", "note": "The footer shows the version.", "commit": "abc1234",
                            "commit_url": "https://github.com/o/r/commit/abc1234", "pr_url": ""}],
                  "order": [{"id": "41", "reason": "Finance needs it this week."}]}


def _consult_request(tmp_path, monkeypatch, **extra) -> Path:
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    folder = tmp_path / ".ore" / "pm" / "5"
    folder.mkdir(parents=True)
    req = {"specialist": "backlog", "version": 1, "workspace": {"name": "OneFan", "slug": "onefan"},
           "goals": "Ship refunds first.",
           "items": [{"id": "41", "title": "Refund export", "detail": "CSV", "pinned": False, "keep": False,
                      "possible_duplicate_of": "37"}],
           "schema": {"type": "object", "required": ["duplicates", "done", "order"]}, **extra}
    (folder / "request.json").write_text(json.dumps(req), encoding="utf-8")
    return folder / "request.json"


def _fake_claude(calls, out, returncode=0):
    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        return type("P", (), {"returncode": returncode, "stdout": json.dumps(out), "stderr": ""})()
    return fake_run


def test_consult_is_advertised():
    assert "consult" in ae.QUERIES


def test_consult_runs_the_specialist_read_only_and_removes_the_request(tmp_path, monkeypatch, capsys):
    path = _consult_request(tmp_path, monkeypatch, minutes=15)
    (tmp_path / "adws" / "specialists").mkdir(parents=True)
    (tmp_path / "adws" / "specialists" / "backlog.md").write_text("You are the project manager (repo copy).",
                                                                   encoding="utf-8")
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude(calls, {
        "type": "result", "result": "", "structured_output": BACKLOG_ANSWER, "session_id": "s-9",
        "total_cost_usd": 0.42, "is_error": False}))
    assert ae.run_query("consult", ["backlog", str(path)]) == 0
    assert _lines(capsys) == [{"type": "answer", "query": "consult", "data": {
        "result": BACKLOG_ANSWER, "session_id": "s-9", "cost_usd": 0.42}}]
    cmd, kw = calls[0]
    assert kw["cwd"] == tmp_path and kw["timeout"] == 15 * 60
    sent = json.loads(kw["input"][kw["input"].index("{"):])
    assert sent["goals"] == "Ship refunds first." and sent["items"][0]["id"] == "41"
    assert sent["workspace"]["slug"] == "onefan" and "schema" not in sent
    assert cmd[cmd.index("--append-system-prompt") + 1] == "You are the project manager (repo copy)."
    assert json.loads(cmd[cmd.index("--json-schema") + 1])["required"] == ["duplicates", "done", "order"]
    assert cmd[cmd.index("--model") + 1] == ae.CONSULT_MODEL
    assert cmd[cmd.index("--permission-mode") + 1] == "plan" and "--max-budget-usd" not in cmd
    assert "Edit" in cmd[cmd.index("--disallowedTools"):] and "Write" in cmd[cmd.index("--disallowedTools"):]
    allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")]
    assert "Bash(git log:*)" in allowed and "Bash(gh pr view:*)" in allowed
    assert not any(a.startswith("Bash(") and not a.startswith(("Bash(git log", "Bash(git show", "Bash(git remote get-url",
                                                               "Bash(git diff", "Bash(gh pr list", "Bash(gh pr view",
                                                               "Bash(gh pr diff", "Bash(gh pr checks")) for a in allowed)
    assert not path.parent.exists() and (tmp_path / ".ore" / "pm").exists()


def test_consult_falls_back_to_the_built_in_backlog_prompt(tmp_path, monkeypatch, capsys):
    path = _consult_request(tmp_path, monkeypatch)             # no adws/specialists/ in this repository
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude(calls, {
        "type": "result", "structured_output": BACKLOG_ANSWER, "session_id": "s-1", "total_cost_usd": 0.1}))
    assert ae.run_query("consult", ["backlog", str(path)]) == 0
    cmd, kw = calls[0]
    assert cmd[cmd.index("--append-system-prompt") + 1] == ae.BACKLOG_FALLBACK and kw["timeout"] == 15 * 60


def test_the_repo_backlog_prompt_is_found(monkeypatch):
    # the template's own adws/specialists/backlog.md is what the trigger loads
    monkeypatch.setattr(ae, "REPO_ROOT", Path(__file__).resolve().parents[2])
    text = ae.specialist_prompt("backlog")
    assert text != ae.BACKLOG_FALLBACK and '"keep": true' in text and "never commit" in text


def test_consult_refuses_bad_names_unknown_specialists_and_outside_requests(tmp_path, monkeypatch, capsys):
    path = _consult_request(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude(calls, {}))
    assert ae.run_query("consult", ["../etc", str(path)]) == 1
    assert "specialist name" in _lines(capsys)[0]["message"] and path.exists()
    assert ae.run_query("consult", ["backlog"]) == 1
    assert "needs the request" in _lines(capsys)[0]["message"]
    outside = tmp_path / "request.json"
    outside.write_text("{}", encoding="utf-8")
    assert ae.run_query("consult", ["backlog", str(outside)]) == 1
    assert ".ore/pm" in _lines(capsys)[0]["message"] and outside.exists()
    assert ae.run_query("consult", ["security", str(path)]) == 1
    line = _lines(capsys)[0]
    assert line["type"] == "error" and "no specialist 'security'" in line["message"]
    assert not calls and not path.parent.exists()              # the request is cleaned up either way


def test_consult_reports_claude_problems(tmp_path, monkeypatch, capsys):
    path = _consult_request(tmp_path, monkeypatch)
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude([], {
        "type": "result", "result": "Not logged in", "is_error": True}, returncode=1))
    assert ae.run_query("consult", ["backlog", str(path)]) == 1
    assert "Not logged in" in _lines(capsys)[0]["message"] and not path.parent.exists()
    path = _consult_request(tmp_path, monkeypatch)
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude([], {"type": "result", "result": "Done."}))
    assert ae.run_query("consult", ["backlog", str(path)]) == 1
    assert "backlog specialist didn't answer" in _lines(capsys)[0]["message"]


# ---- consult, phase 3: sessions, the user's message and files, the four specialists --------------------------------

def test_consult_continues_the_session_with_the_same_read_only_flags(tmp_path, monkeypatch, capsys):
    path = _consult_request(tmp_path, monkeypatch, session_id="0f3c2a1e-5b7d-4c9e-8a10-123456789abc")
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude(calls, {
        "type": "result", "structured_output": {"duplicates": [], "done": []}, "total_cost_usd": 0.05}))
    assert ae.run_query("consult", ["backlog", str(path)]) == 0
    # no session id in Claude's reply: the one continued comes back
    assert _lines(capsys)[0]["data"]["session_id"] == "0f3c2a1e-5b7d-4c9e-8a10-123456789abc"
    cmd, kw = calls[0]
    assert cmd[cmd.index("--resume") + 1] == "0f3c2a1e-5b7d-4c9e-8a10-123456789abc"
    assert cmd[cmd.index("--permission-mode") + 1] == "plan" and "--no-session-persistence" not in cmd
    assert "Edit" in cmd[cmd.index("--disallowedTools"):] and "Write" in cmd[cmd.index("--disallowedTools"):]
    allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")]
    assert not any(a.startswith("Bash(") and not a.startswith(("Bash(git log", "Bash(git show", "Bash(git remote get-url",
                                                               "Bash(git diff", "Bash(gh pr list", "Bash(gh pr view",
                                                               "Bash(gh pr diff", "Bash(gh pr checks")) for a in allowed)
    assert "session_id" not in kw["input"]                      # the id is a flag, not part of the message


def test_consult_starts_a_new_session_without_one_or_when_it_is_gone(tmp_path, monkeypatch, capsys):
    path = _consult_request(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude(calls, {
        "type": "result", "structured_output": {"duplicates": [], "done": []}, "session_id": "new"}))
    assert ae.run_query("consult", ["backlog", str(path)]) == 0
    assert "--resume" not in calls[0][0]
    path = _consult_request(tmp_path, monkeypatch, session_id="gone-1")
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "--resume" in cmd:
            return type("P", (), {"returncode": 1, "stdout": "", "stderr": "No conversation found with session ID: gone-1"})()
        return type("P", (), {"returncode": 0, "stderr": "", "stdout": json.dumps({
            "type": "result", "structured_output": {"duplicates": [], "done": []}, "session_id": "fresh"})})()
    monkeypatch.setattr(ae.subprocess, "run", fake_run)
    assert ae.run_query("consult", ["backlog", str(path)]) == 0
    assert _lines(capsys)[-1]["data"]["session_id"] == "fresh"
    assert len(calls) == 2 and "--resume" in calls[0] and "--resume" not in calls[1]


def test_consult_refuses_a_session_id_that_could_be_a_flag(tmp_path, monkeypatch, capsys):
    path = _consult_request(tmp_path, monkeypatch, session_id="--dangerously-skip-permissions")
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude(calls, {}))
    assert ae.run_query("consult", ["backlog", str(path)]) == 1
    assert "session_id" in _lines(capsys)[0]["message"] and not calls and not path.parent.exists()


def test_consult_puts_the_users_message_and_files_in_the_session(tmp_path, monkeypatch, capsys):
    files = tmp_path / ".ore" / "pm" / "5" / "files"
    shot, doc = files / "1-screen.png", files / "2-spec.docx"
    path = _consult_request(tmp_path, monkeypatch, session_id="s-1", message={
        "text": "Only the refunds of this year, see the screenshot.",
        "attachments": [{"name": "screen.png", "path": str(shot), "text_path": None},
                        {"name": "spec.docx", "path": ".ore/pm/5/files/2-spec.docx",
                         "text_path": ".ore/pm/5/files/2-spec.docx.txt"}]},
        items=[{"id": "41", "title": "Refund export", "detail": "CSV", "conversation": [
            {"author": "scoper", "text": "Which refunds?", "attachments": []},
            {"author": "you", "text": "Like this", "attachments": [str(files / "0-old.pdf")]}]}],
        workspaces=[{"slug": "admin", "name": "Admin", "kind": "general"}])
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude(calls, {
        "type": "result", "structured_output": {"items": [], "messages": []}, "session_id": "s-1"}))
    assert ae.run_query("consult", ["scoper", str(path)]) == 0
    cmd, kw = calls[0]
    text = kw["input"]
    assert text.startswith("The user wrote to you on a card in Ore:\n\nOnly the refunds of this year")
    assert f"- screen.png: {shot.resolve()}" in text
    assert f"- spec.docx: {doc.resolve()} (text: {(files / '2-spec.docx.txt').resolve()})" in text
    assert str((files / "0-old.pdf").resolve()) in text and "read them with Read" in text
    sent = json.loads(text[text.index("Ore's request"):][text[text.index("Ore's request"):].index("{"):])
    assert sent["workspaces"][0]["slug"] == "admin" and sent["items"][0]["conversation"][1]["author"] == "you"
    assert "message" not in sent and "schema" not in sent
    assert "--add-dir" not in cmd                                # the files are inside the repository
    assert cmd[cmd.index("--append-system-prompt") + 1] == ae.SCOPER_FALLBACK


def test_consult_refuses_attachments_outside_the_requests_files(tmp_path, monkeypatch, capsys):
    for bad in ("/etc/passwd", ".ore/pm/5/request.json", ".ore/pm/5/files/../../../.env", ".ore/pm/6/files/a.png"):
        path = _consult_request(tmp_path, monkeypatch, message={"text": "see", "attachments": [{"name": "x",
                                                                                              "path": bad}]})
        calls = []
        monkeypatch.setattr(ae.subprocess, "run", _fake_claude(calls, {}))
        assert ae.run_query("consult", ["triage", str(path)]) == 1
        assert "files/ folder" in _lines(capsys)[0]["message"] and not calls and not path.parent.exists()
    path = _consult_request(tmp_path, monkeypatch, items=[{"id": "1", "title": "t", "conversation": [
        {"author": "you", "text": "", "attachments": [str(tmp_path / "secret.txt")]}]}])
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude([], {}))
    assert ae.run_query("consult", ["triage", str(path)]) == 1
    assert "files/ folder" in _lines(capsys)[0]["message"]


@pytest.mark.parametrize("name,word", [("backlog", "Duplicates"), ("triage", "not_dev"), ("planner", "Links"),
                                       ("scoper", "questions")])
def test_each_specialist_has_a_built_in_fallback(tmp_path, monkeypatch, capsys, name, word):
    path = _consult_request(tmp_path, monkeypatch)             # no adws/specialists/ in this repository
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", _fake_claude(calls, {"type": "result", "structured_output": {}}))
    assert ae.run_query("consult", [name, str(path)]) == 0
    prompt = calls[0][0][calls[0][0].index("--append-system-prompt") + 1]
    assert prompt == ae.SPECIALIST_FALLBACKS[name] and word in prompt
    assert "never commit" in prompt and "never push" in prompt and "messages" in prompt
    assert "given schema" in prompt


def test_the_backlog_fallback_no_longer_orders():
    assert "Order" not in ae.BACKLOG_FALLBACK and "rank" not in ae.BACKLOG_FALLBACK


@pytest.mark.parametrize("name,words", [
    ("backlog", ["Duplicates", "Already done", '"keep": true']),
    ("triage", ["`dev`", "`not_dev`", "`other_workspace`", "`split`", "workspaces"]),
    ("planner", ["`S`", "`M`", "`L`", "Links", "Groups"]),
    ("scoper", ["testable", "at most three", "`questions`"])])
def test_the_repo_specialist_prompts_are_found(monkeypatch, name, words):
    monkeypatch.setattr(ae, "REPO_ROOT", Path(__file__).resolve().parents[2])
    text = ae.specialist_prompt(name)
    assert text != ae.SPECIALIST_FALLBACKS[name]
    assert all(w in text for w in words), name
    assert "never commit" in text and "never push" in text and "given schema" in text and "`messages`" in text
    if name == "backlog":
        assert "## 3. Order" not in text and "Ordering is not your job" in text
