"""Ore's project board (docs/script-protocol.md): the run's phase in every status, taking items out while it plans
(stdin "withdraw"), and going back to planning (--ore-replan) with the work kept or undone.

Run: uv run --with pytest --with pydantic --with python-dotenv pytest adws/adw_tests/test_ore_board.py
"""

from __future__ import annotations

import base64
import json
import sys
import types
from pathlib import Path

import pytest

ADWS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ADWS))

from adw_triggers import trigger_ore as ae  # noqa: E402

ITEMS = [{"id": str(n), "title": t, "detail": "", "images": [], "text": f"- [ ] {t}"}
         for n, t in ((1, "Order status"), (2, "Checkout typo"), (3, "CSV export"))]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    sent = []
    monkeypatch.setattr(ae, "emit", lambda msg: sent.append(msg))
    monkeypatch.setattr(ae, "status", ae.ore_status)          # as under Ore, with or without its SDK installed here
    monkeypatch.setattr(ae, "IO", ae.OreInput())
    ae.IO.enabled = True
    gh = []

    class Done:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(ae, "_cmd", lambda *args: gh.append(list(args)) or Done())
    return types.SimpleNamespace(root=tmp_path, sent=sent, gh=gh)


def make_run(repo, phase, groups, **extra):
    run = ae.Run(repo.root / "agents" / "ore" / "rb")
    run.dir.mkdir(parents=True, exist_ok=True)
    run.s = {"run_id": "rb", "items_file": str(repo.root / "batch.md"), "items": [dict(i) for i in ITEMS],
             "phase": phase, "session_id": "sess-1", "next_message": None, "pending": None, "groups": groups,
             "dry_run": False, "simulate": False, "stages": {}, **extra}
    run.save()
    return run


def statuses(repo):
    return [m for m in repo.sent if m["type"] == "status"]


def replies(repo):
    return {m["to"]: m["text"] for m in repo.sent if m["type"] == "reply"}


def test_every_status_says_the_phase_and_what_the_run_accepts(repo):
    for phase, expected in (("clarify", "planning"), ("review", "planning"), ("issues", "building"),
                            ("workflows", "building"), ("done", "building")):
        ae.report(make_run(repo, phase, []), "x")
        last = statuses(repo)[-1]
        assert last["phase"] == expected, phase
        assert last["accepts"] == ["message", "follow_up", "withdraw", "replan", "files"]


def test_withdraw_while_the_groups_wait_for_the_user(repo, monkeypatch):
    groups = [{"title": "Orders", "summary": "", "item_ids": ["1", "2"]},
              {"title": "Export", "summary": "", "item_ids": ["3"]}]
    run = make_run(repo, "review", groups, pending={"key": "review-2"})
    ae.IO.messages = [{"type": "withdraw", "id": "w7", "items": ["2"], "reason": "Done by hand already"}]
    ae.handle_messages(run)
    assert replies(repo)["w7"] == "Took out “Checkout typo”."
    assert [g["item_ids"] for g in run.s["groups"]] == [["1"], ["3"]]
    assert ae.Run(run.dir).s["withdrawn"] == {"2": "Done by hand already"}
    assert "item 2 (Checkout typo)" in run.s["planning_notes"][0] and "Done by hand" in run.s["planning_notes"][0]
    # the open groups check is asked again (same id) without the item, then a fresh status
    ask = next(m for m in repo.sent if m["type"] == "input_request")
    assert ask["id"] == "review-2" and [[i["id"] for i in g["items"]] for g in ask["groups"]] == [["1"], ["3"]]
    assert repo.sent[-1]["type"] == "status" and repo.sent[-1]["phase"] == "planning"
    # an answer that still lists it (sent before the change) doesn't bring it back
    assert ae.normalise_groups(run, [{"title": "All", "item_ids": ["1", "2", "3"]}]) == \
        [{"title": "All", "summary": "", "item_ids": ["1", "3"]}]
    # the note goes to Claude once, before its next turn
    seen = []
    proc = types.SimpleNamespace(returncode=0, stderr="",
                                 stdout=json.dumps({"type": "result", "structured_output": {"status": "ready"}}))
    monkeypatch.setattr(ae.subprocess, "run", lambda cmd, **kw: seen.append(cmd[2]) or proc)
    monkeypatch.setattr(ae, "free_workflow_slots", lambda: 2)
    ae.claude_turn(run, "My answers")
    ae.claude_turn(run, "Next")
    assert seen[0].startswith("The user took item 2") and "My answers" in seen[0]
    assert seen[1].startswith("Next") and "planning_notes" not in run.s


