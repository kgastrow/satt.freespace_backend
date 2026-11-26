"""Ore's question round (docs/script-protocol.md in Ore): before anything is built, the trigger runs the test planner,
the risk reviewer and the designer on every group, asks the reviews (kind "review": gates design, risk and build) one
at a time, reports the specialists' notes and the gates on the parts, and puts the approved prototype, the test plan
and the accepted risks into the build instructions.

Run: uv run --with pytest --with pydantic --with python-dotenv pytest adws/adw_tests/test_ore_round.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import types
from pathlib import Path

import pytest

ADWS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ADWS))

from adw_triggers import trigger_ore as ae  # noqa: E402

ITEMS = [{"id": "1", "title": "Order status", "detail": "", "images": [], "criteria": [], "size": "M",
          "text": "- [ ] Order status\n  Size: M"},
         {"id": "2", "title": "Checkout typo", "detail": "", "images": [], "criteria": [], "size": "S",
          "text": "- [ ] Checkout typo"}]

RISK = {"title": "Old orders have no status", "detail": "Orders from before would show as empty.", "severity": "medium",
        "needs_acceptance": True, "mitigation": "Backfill them as Delivered."}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    sent = []
    monkeypatch.setattr(ae, "emit", lambda msg: sent.append(msg))
    monkeypatch.setattr(ae, "status", ae.ore_status)
    monkeypatch.setattr(ae, "IO", ae.OreInput())
    monkeypatch.setattr(ae, "get_safe_subprocess_env", lambda: dict(os.environ))
    monkeypatch.setattr(ae, "git_changes", lambda: None)          # tmp_path isn't a git repository
    ae.IO.enabled = True
    ae.IO.closed = True                  # an answer the test didn't give fails the test instead of waiting for ever
    return types.SimpleNamespace(root=tmp_path, sent=sent)


def make_run(repo, groups, phase="checks", **extra):
    run = ae.Run(repo.root / "agents" / "ore" / "rq")
    run.dir.mkdir(parents=True, exist_ok=True)
    run.s = {"run_id": "rq", "items_file": str(repo.root / "batch.md"), "items": [dict(i) for i in ITEMS],
             "phase": phase, "session_id": "plan-1", "next_message": None, "pending": None, "groups": groups,
             "dry_run": False, "simulate": False, "stages": {}, "question_rounds": 1,
             "clarifications": ["{\"Which statuses?\": \"All statuses\"}"], **extra}
    run.save()
    return run


def fake_claude(repo, calls, risks=(RISK,)):
    """claude -p as the specialists would answer: by the schema it was given; the designer writes its file."""
    def run(cmd, input=None, **kw):
        calls.append((cmd, input))
        required = json.loads(cmd[cmd.index("--json-schema") + 1])["required"]
        if required == ["summary", "plan"]:
            time.sleep(0.6)                  # long enough for a status while it runs
            kind, reply = "tests", {"summary": "Two unit tests and an end-to-end check", "plan": "- test_status"}
        elif required == ["summary", "risks"]:
            kind, reply = "risk", {"summary": "One risk.", "risks": list(risks)}
        else:
            kind = "design"
            path = Path(re.search(r"to exactly this file: (\S+)", input).group(1))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"<!doctype html><title>{path.name}</title>", encoding="utf-8")
            reply = {"summary": f"The orders table ({path.stem})."}
        out = {"type": "result", "structured_output": reply, "session_id": f"s-{kind}", "total_cost_usd": 0.01}
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(out) + "\n", stderr="")
    return run


def requests(repo):
    return [m for m in repo.sent if m["type"] == "input_request"]


def statuses(repo):
    return [m for m in repo.sent if m["type"] == "status"]


ORDERS = {"title": "Orders page", "summary": "Status column", "item_ids": ["1", "2"], "frontend": "significant"}


def test_batch_items_carry_their_size(tmp_path):
    md = tmp_path / "b.md"
    md.write_text("- [ ] A\n  The detail.\n  Size: M\n\n- [ ] B\n  Size: l\n\n- [ ] C\n", encoding="utf-8")
    items = ae.parse_items(md)
    assert [i["size"] for i in items] == ["M", "L", None] and items[0]["detail"] == "The detail."
    js = tmp_path / "b.json"
    js.write_text(json.dumps({"items": [{"title": "A", "size": "S"}, {"title": "B", "size": "XL?"}, {"title": "C"}]}))
    assert [i["size"] for i in ae.parse_items(js)] == ["S", None, None]


def test_the_planner_marks_groups_and_the_users_groups_inherit_them(repo):
    run = make_run(repo, [], phase="review")
    proposed = ae.normalise_groups(run, [{"title": "A", "item_ids": ["1"], "size": "L", "frontend": "significant"},
                                         {"title": "B", "item_ids": ["2"], "size": "S", "frontend": "bogus"}])
    assert proposed[0]["size"] == "L" and proposed[0]["frontend"] == "significant" and "frontend" not in proposed[1]
    assert ae.SCHEMA["properties"]["groups"]["items"]["properties"]["frontend"]["enum"] == list(ae.FRONTEND)
    mine = ae.inherit_marks([{"title": "All", "summary": "", "item_ids": ["1", "2"]}], proposed)
    assert mine[0]["size"] == "L" and mine[0]["frontend"] == "significant"
    # the group's size: the items' sizes when Ore sent them, else the planner's, else M
    assert ae.group_size(run, {"item_ids": ["1", "2"], "size": "L"}) == "M"
    run.s["items"] = [{**i, "size": None} for i in ITEMS]
    assert ae.group_size(run, {"item_ids": ["2"], "size": "S"}) == "S" and ae.group_size(run, {"item_ids": ["2"]}) == "M"


def test_starting_the_groups_goes_to_the_specialists(repo, monkeypatch):
    run = make_run(repo, [{"title": "Orders", "summary": "s", "item_ids": ["1", "2"], "frontend": "significant",
                           "size": "M"}], phase="review", pending={"key": "review-3"})
    monkeypatch.setattr(ae, "review_groups", lambda groups, prompt="", key=None: {
        "action": "start", "groups": [{"title": "Orders", "item_ids": ["1", "2"]}]})
    ae.review(run)
    assert run.s["phase"] == "checks" and run.s["groups"][0]["frontend"] == "significant"
    assert ae.run_phase(run) == "planning"
    assert [s["key"] for s in ae.stages(run)] == ["clarify", "review", "checks", "issues", "workflows"]


def test_the_question_round_end_to_end(repo, monkeypatch):
    sketch = repo.root / ".ore" / "runs" / "rq" / "files" / "1-sketch.png"
    sketch.parent.mkdir(parents=True)
    sketch.write_bytes(b"png")
    run = make_run(repo, [dict(ORDERS)])
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", fake_claude(repo, calls))
    ae.IO.answers.update({
        "risk-orders-page-1": {"action": "approve"},
        "design-orders-page-v1": {"action": "change", "feedback": "Make the status a badge",
                                  "files": [".ore/runs/rq/files/1-sketch.png"]},
        "design-orders-page-v2": {"action": "approve"},
        "build-1": {"action": "approve"}})
    ae.checks(run)
    assert run.s["phase"] == "issues" and ae.run_phase(run) == "building"

    asked = requests(repo)
    ids = [r["id"] for r in asked]
    assert sorted(ids[:3]) == ["design-orders-page-v1", "design-orders-page-v2", "risk-orders-page-1"]
    assert ids.index("design-orders-page-v1") < ids.index("design-orders-page-v2") and ids[-1] == "build-1"
    design = next(r for r in asked if r["id"] == "design-orders-page-v1")
    assert design == {"type": "input_request", "id": "design-orders-page-v1", "kind": "review", "gate": "design",
                      "part": "Orders page", "title": "Review the design: Orders page",
                      "prompt": "The designer made prototype v1 for Orders page. Open it and click through it, then "
                                "approve it or ask for changes.",
                      "attachments": [{"label": "Prototype v1", "path": ".ore/designs/rq/orders-page/v1.html",
                                       "kind": "design"}],
                      "summary": "The orders table (v1)."}
    risk = next(r for r in asked if r["id"] == "risk-orders-page-1")
    assert risk["gate"] == "risk" and risk["title"] == "Accept the risks: Orders page" and risk["attachments"] == []
    assert "Old orders have no status" in risk["summary"] and "needs your OK" in risk["summary"]
    build = asked[-1]
    assert build["gate"] == "build" and build["part"] is None and build["prompt"] == ae.BUILD_PROMPT
    assert build["attachments"] == [{"label": "Orders page: prototype v2", "path": ".ore/designs/rq/orders-page/v2.html",
                                     "kind": "design"}]
    assert "prototype v2 approved" in build["summary"] and "you accepted Old orders have no status" in build["summary"]

    # read-only sessions for tests and risks; the designer may write only in its folder, and continues its session
    by_kind = {}
    for cmd, text in calls:
        by_kind.setdefault(json.dumps(json.loads(cmd[cmd.index("--json-schema") + 1])["required"]), []).append((cmd, text))
    tests_cmd = by_kind['["summary", "plan"]'][0][0]
    assert tests_cmd[tests_cmd.index("--permission-mode") + 1] == "plan" and "Write" in tests_cmd
    assert "Order status" in by_kind['["summary", "plan"]'][0][1] and "All statuses" in by_kind['["summary", "plan"]'][0][1]
    (d1, m1), (d2, m2) = by_kind['["summary"]']
    assert "--permission-mode" not in d1 and "Write(.ore/designs/rq/orders-page/**)" in d1 and "Bash" in d1
    assert "--resume" not in d1 and d2[d2.index("--resume") + 1] == "s-design"
    assert "Make the status a badge" in m2 and str(sketch) in m2 and "v2.html" in m2
    assert (repo.root / ".ore/designs/rq/orders-page/v1.html").exists()     # earlier versions stay

    # parts: the gates and the specialists' notes, and input while a review is open
    parts = [p for s in statuses(repo) for p in s.get("parts") or []]
    assert any(p["status"] == "input" for p in parts) and any(p["status"] == "running" for p in parts)
    last = [s for s in statuses(repo) if s.get("parts")][-1]["parts"][0]
    gates = {g["key"]: g for g in last["gates"]}
    assert gates["design"]["state"] == "ok" and gates["risk"]["state"] == "ok" and gates["tests"]["state"] == "ok"
    assert gates["questions"] == {"key": "questions", "label": "Questions", "state": "ok", "note": "1 round answered"}
    notes = last["notes"]
    assert [n["author"] for n in notes].count("designer") == 2 and {"planning", "tests", "risk"} <= {
        n["author"] for n in notes}
    assert len({n["id"] for n in notes}) == len(notes)
    assert next(n for n in notes if n["author"] == "designer")["attachments"] == [
        {"label": "Prototype v1", "path": ".ore/designs/rq/orders-page/v1.html", "kind": "design"}]
    assert all(s["phase"] == "planning" for s in statuses(repo))
    assert run.s["usage"]["cost_usd"] > 0

    # the approved prototype is kept with the run and goes into the issue and the worktree
    g = run.s["groups"][0]
    assert g["design_version"] == 2 and Path(g["design_file"]) == run.dir / "designs" / "orders-page.html"
    assert Path(g["design_file"]).read_text() == (repo.root / ".ore/designs/rq/orders-page/v2.html").read_text()
    body = ae.build_sections(run, g)
    assert "## Approved design" in body and "specs/designs/orders-page.html" in body and g["design_file"] in body
    assert "## Test plan" in body and "- test_status" in body
    assert "## Accepted risks" in body and "Backfill them as Delivered." in body
    wt = repo.root / "trees" / "a1"
    wt.mkdir(parents=True)
    (repo.root / "agents" / "a1").mkdir(parents=True)
    (repo.root / "agents" / "a1" / "adw_state.json").write_text(json.dumps({"worktree_path": str(wt)}))
    g.update(adw_id="a1", status="running")
    ae.place_design(run, g)
    assert (wt / "specs" / "designs" / "orders-page.html").read_text() == Path(g["design_file"]).read_text()
    assert g["design_placed"] and "design_placed" in ae.RETRY_RESET
    # the building parts keep the notes and gates
    part = ae.parts_of(run, [g])[0]
    assert part["notes"] == g["notes"] and {x["key"] for x in part["gates"]} == {"design", "risk", "tests", "questions"}


def test_small_groups_skip_the_risks_and_the_prototype(repo, monkeypatch):
    run = make_run(repo, [{"title": "Typo", "summary": "", "item_ids": ["2"], "frontend": "small"}])
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", fake_claude(repo, calls))
    ae.IO.answers["build-1"] = {"action": "approve"}
    ae.checks(run)
    assert len(calls) == 1 and [r["id"] for r in requests(repo)] == ["build-1"]
    gates = {g["key"]: g for g in ae.gates(run, run.s["groups"][0])}
    assert gates["design"]["state"] == "skipped" and gates["risk"]["state"] == "skipped"
    assert gates["tests"]["state"] == "ok" and "design_file" not in run.s["groups"][0]


def test_an_open_review_survives_a_restart(repo, monkeypatch):
    run = make_run(repo, [dict(ORDERS)])
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", fake_claude(repo, calls, risks=()))
    with pytest.raises(EOFError):            # Ore went away while the review was open
        ae.checks(run)
    first = requests(repo)[-1]
    assert first["id"] == "design-orders-page-v1"
    saved = ae.Run(run.dir)
    assert saved.s["pending"]["request"] == first
    assert {k: saved.s["groups"][0]["prep"][k]["state"] for k in ae.CHECK_KINDS} == \
        {"tests": "ok", "risk": "ok", "design": "review"}
    n = len(calls)
    repo.sent.clear()
    monkeypatch.setattr(ae, "IO", ae.OreInput())
    ae.IO.enabled, ae.IO.closed = True, True
    ae.IO.answers.update({"design-orders-page-v1": {"action": "approve"}, "build-1": {"action": "approve"}})
    ae.checks(saved)
    assert requests(repo)[0] == first and len(calls) == n          # asked again with the same id; nothing rerun
    assert saved.s["phase"] == "issues"


def test_an_interrupted_session_runs_again(repo, monkeypatch):
    g = dict(ORDERS, frontend="none", slug="orders-page", prep={"tests": {"state": "running"},
                                                              "risk": {"state": "ok", "risks": []},
                                                              "design": {"state": "skipped"}})
    run = make_run(repo, [g])
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", fake_claude(repo, calls))
    ae.IO.answers["build-1"] = {"action": "approve"}
    ae.checks(run)
    assert len(calls) == 1 and run.s["groups"][0]["prep"]["tests"]["state"] == "ok"


def test_the_designer_may_not_touch_the_repository(repo, monkeypatch):
    run = make_run(repo, [dict(ORDERS, item_ids=["2"])])
    monkeypatch.setattr(ae.subprocess, "run", fake_claude(repo, []))
    seen = iter([{}, {"src/app.tsx": ("??", 1, 2)}])
    monkeypatch.setattr(ae, "git_changes", lambda: next(seen))
    with pytest.raises(RuntimeError, match=r"The designer changed files outside \.ore/ \(src/app\.tsx\)"):
        ae.checks(run)
    d = ae.Run(run.dir).s["groups"][0]["prep"]["design"]
    assert d["state"] == "failed" and "outside .ore/" in d["note"]
    assert not any(r["gate"] == "design" for r in requests(repo))


def test_git_changes_ignore_ore(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    out = " M src/app.tsx\n?? .ore/designs/rq/a/v1.html\nR  old.py -> new.py\n"
    monkeypatch.setattr(ae.subprocess, "run", lambda cmd, **kw: types.SimpleNamespace(returncode=0, stdout=out))
    assert set(ae.git_changes()) == {"src/app.tsx", "new.py"}


def test_a_failed_session_stops_the_run_and_resume_runs_it_again(repo, monkeypatch):
    run = make_run(repo, [dict(ORDERS, item_ids=["2"], frontend="none")])
    bad = types.SimpleNamespace(returncode=1, stdout="", stderr="boom")
    monkeypatch.setattr(ae.subprocess, "run", lambda cmd, **kw: bad)
    with pytest.raises(RuntimeError, match="The test planner couldn't finish Orders page: boom"):
        ae.checks(run)
    assert ae.Run(run.dir).s["groups"][0]["prep"]["tests"]["state"] == "failed"
    monkeypatch.setattr(ae.subprocess, "run", fake_claude(repo, []))
    ae.IO.answers["build-1"] = {"action": "approve"}
    saved = ae.Run(run.dir)
    ae.checks(saved)
    assert saved.s["phase"] == "issues"


def test_asking_for_changes_at_the_build_check_goes_back_to_the_questions(repo, monkeypatch):
    v1 = repo.root / ".ore/designs/rq/orders-page/v1.html"
    v1.parent.mkdir(parents=True)
    v1.write_text("<html>v1</html>")
    g = dict(ORDERS, slug="orders-page", notes=[], note_seq=3, prep={
        "tests": {"state": "ok", "summary": "s", "plan": "p", "session": "s-tests"},
        "risk": {"state": "ok", "risks": [], "round": 1, "session": "s-risk"},
        "design": {"state": "ok", "version": 1, "approved": 1, "session": "s-design"}})
    run = make_run(repo, [g])
    ae.IO.answers["build-1"] = {"action": "change", "feedback": "Add a date filter"}
    ae.checks(run)
    assert run.s["phase"] == "clarify" and run.s["groups"] == [] and run.s["checked_groups"][0]["title"] == "Orders page"
    assert "Add a date filter" in run.s["next_message"] and "recheck" in run.s["next_message"]
    assert "Prototype v1 approved" in run.s["next_message"]
    # while Claude plans again, the checked groups stay on the board as parts
    ae.report(run, "x")
    assert [p["key"] for p in statuses(repo)[-1]["parts"]] == ["Orders page"]
    # Claude keeps the groups and says the change affects the design: straight back to the designer
    monkeypatch.setattr(ae, "claude_turn", lambda run_, message: {"status": "ready", "groups": [
        {"title": "Orders and checkout", "item_ids": ["2", "1"], "frontend": "significant", "recheck": ["design"]}]})
    ae.clarify(run)
    g = run.s["groups"][0]
    assert run.s["phase"] == "checks" and g["title"] == "Orders page" and "checked_groups" not in run.s
    assert g["prep"]["design"]["state"] == "pending" and g["prep"]["tests"]["state"] == "ok"
    assert g["prep"]["design"]["feedback"]["text"] == "Add a date filter"
    assert g["prep"]["user_notes"][0]["text"] == "At the build check: Add a date filter"
    calls = []
    monkeypatch.setattr(ae.subprocess, "run", fake_claude(repo, calls))
    ae.IO.answers.update({"design-orders-page-v2": {"action": "approve"}, "build-2": {"action": "approve"}})
    ae.checks(run)
    assert len(calls) == 1 and calls[0][0][calls[0][0].index("--resume") + 1] == "s-design"
    assert "Add a date filter" in calls[0][1] and run.s["phase"] == "issues"
    assert "At the build check: Add a date filter" in ae.build_sections(run, g)


def test_messages_while_planning_are_notes(repo, monkeypatch):
    f = repo.root / ".ore/runs/rq/files/1-brief.pdf"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"%PDF")
    run = make_run(repo, [dict(ORDERS, slug="orders-page", prep={k: {"state": "ok"} for k in ae.CHECK_KINDS})])
    ae.IO.messages = [{"type": "message", "id": "m1", "part": "Orders page", "text": "Use the brand colours",
                       "files": [".ore/runs/rq/files/1-brief.pdf", "/etc/passwd"]},
                      {"type": "message", "id": "m2", "part": "Nope", "text": "x"}]
    ae.handle_messages(run)
    replies = {m["to"]: m["text"] for m in repo.sent if m["type"] == "reply"}
    assert replies["m1"].startswith("Noted.") and "no group called 'Nope'" in replies["m2"]
    note = run.s["groups"][0]["prep"]["user_notes"][0]
    assert note["text"] == "Use the brand colours" and note["files"] == [str(f)]       # outside .ore/: dropped
    assert "Use the brand colours" in ae.group_context(run, run.s["groups"][0]) and str(f) in ae.build_sections(
        run, run.s["groups"][0])
    run.s["phase"] = "clarify"
    ae.IO.messages = [{"type": "message", "id": "m3", "part": None, "text": "Keep it simple", "from": "Konrad"}]
    ae.handle_messages(run)
    assert run.s["planning_notes"] == ["Konrad wrote while you plan: Keep it simple"]


def test_files_on_answers_and_messages_reach_the_sessions_and_workflows(repo, monkeypatch):
    f = repo.root / ".ore/runs/rq/files/1-shot.png"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"png")
    assert ae.split_files({"text": "See this", "files": [".ore/runs/rq/files/1-shot.png"]}) == ("See this", [str(f)])
    assert ae.split_files({"Q?": "A", "files": []}) == ({"Q?": "A"}, [])
    assert ae.split_files("plain") == ("plain", [])
    # the planning questions: the files go to Claude with the answers
    run = make_run(repo, [], phase="clarify", pending={"key": "clarify-1", "questions": [{"question": "Q?"}]})
    monkeypatch.setattr(ae, "ask_questions", lambda qs, prompt="", key=None: {
        "Q?": "Like this", "files": [".ore/runs/rq/files/1-shot.png"]})
    seen = []
    monkeypatch.setattr(ae, "claude_turn", lambda run_, message: seen.append(message) or {"status": "ready", "groups": [
        {"title": "All", "item_ids": ["1", "2"]}]})
    ae.clarify(run)
    assert "Like this" in seen[0] and str(f) in seen[0] and '"files"' not in seen[0]
    # a workflow's message and an answer to its question
    g = {"title": "W", "status": "running", "adw_id": "a9", "workflow": "orchestrated", "item_ids": ["1"]}
    run.s.update(phase="workflows", groups=[g], asks=[{"id": "ask-9-1", "group": "W", "adw_id": "a9", "n": 1,
                                                        "question": "?", "options": [], "state": "open"}])
    (repo.root / "agents" / "a9").mkdir(parents=True)
    ae.IO.messages = [{"type": "message", "id": "m1", "part": "W", "text": "Look", "mode": "amend",
                       "files": [".ore/runs/rq/files/1-shot.png"]}]
    ae.handle_messages(run)
    ae.IO.answers["ask-9-1"] = {"text": "This one", "files": [".ore/runs/rq/files/1-shot.png"]}
    ae.poll_asks(run)
    inbox = [json.loads(x) for x in (repo.root / "agents/a9/inbox.jsonl").read_text().splitlines()]
    assert inbox[0]["files"] == [str(f)] and str(f) in inbox[0]["text"]
    assert inbox[1]["type"] == "answer" and inbox[1]["text"].startswith("This one") and inbox[1]["files"] == [str(f)]


def test_cleanup_removes_the_runs_prototypes_and_files(repo, monkeypatch):
    run = make_run(repo, [], phase="checks")
    for d in ("designs", "runs"):
        (repo.root / ".ore" / d / "rq").mkdir(parents=True)
    (repo.root / ".ore" / "designs" / "other").mkdir()
    monkeypatch.setattr(ae, "result", lambda summary, **kw: None)
    ae.clean(run.dir, set())
    assert not (repo.root / ".ore/designs/rq").exists() and not (repo.root / ".ore/runs/rq").exists()
    assert (repo.root / ".ore/designs/other").exists()


@pytest.mark.parametrize("name,words", [("designer", ["self-contained", "data: URIs", "Accessible", "frontend"]),
                                        ("risk", ["needs_acceptance", "Data", "Security", "Breaking"]),
                                        ("tests", ["acceptance criterion", "unit", "end-to-end"])])
def test_the_round_specialists_have_prompts_and_fallbacks(monkeypatch, tmp_path, name, words):
    monkeypatch.setattr(ae, "REPO_ROOT", Path(__file__).resolve().parents[2])
    text = ae.specialist_prompt(name, ae.ROUND_FALLBACKS)
    assert text != ae.ROUND_FALLBACKS[name] and all(w in text for w in words) and "given schema" in text
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    assert ae.specialist_prompt(name, ae.ROUND_FALLBACKS) == ae.ROUND_FALLBACKS[name]
    assert "never commit" in ae.ROUND_FALLBACKS[name] or "never commit or" in ae.ROUND_FALLBACKS[name]


def test_simulate_runs_the_question_round(tmp_path):
    """--simulate end to end: the specialists' notes and gates on the parts, the reviews, a prototype on disk."""
    from adw_tests import ore_harness
    repo = tmp_path / "repo"
    shutil.copytree(ADWS, repo / "adws", ignore=shutil.ignore_patterns("__pycache__", "agents", "trees"))
    env = {"ORE_SIM_SPEED": "10", "PYTHONPATH": os.environ.get("PYTHONPATH", "")}
    code, msgs, err = ore_harness.run([str(repo / "adws" / "adw_triggers" / "trigger_ore.py"), "--simulate"],
                                      env=env, timeout=300)
    assert code == 0, err[-2000:]
    reviews = [m for m in msgs if m["type"] == "input_request" and m.get("kind") == "review"]
    assert {r["gate"] for r in reviews} == {"risk", "design", "build"} and reviews[-1]["gate"] == "build"
    design = next(r for r in reviews if r["gate"] == "design")
    assert (repo / design["attachments"][0]["path"]).read_text().startswith("<!doctype html>")
    planning = [m for m in msgs if m["type"] == "status" and m.get("phase") == "planning" and m.get("parts")]
    assert planning and all({g["key"] for g in p["gates"]} == {"design", "risk", "tests", "questions"}
                            for m in planning for p in m["parts"])
    building = [m for m in msgs if m["type"] == "status" and m.get("phase") == "building" and m.get("parts")][-1]
    first = building["parts"][0]
    assert {"planning", "tests", "risk", "designer"} <= {n["author"] for n in first["notes"]}
