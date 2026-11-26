#!/usr/bin/env python3
"""Tests for structured step reporting (adw_modules/steps.py) and the flow the Ore trigger builds from it.

Run: uv run --with pytest --with pydantic --with python-dotenv pytest adws/adw_tests/test_steps.py
"""

import json
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adw_modules import steps  # noqa: E402
from adw_triggers import trigger_ore as ae  # noqa: E402


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo root in tmp: steps.py and the trigger both use its agents/ folder."""
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(steps, "steps_path", lambda adw_id: str(ae.steps_file(adw_id)))
    monkeypatch.setattr(steps, "_open", {})
    return tmp_path


def lines(adw_id):
    return [json.loads(ln) for ln in ae.steps_file(adw_id).read_text(encoding="utf-8").splitlines()]


def by_key(nodes):
    return {n["key"]: n for n in nodes}


def test_record_appends_one_line_per_event(repo):
    steps.record("a1", "build", "running")
    steps.record("a1", "build", "done", note="  all\ngood ")
    steps.route("a1", "/feature", "multi-phase", "Multi-phase SDLC")
    steps.plan("a1", [("p1", "Data model"), ("p2", None)])
    out = lines("a1")
    assert [e["status"] for e in out] == ["running", "done", "done", "planned"]
    assert set(out[0]) == {"ts", "key", "parent", "label", "status", "note"}
    assert len(out[0]["ts"]) == 19 and out[0]["ts"][10] == "T"            # local ISO, seconds
    assert out[1]["note"] == "all good"
    assert out[2]["key"] == "route" and out[2]["type"] == "feature" and out[2]["workflow"] == "Multi-phase SDLC"
    assert out[3]["phases"] == [{"id": "p1", "name": "Data model"}, {"id": "p2", "name": "p2"}]


def test_recording_never_raises(monkeypatch):
    def broken(adw_id):
        raise OSError("disk full")

    monkeypatch.setattr(steps, "steps_path", broken)
    steps.record("a1", "build", "running")
    steps.route("a1", None, None, None)
    steps.plan("a1", None)                       # not even a bad phase list
    steps.record(None, "x", "done")


def test_run_main_fails_what_was_left_running(repo):
    def main():
        steps.record("a2", "p1", "running", label="Phase 1", parent="phases")
        steps.record("a2", "build", "running", parent="p1")
        sys.exit("Build broke")

    with pytest.raises(SystemExit):
        steps.run_main(main)
    out = lines("a2")[2:]
    assert [(e["key"], e["status"], e["note"]) for e in out] == [("build", "failed", "Build broke"),
                                                                  ("p1", "failed", "Build broke")]
    assert out[1]["label"] == "Phase 1" and out[1]["parent"] == "phases"


def test_child_env_puts_child_steps_under_a_parent(monkeypatch):
    monkeypatch.delenv(steps.PARENT_ENV, raising=False)
    assert steps.inherited_parent() is None
    monkeypatch.setattr(os, "environ", steps.child_env("integration"))
    assert steps.inherited_parent() == "integration"


def multi_phase_run(adw_id):
    """What adw_sdlc_router_iso + adw_multi_phase_sdlc_iso record, part way through phase 2."""
    steps.record(adw_id, "route", "running", label="Route")
    steps.route(adw_id, "/feature", "multi-phase", "Multi-phase SDLC")
    steps.record(adw_id, "setup", "running", label="Setup")
    steps.record(adw_id, "setup", "done", label="Setup")
    steps.record(adw_id, "plan", "running", label="Plan")
    steps.plan(adw_id, [("phase-1", "Data model"), ("phase-2", "API"), ("phase-3", "UI")])
    steps.record(adw_id, "plan", "done", label="Plan", note="3 phases")
    steps.record(adw_id, "phase-1", "running", label="Data model", parent="phases")
    for k in ("build", "test", "review", "commit"):
        steps.record(adw_id, k, "running", parent="phase-1")
        steps.record(adw_id, k, "done", parent="phase-1")
    steps.record(adw_id, "phase-1", "done", label="Data model", parent="phases")
    steps.record(adw_id, "phase-2", "running", label="API", parent="phases")
    steps.record(adw_id, "build", "running", parent="phase-2")
    steps.record(adw_id, "build", "done", parent="phase-2")
    steps.record(adw_id, "test", "running", parent="phase-2")
    steps.record(adw_id, "test", "failed", parent="phase-2", note="2 tests failed: test_a, test_b")
    steps.record(adw_id, "test", "running", parent="phase-2", note="Retry 1")


def test_multi_phase_flow(repo):
    multi_phase_run("m1")
    tree, route = ae.build_steps(ae.read_steps("m1"))
    assert route == {"type": "feature", "complexity": "multi-phase", "workflow": "Multi-phase SDLC"}
    assert [n["key"] for n in tree] == ["route", "setup", "plan", "phases", "integration", "pr"]
    top = by_key(tree)
    assert top["plan"]["note"] == "3 phases" and top["plan"]["status"] == "done"
    phases = top["phases"]["steps"]
    assert [(p["key"], p["label"], p["status"]) for p in phases] == [
        ("phase-1", "Data model", "done"), ("phase-2", "API", "running"), ("phase-3", "UI", "pending")]
    assert top["phases"]["status"] == "running" and top["phases"]["started"]          # derived from the phases
    p2 = by_key(phases[1]["steps"])
    assert [s["key"] for s in phases[1]["steps"]] == ["build", "test", "review", "commit"]
    assert p2["test"]["status"] == "running" and p2["test"]["note"] == "Retry 1"
    assert [(a["status"], a["note"]) for a in p2["test"]["attempts"]] == [
        ("failed", "2 tests failed: test_a, test_b"), ("running", "Retry 1")]
    assert p2["review"]["status"] == "pending" and p2["review"]["attempts"] == []
    assert [s["key"] for s in top["integration"]["steps"]] == ["build", "tests", "smoke", "review", "docs"]
    assert top["integration"]["status"] == "pending" and top["pr"]["status"] == "pending"


def test_part_carries_the_flow(repo):
    multi_phase_run("m2")
    (repo / "agents" / "m2" / "adw_state.json").write_text(json.dumps(
        {"adw_id": "m2", "branch_name": "feature-issue-26-adw-m2", "worktree_path": "/repo/trees/m2"}))
    g = {"title": "Orders", "status": "running", "issue_number": "26", "issue_url": "https://github.com/o/r/issues/26",
         "adw_id": "m2", "started_at": time.time() - 60, "message": "Re-running tests", "progress": 0.0,
         "log": [{"time": "2026-11-04T09:04:44", "text": "Starting phase: phase-2"}]}

    class R:
        s = {"groups": [g]}

    part = ae.parts(R())[0]
    assert set(part) >= {"key", "label", "status", "message", "progress", "links", "started", "route", "steps",
                         "details", "log"}
    assert "ended" not in part
    assert part["details"] == [{"label": "Branch", "value": "feature-issue-26-adw-m2"}, {"label": "ADW id", "value": "m2"},
                               {"label": "Worktree", "value": "/repo/trees/m2"}]
    # leaves: route, setup, plan, pr + 3 phases x 4 + integration x 5 = 21; finished: 3 + 4 (phase 1) + 1 (build)
    assert part["progress"] == round(8 / 21, 3)
    assert part["message"] == "API · Test: Re-running tests"
    json.dumps(part)                                                   # it all goes to Ore as JSON


def test_sdlc_skeleton_and_old_adws(repo):
    steps.record("s1", "route", "running", label="Route")
    steps.route("s1", "/bug", "single-phase", "SDLC")
    steps.record("s1", "plan", "running")
    tree, route = ae.build_steps(ae.read_steps("s1"))
    assert [n["key"] for n in tree] == ["route", "plan", "build", "test", "smoke", "review", "docs", "domain_docs", "pr"]
    assert [n["status"] for n in tree][:3] == ["done", "running", "pending"] and route["type"] == "bug"
    # before the router decides, only the route is known
    steps.record("s0", "route", "running", label="Route")
    assert [n["key"] for n in ae.build_steps(ae.read_steps("s0"))[0]] == ["route"]
    # an older ADW without steps.jsonl: no steps; the route type comes from its state
    (repo / "agents" / "old").mkdir(parents=True)
    (repo / "agents" / "old" / "adw_state.json").write_text(json.dumps({"issue_class": "/chore"}))
    f = ae.flow({"adw_id": "old", "status": "running"})
    assert "steps" not in f and f["route"] == {"type": "chore"}


def test_a_failed_workflow_leaves_nothing_running(repo):
    steps.record("f1", "route", "running", label="Route")
    steps.route("f1", "/feature", "single-phase", "SDLC")
    steps.record("f1", "plan", "running")
    f = ae.flow({"adw_id": "f1", "status": "failed", "started_at": 1, "ended_at": 2})
    assert by_key(f["steps"])["plan"]["status"] == "failed" and f["ended"]


def test_run_stages(repo):
    run = ae.Run(repo / "agents" / "ore" / "r1")
    run.s = {"phase": "clarify", "groups": [], "question_rounds": 2}
    ae.stage_start(run, "clarify")
    st = ae.stages(run)
    assert [(s["key"], s["label"], s["status"]) for s in st] == [
        ("clarify", "Questions", "running"), ("review", "Your check", "pending"), ("issues", "Issues", "pending"),
        ("workflows", "Workflows", "pending")]
    assert st[0]["note"] == "2 rounds" and st[0]["started"] and st[0]["ended"] is None
    run.s["groups"] = [{"title": t, "issue_number": n, "status": "running"} for t, n in (("A", "26"), ("B", "34"))]
    ae.stage_end(run, "clarify", "2 rounds")
    for k in ("review", "issues"):
        ae.stage_start(run, k)
        ae.stage_end(run, k)
    run.s["phase"] = "workflows"
    ae.stage_start(run, "workflows")
    st = {s["key"]: s for s in ae.stages(run)}
    assert [s["status"] for s in st.values()] == ["done", "done", "done", "running"]
    assert st["review"]["note"] == "2 workflows" and st["issues"]["note"] == "#26–#34"
    assert st["workflows"]["note"] == "2 running"


def test_dry_run_simulates_steps(repo, monkeypatch):
    monkeypatch.setenv("ORE_WORKFLOW", "router")          # the classic workflows' simulation
    run = ae.Run(repo / "agents" / "ore" / "r2")
    run.dir.mkdir(parents=True)
    groups = [{"title": t, "status": "queued", "issue_number": f"dry-r2-{n}", "issue_url": None}
              for n, t in enumerate(("Footer", "Orders"), 1)]
    run.s = {"run_id": "r2", "dry_run": True, "groups": groups, "phase": "workflows", "stages": {}}
    for g in groups:
        ae.start_adw(run, g)
        g["started_at"] -= 1000                 # long enough ago for the whole script
    sent = []
    ae_status = ae.status
    try:
        ae.status = lambda *a, **kw: sent.append(kw)
        ae.time.sleep, sleep = (lambda s: None), ae.time.sleep
        ae.result = lambda *a, **kw: None
        ae.workflows(run)
    finally:
        ae.status, ae.time.sleep = ae_status, sleep
    last = sent[-1]
    assert [s["status"] for s in last["stages"]] == ["done", "done", "done", "done"]
    assert last["stages"][2]["note"] == "2 issues (dry run)" and last["stages"][3]["note"] == "2 done"
    sdlc, multi = last["parts"]
    assert sdlc["status"] == "done" and multi["status"] == "done"
    assert by_key(sdlc["steps"])["test"]["attempts"][0]["note"] == "1 test failed: test_footer_version"
    assert by_key(sdlc["steps"])["pr"]["note"].startswith("PR #1")
    assert multi["route"]["workflow"] == "Multi-phase SDLC"
    phases = by_key(multi["steps"])["phases"]["steps"]
    assert [p["label"] for p in phases] == ["Data model", "API and UI"]
    assert len(by_key(phases[1]["steps"])["review"]["attempts"]) == 2
    assert sdlc["log"][-1]["text"] == "SDLC workflow completed" and len(sdlc["log"]) <= 10