def test_withdraw_refuses_every_item_unknown_items_and_after_building_started(repo):
    run = make_run(repo, "clarify", [], pending={"key": "clarify-1", "questions": []})
    ae.IO.messages = [{"type": "withdraw", "id": "w1", "items": ["1", "2", "3"], "reason": ""},
                      {"type": "withdraw", "id": "w2", "items": ["9"], "reason": ""},
                      {"type": "withdraw", "id": "w3", "items": ["Item 3"], "reason": ""}]
    ae.handle_messages(run)
    r = replies(repo)
    assert "every item" in r["w1"] and "None of those" in r["w2"] and r["w3"] == "Took out “CSV export”."
    assert [it["id"] for it in ae.planned_items(run)] == ["1", "2"]
    assert not any(m["type"] == "input_request" for m in repo.sent)      # no groups check open in clarify
    building = make_run(repo, "workflows", [{"title": "Orders", "status": "running", "item_ids": ["1"]}])
    ae.IO.messages = [{"type": "withdraw", "id": "w4", "items": ["1"], "reason": "x"}]
    ae.handle_messages(building)
    assert "workflows have started" in replies(repo)["w4"] and "withdrawn" not in building.s


def test_the_stdin_reader_queues_withdraw_messages(monkeypatch):
    io = ae.OreInput()
    lines = [json.dumps({"type": "withdraw", "id": "w1", "items": ["2"], "reason": "r"}) + "\n",
             json.dumps({"id": "review-1", "value": {"action": "start"}}) + "\n"]
    monkeypatch.setattr(ae.sys, "stdin", lines)
    io._read()
    assert io.take_messages()[0]["type"] == "withdraw" and io.answer("review-1") == {"action": "start"}


def replan_arg(req: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(req).encode()).decode().rstrip("=")


def test_the_replan_argument_comes_after_the_resume_arguments(repo, monkeypatch):
    req = {"id": "mv3", "reason": "Use the new API", "keep_work": True, "items": ["1"], "prs": [12]}
    rest, got = ae.follow_up_arg(["--resume", "/r", "--ore-replan", replan_arg(req)], "--ore-replan")
    assert rest == ["--resume", "/r"] and got == req
    assert ae.follow_up_arg(["--resume", "/r"], "--ore-replan") == (["--resume", "/r"], None)
    run = make_run(repo, "done", [])
    seen = []

    class Stop(Exception):
        pass

    def fake_replan(run_, r):
        seen.append(r)
        raise Stop

    monkeypatch.setattr(ae, "replan", fake_replan)
    for keep in (True, False):
        monkeypatch.setattr(ae.sys, "argv", ["trigger_ore.py", "--resume", str(run.dir), "--ore-replan",
                                             replan_arg({**req, "keep_work": keep}), "--model", "sonnet"])
        with pytest.raises(Stop):
            ae.main()
    assert [r["keep_work"] for r in seen] == [True, False]
    # a replan cut short (Ore stopped meanwhile) is finished by a plain resume
    run.s["replan"] = req
    run.save()
    monkeypatch.setattr(ae.sys, "argv", ["trigger_ore.py", "--resume", str(run.dir)])
    with pytest.raises(Stop):
        ae.main()
    assert seen[-1] == req
    # an unreadable request fails the run
    monkeypatch.setattr(ae, "error", lambda message, exit_code=1: (_ for _ in ()).throw(SystemExit(message)))
    monkeypatch.setattr(ae.sys, "argv", ["trigger_ore.py", "--resume", str(run.dir), "--ore-replan", "%%%"])
    with pytest.raises(SystemExit, match="couldn't be read"):
        ae.main()


def orchestrated(repo, title, items, adw, pr, status="done"):
    wt = repo.root / "trees" / adw
    wt.mkdir(parents=True, exist_ok=True)
    (repo.root / "agents" / adw).mkdir(parents=True, exist_ok=True)
    (repo.root / "agents" / adw / "adw_state.json").write_text(json.dumps(
        {"adw_id": adw, "worktree_path": str(wt), "orchestrator_session_id": f"s-{adw}",
         "branch_name": f"feat-issue-{pr}-adw-{adw}"}))
    return {"title": title, "summary": "", "item_ids": items, "status": status, "adw_id": adw,
            "workflow": "orchestrated", "issue_number": str(pr - 10), "issue_url": f"https://github.com/o/r/issues/{pr - 10}",
            "pr_url": f"https://github.com/o/r/pull/{pr}", "progress": 1.0, "completed": True}


def test_replan_keeping_the_work_drafts_the_prs_and_continues_the_same_workflow(repo, monkeypatch):
    a = orchestrated(repo, "Orders", ["1", "2"], "a1", 12)
    b = orchestrated(repo, "Export", ["3"], "b1", 13)
    run = make_run(repo, "done", [a, b], stages={"clarify": {"started": "t", "ended": "t"}, "workflows": {}})
    ae.replan(run, {"id": "mv3", "reason": "Use the new API", "keep_work": True, "items": ["1"], "prs": [12]})
    assert repo.gh == [["gh", "pr", "ready", "12", "--undo"]]            # only the card's PR; Export's stays
    assert run.s["phase"] == "clarify" and run.s["groups"] == [] and "replan" not in run.s
    assert run.s["kept_groups"] == [b] and run.s["scope"] == ["1", "2"]
    assert run.s["previous_groups"][0]["drafted"] is True
    assert "Use the new API" in run.s["next_message"] and "feat-issue-12-adw-a1" in run.s["next_message"]
    assert "Plan items 1, 2 again" in run.s["next_message"]
    assert "workflows" not in run.s["stages"] and "ended" not in run.s["stages"]["clarify"]
    last = statuses(repo)[-1]
    assert last["phase"] == "planning" and last["message"] == "Planning again: Use the new API"
    assert [p["key"] for p in last["parts"]] == ["Export"]              # the old Orders part is gone
    # Claude's next turn hears it; the groups check shows only the replanned items
    assert [it["id"] for it in ae.planned_items(run)] == ["1", "2"]
    run.s.update(phase="review", pending={"key": "review-9"})
    monkeypatch.setattr(ae, "review_groups", lambda groups, prompt="", key=None: {
        "action": "start", "groups": [{"title": "Export", "item_ids": ["1", "2", "3"]}]})
    ae.review(run)
    assert [g["title"] for g in run.s["groups"]] == ["Export", "Export (new)"]
    assert run.s["groups"][1]["item_ids"] == ["1", "2"] and "scope" not in run.s and "kept_groups" not in run.s
    monkeypatch.setattr(ae, "claude_turn", lambda run_, message: {"groups": []})
    ae.write_issues(run)
    new = run.s["groups"][1]
    assert run.s["groups"][0] is b and b["status"] == "done"            # the kept workflow is left alone
    assert new["continue_adw"] == new["next_adw_id"] == "a1" and new["issue_number"] == "2"
    assert new["pr_url"].endswith("/12") and new["follow_up"]["text"].startswith("This work went back to planning")
    assert new["drafted"] is True and run.s["previous_groups"] == []
    # when it finishes, its PR is ready for review again
    repo.gh.clear()
    ae.ready_again(run, new)
    assert repo.gh == [["gh", "pr", "ready", "https://github.com/o/r/pull/12"]] and "drafted" not in new


def test_replan_from_scratch_cleans_up_first(repo, monkeypatch):
    a = orchestrated(repo, "Orders", ["1", "2"], "a1", 12)
    b = orchestrated(repo, "Export", ["3"], "b1", 13)
    run = make_run(repo, "workflows", [a, b])
    cleaned = []
    monkeypatch.setattr(ae, "clean_group", lambda run_, g, on_github: cleaned.append((g["title"], on_github)) or [])
    ae.replan(run, {"id": "mv4", "reason": "Wrong approach", "keep_work": False, "items": [], "prs": [12, 13]})
    assert cleaned == [("Orders", True), ("Export", True)] and repo.gh == []     # no drafts: the PRs are closed
    assert run.s["phase"] == "clarify" and "kept_groups" not in run.s and "scope" not in run.s
    assert not run.s.get("previous_groups") and "thrown away" in run.s["next_message"]
    assert statuses(repo)[-1]["phase"] == "planning"
    # a cleanup that fails keeps the request for the next resume
    monkeypatch.setattr(ae, "clean_group", lambda run_, g, on_github: [f"{g['title']}: gh is down"])
    monkeypatch.setattr(ae, "error", lambda message, exit_code=1: (_ for _ in ()).throw(SystemExit(message)))
    run2 = make_run(repo, "workflows", [orchestrated(repo, "Orders", ["1"], "a2", 14)])
    with pytest.raises(SystemExit, match="gh is down"):
        ae.replan(run2, {"id": "mv5", "reason": "r", "keep_work": False, "items": ["1"], "prs": []})
    assert ae.Run(run2.dir).s["replan"]["id"] == "mv5" and ae.Run(run2.dir).s["phase"] == "workflows"


def test_delete_cleans_up_kept_and_earlier_workflows_too(repo, monkeypatch):
    run = make_run(repo, "clarify", [], kept_groups=[{"title": "Export"}], previous_groups=[{"title": "Orders"}])
    seen = []
    monkeypatch.setattr(ae, "clean_group", lambda run_, g, on_github: seen.append(g["title"]) or [])
    monkeypatch.setattr(ae, "result", lambda summary, **kw: None)
    monkeypatch.setattr(ae, "status", lambda *a, **kw: None)
    ae.clean(run.dir, set())
    assert seen == ["Export", "Orders"] and not run.dir.exists()
