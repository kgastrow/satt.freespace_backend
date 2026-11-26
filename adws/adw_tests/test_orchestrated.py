#!/usr/bin/env python3
"""Tests for the orchestrated SDLC workflow: adw_report.py, adw_run_suites.py, the read-only guard, the
orchestrator script's pieces that run without Claude/GitHub, and the Ore trigger's handling of it.

Run: uv run --with pytest --with pydantic --with python-dotenv pytest adws/adw_tests/test_orchestrated.py
"""

import json
import os
import sys
import time
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adw_orchestrated_sdlc_iso as orch  # noqa: E402
import adw_report  # noqa: E402
import adw_run_suites as suites  # noqa: E402
from adw_modules import github, messages, orchestrated_sim, steps  # noqa: E402
from adw_triggers import trigger_ore as ae  # noqa: E402
from orchestrator import readonly_guard as guard  # noqa: E402


COMMENTS: list = []          # (issue, text) of every comment a test's code posted


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo root in tmp: steps, the trigger, the orchestrator's files and suite slots all live under it."""
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(steps, "steps_path", lambda adw_id: str(ae.steps_file(adw_id)))
    monkeypatch.setattr(steps, "_open", {})
    monkeypatch.setattr(orch, "MAIN_ROOT", str(tmp_path))
    monkeypatch.setattr(suites, "SLOTS_DIR", str(tmp_path / "trees" / ".suite_slots"))
    monkeypatch.setattr(suites, "ACTIVE_DIR", str(tmp_path / "trees" / ".active_adws"))
    monkeypatch.setattr(suites, "MAIN_ROOT", str(tmp_path))
    COMMENTS.clear()
    monkeypatch.setattr(github, "_record_progress", lambda issue, text: COMMENTS.append((str(issue), text)))
    monkeypatch.setattr(github, "make_issue_comment", lambda issue, text: COMMENTS.append((str(issue), text)))
    return tmp_path


def lines(adw_id):
    return [json.loads(ln) for ln in ae.steps_file(adw_id).read_text(encoding="utf-8").splitlines()]


def by_key(nodes):
    return {n["key"]: n for n in nodes}


# ---- adw_report.py -------------------------------------------------------------

def test_report_step_writes_steps_jsonl(repo):
    assert adw_report.main(["--adw-id", "o1", "step", "api", "running", "--parent", "work", "--label", "Orders API"]) == 0
    assert adw_report.main(["--adw-id", "o1", "step", "api", "done", "--parent", "work", "--note", "3 files\n 5 tests"]) == 0
    out = lines("o1")
    assert [(e["key"], e["parent"], e["status"]) for e in out] == [("api", "work", "running"), ("api", "work", "done")]
    assert out[0]["label"] == "Orders API" and out[1]["note"] == "3 files 5 tests"


def test_report_rejects_bad_input(repo, monkeypatch):
    monkeypatch.delenv("ADW_ID", raising=False)
    assert adw_report.main(["--adw-id", "o2", "step", "api", "finished"]) == 2
    assert adw_report.main(["--adw-id", "o2", "step", "a b", "done"]) == 2
    assert not ae.steps_file("o2").exists()
    assert adw_report.main(["step", "api", "done"]) == 2           # no ADW id at all


def test_report_reads_adw_id_from_env(repo, monkeypatch):
    monkeypatch.setenv("ADW_ID", "o3")
    assert adw_report.main(["step", "integrate", "running"]) == 0
    assert lines("o3")[0]["key"] == "integrate"


def test_report_plan_records_packages_under_work(repo):
    assert adw_report.main(["--adw-id", "o4", "plan", "--package", "model=Order model",
                            "--package", "api=Orders API:model", "--package", "ui=Fix: the page:model,api"]) == 0
    planned, plan = lines("o4")
    assert planned["key"] == "work" and planned["status"] == "planned"
    assert planned["phases"] == [{"id": "model", "name": "Order model"},
                                 {"id": "api", "name": "Orders API", "after": ["model"]},
                                 {"id": "ui", "name": "Fix: the page", "after": ["model", "api"]}]
    assert (plan["key"], plan["status"], plan["note"]) == ("plan", "done", "3 packages")
    tree, _ = ae.build_steps(ae.read_steps("o4"))
    work = by_key(tree)["work"]
    assert [(s["key"], s["label"], s["status"]) for s in work["steps"]] == [
        ("model", "Order model", "pending"), ("api", "Orders API", "pending"), ("ui", "Fix: the page", "pending")]
    assert (repo / "agents" / "o4" / "orchestrator" / "plan.json").exists()


def test_report_result_validates_and_writes(repo):
    path = repo / "agents" / "rs1" / "result.json"
    run = lambda *a: adw_report.main(["--adw-id", "rs1", "result", *a])  # noqa: E731
    assert run("pr_opened", "--summary", "Orders page", "--pr-url", "https://github.com/o/r/pull/4",
               "--review-rounds", "2") == 0
    assert json.loads(path.read_text()) == {"status": "pr_opened", "summary": "Orders page",
                                            "pr_url": "https://github.com/o/r/pull/4", "review_rounds": 2}
    assert not [p for p in path.parent.iterdir() if p.name.endswith(".tmp")]              # written atomically
    assert run("failed", "--summary", "s", "--reason", "4 rounds", "--blocker", "a", "--blocker", "b", "--force") == 0
    assert json.loads(path.read_text()) == {"status": "failed", "summary": "s", "reason": "4 rounds",
                                            "open_blockers": ["a", "b"], "force": True}
    assert orch.messages.read_result(str(path))["force"] is True
    assert run("--json", json.dumps({"status": "failed", "summary": "j", "open_blockers": ["x"]})) == 0
    assert json.loads(path.read_text()) == {"status": "failed", "summary": "j", "open_blockers": ["x"]}
    before = path.read_text()
    for bad in (["done", "--summary", "s"],                                      # not a status
                ["pr_opened"],                                                   # no summary
                ["--json", '{"status": "failed", "summary": "s", "extra": 1}'],  # unknown field
                ["--json", '{"status": "failed", "summary": "s", "review_rounds": "2"}'],
                ["--json", "not json"],
                ["--json", "{}", "--summary", "s"]):
        assert run(*bad) == 2, bad
    assert path.read_text() == before                                            # nothing written


def test_parse_package_colon_in_name():
    assert adw_report.parse_package("x=Fix: login") == {"id": "x", "name": "Fix: login"}
    assert adw_report.parse_package("x=Login:a,b") == {"id": "x", "name": "Login", "after": ["a", "b"]}
    with pytest.raises(ValueError):
        adw_report.parse_package("bad id=x")


def test_report_comment_posts_an_adw_comment(repo, monkeypatch):
    posted = []
    monkeypatch.setattr(github, "make_issue_comment", lambda issue, text: posted.append((issue, text)))
    monkeypatch.setenv("ADW_ISSUE_NUMBER", "42")
    assert adw_report.main(["--adw-id", "o5", "comment", "Plan: 2 packages"]) == 0
    assert posted == [("42", "[ADW-AGENTS] o5_orchestrator: Plan: 2 packages")]


def test_report_comment_never_fails_the_caller(repo, monkeypatch):
    def broken(issue, text):
        raise RuntimeError("GitHub auth error")

    monkeypatch.setattr(github, "make_issue_comment", broken)
    assert adw_report.main(["--adw-id", "o6", "--issue", "7", "comment", "hi"]) == 0


# ---- the trigger -------------------------------------------------------------------

def test_trigger_workflow_mode_from_env(monkeypatch):
    monkeypatch.delenv("ORE_WORKFLOW", raising=False)
    assert ae.workflow_mode() == "orchestrated"                 # the default
    monkeypatch.setenv("ORE_WORKFLOW", "Router")
    assert ae.workflow_mode() == "router"                       # the opt-out
    monkeypatch.setenv("ORE_WORKFLOW", "something-else")
    assert ae.workflow_mode() == "orchestrated"


def test_router_sends_every_issue_to_the_orchestrated_workflow_by_default(monkeypatch):
    import adw_sdlc_router_iso as router
    monkeypatch.delenv("ADW_ORCHESTRATED", raising=False)
    assert router.orchestrated_enabled()
    for off in ("0", "false", "No", "off"):
        monkeypatch.setenv("ADW_ORCHESTRATED", off)
        assert not router.orchestrated_enabled()
    for on in ("1", "", "yes"):
        monkeypatch.setenv("ADW_ORCHESTRATED", on)
        assert router.orchestrated_enabled()


@pytest.mark.parametrize("mode,script", [("router", ae.ROUTER), ("orchestrated", ae.ORCHESTRATED)])
def test_trigger_launches_the_chosen_workflow(repo, monkeypatch, mode, script):
    monkeypatch.setenv("ORE_WORKFLOW", mode)
    launched = []

    class FakeProc:
        pid = 4242

        def poll(self):
            return None

    monkeypatch.setattr(ae.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd) or FakeProc())
    monkeypatch.setattr(ae.os, "getpgid", lambda pid: pid, raising=False)

    class FakeState:
        def __init__(self, adw_id):
            self.data = {}

        def update(self, **kw):
            self.data.update(kw)

        def save(self, *_):
            pass

    monkeypatch.setattr(ae, "ADWState", FakeState)
    run = types.SimpleNamespace(s={"dry_run": False, "groups": []}, dir=repo / "agents" / "ore" / "r1")
    g = {"title": "Orders", "issue_number": "26"}
    ae.start_adw(run, g)
    assert launched and launched[0][2].endswith(script) and launched[0][3] == "26"
    assert g["workflow"] == mode and g["status"] == "running"


def test_trigger_skeleton_for_orchestrated(repo):
    steps.record("t1", "route", "running", label="Route")
    steps.route("t1", "/feature", "dynamic", "Orchestrated SDLC")
    steps.record("t1", "setup", "running", label="Setup")
    tree, route = ae.build_steps(ae.read_steps("t1"))
    assert route == {"type": "feature", "complexity": "dynamic", "workflow": "Orchestrated SDLC"}
    assert [n["key"] for n in tree] == ["route", "setup", "plan", "work", "integrate", "screens", "review", "docs",
                                        "check", "pr"]
    assert [n["status"] for n in tree] == ["done", "running"] + ["pending"] * 8
    # without a route record (e.g. an older router), the work steps still identify the workflow
    steps.record("t2", "api", "running", parent="work", label="API")
    assert [n["key"] for n in ae.build_steps(ae.read_steps("t2"))[0]][3] == "work"


def sim_into(adw_id, upto=None):
    path = ae.steps_file(adw_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for event, _ in orchestrated_sim.EVENTS[:upto]:
            if event:
                f.write(json.dumps({"ts": ae.now_iso(), "parent": None, "label": None, "note": "", **event}) + "\n")


def test_orchestrated_flow_parallel_packages_and_attempts(repo):
    # part way: model done, api and ui running in parallel
    upto = next(i for i, (e, _) in enumerate(orchestrated_sim.EVENTS) if e and e["key"] == "ui") + 1
    sim_into("t3", upto)
    tree, _ = ae.build_steps(ae.read_steps("t3"))
    work = by_key(tree)["work"]
    assert [(s["key"], s["status"]) for s in work["steps"]] == [("model", "done"), ("api", "running"),
                                                                 ("ui", "running")]
    assert work["status"] == "running" and work["started"]                     # derived from its packages
    assert ae._current(tree) == "Work · Orders API"
    # the whole run
    sim_into("t4")
    tree, _ = ae.build_steps(ae.read_steps("t4"))
    top = by_key(tree)
    assert all(n["status"] == "done" for n in tree)
    review = top["review"]
    assert [(a["status"], a["note"]) for a in review["attempts"]] == [
        ("failed", "Round 1: 2 blockers: list endpoint misses organization_id filter"),
        ("done", "Round 2: passed, 1 warning")]
    # a run after a failed one is a new attempt; a run after a passing one replaces it (trigger semantics)
    assert [a["status"] for a in top["integrate"]["attempts"]] == ["failed", "done"]
    assert top["integrate"]["note"].startswith("Run 3: ")
    assert top["pr"]["note"].startswith("PR #3")


def test_trigger_dry_run_with_orchestrated_workflows(repo, monkeypatch):
    monkeypatch.setenv("ORE_WORKFLOW", "orchestrated")
    run = ae.Run(repo / "agents" / "ore" / "r9")
    run.dir.mkdir(parents=True)
    groups = [{"title": t, "status": "queued", "issue_number": f"dry-r9-{n}", "issue_url": None}
              for n, t in enumerate(("Orders", "Invoices"), 1)]
    run.s = {"run_id": "r9", "dry_run": True, "groups": groups, "phase": "workflows", "stages": {}}
    for g in groups:
        ae.start_adw(run, g)
        g["started_at"] -= 1000
    sent = []
    monkeypatch.setattr(ae, "status", lambda *a, **kw: sent.append(kw))
    monkeypatch.setattr(ae.time, "sleep", lambda s: None)
    monkeypatch.setattr(ae, "result", lambda *a, **kw: None)
    ae.workflows(run)
    parts = sent[-1]["parts"]
    for part in parts:
        assert part["status"] == "done" and part["route"]["workflow"] == "Orchestrated SDLC"
        assert [s["label"] for s in by_key(part["steps"])["work"]["steps"]] == [
            "Order model + migration", "Orders API", "Orders page"]
        assert len(by_key(part["steps"])["review"]["attempts"]) == 2
        assert any("pull/3" in link[1] for link in part["links"])


# ---- the workflow script (no Claude, no GitHub) -------------------------------------

def test_script_dry_run_records_a_full_run(repo):
    orch.dry_run("12", "d1", delay=0)
    tree, route = ae.build_steps(ae.read_steps("d1"))
    assert route["workflow"] == "Orchestrated SDLC"
    assert [n["status"] for n in tree] == ["done"] * 10
    texts = [t for _, t in COMMENTS]
    assert texts[0].startswith("[ADW-AGENTS] d1_orchestrator: ")
    assert "Orchestrated SDLC workflow completed" in texts[-1]
    g = {"issue_number": "12", "offset": 0}                       # the trigger's progress reading understands it
    monkey_path = repo / "agents" / "progress" / "issue-12.jsonl"
    monkey_path.parent.mkdir(parents=True, exist_ok=True)
    monkey_path.write_text("".join(json.dumps({"ts": "t", "comment": t}) + "\n" for t in texts), encoding="utf-8")
    ae.read_progress(g)
    assert g.get("completed") and g["pr_url"] == orchestrated_sim.PR_URL


def test_agent_definitions(monkeypatch):
    monkeypatch.setenv("ADW_ORCH_IMPL_MODEL", "claude-sonnet-test")
    monkeypatch.delenv("ADW_ORCH_REVIEW_MODEL", raising=False)
    agents = orch.agent_definitions("uv run SUITES", "python3 GUARD")
    assert set(agents) == {"adw-implementer", "adw-implementer-hard", "adw-investigator", "adw-reviewer",
                           "adw-ui-checker"}
    rev = agents["adw-reviewer"]
    assert rev["tools"] == ["Read", "Grep", "Glob", "Bash"] and "Edit" in rev["disallowedTools"]
    assert rev["model"] == "claude-opus-5-5"
    assert rev["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "python3 GUARD --always"
    impl = agents["adw-implementer"]
    assert impl["model"] == "claude-sonnet-test" and "Edit" in impl["tools"] and "hooks" not in impl
    assert "uv run SUITES targeted" in impl["prompt"] and "{{" not in impl["prompt"]
    assert agents["adw-implementer-hard"]["prompt"] == impl["prompt"]       # @include
    assert agents["adw-implementer-hard"]["model"] == "claude-opus-5-5"
    assert agents["adw-investigator"]["model"] == "claude-haiku-5-5"
    assert sorted(orch.readonly_agents(agents)) == ["adw-investigator", "adw-reviewer"]
    json.dumps(agents)


def test_orchestrator_command_and_prompt(tmp_path):
    agents = orch.agent_definitions("S", "G")
    cmd = orch.orchestrator_command(agents, "G", str(tmp_path), None)
    # streaming input: the prompt and later messages go in on stdin
    assert cmd[1:7] == ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
    assert cmd[cmd.index("--model") + 1] == orch.ORCH_MODEL and "--replay-user-messages" in cmd
    assert "--resume" not in cmd and "--dangerously-skip-permissions" in cmd
    # no --json-schema: it makes the CLI demand a result at every turn's end, also while subagents still run
    assert "--json-schema" not in cmd and not any("StructuredOutput" in c or '"pr_opened"' in c for c in cmd)
    settings = json.loads(cmd[cmd.index("--settings") + 1])
    assert settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "G --agents adw-investigator,adw-reviewer"
    assert json.loads(cmd[cmd.index("--agents") + 1]) == agents
    assert "adw-ui-checker" in agents and "Edit" in agents["adw-ui-checker"]["disallowedTools"]
    assert orch.orchestrator_command(agents, "G", str(tmp_path), "abc")[-2:] == ["--resume", "abc"]
    prompt = orch.build_prompt({"issue_number": 5, "issue_title": "T", "issue_body": "B", "adw_id": "a", "worktree": "w",
                                "branch": "b", "issue_class": "/bug", "backend_port": 1, "frontend_port": 2,
                                "report": "REPORT", "suites": "SUITES", "adws": "ADWS", "max_review_rounds": 4,
                                "max_check_rounds": 3, "pr_body_file": "BODY", "report_file": "REPORT.md", "pr_type": "bug", "plan_file": "PLAN.md",
                                "screens_dir": "SHOTS"})
    assert "{{" not in prompt and "REPORT step review running" in prompt and "SUITES changed" in prompt
    assert "REPORT check" in prompt and "At most 3 full checks" in prompt and "Never run the full suites" in prompt
    assert "IN THE SAME MESSAGE" in prompt and "NEW `adw-reviewer`" in prompt
    assert "REPORT comment --file PLAN.md" in prompt and "adw-ui-checker" in prompt and "SHOTS" in prompt
    assert "REPORT reply <id>" in prompt and "REPORT wait" in prompt and "REPORT ask" in prompt
    assert "REPORT step screens skipped" in prompt
    assert "REPORT result pr_opened --pr-url" in prompt and "REPORT result failed" in prompt and "--force" in prompt
    assert "expected and normal" in prompt and "never\nwhile any of your subagents still runs" in prompt
    assert "JSON the output schema" not in prompt


def test_branch_name_and_classification_fallback(monkeypatch):
    assert orch.make_branch_name("/bug", "7", "20261104-abc", "Fix the Login page!!") == \
        "bug-issue-7-adw-20261104-abc-fix-the-login-page"
    assert orch.heuristic_class("Login crashes on Safari", "") == "/bug"
    assert orch.heuristic_class("Add an orders page", "") == "/feature"

    def no_claude(*a, **kw):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(orch.subprocess, "run", no_claude)
    issue = types.SimpleNamespace(title="Bump vite to 7", body="")
    log = types.SimpleNamespace(warning=lambda *a: None)
    assert orch.classify(issue, "a", log) == ("/chore", "bump-vite-to-7")


class FakeState:
    def __init__(self, **data):
        self.data = data

    def get(self, k, default=None):
        return self.data.get(k, default)


def test_finish_needs_a_passing_review(repo, monkeypatch):
    monkeypatch.setattr(orch, "open_pr_fallback", lambda *a: pytest.fail("no PR without a passing review"))
    steps.record("f1", "review", "running", label="Review", note="Round 1")
    steps.record("f1", "review", "failed", label="Review", note="Round 1: 1 blocker")
    steps.record("f1", "work", "running")                                     # left running by a dead session
    st = FakeState(adw_id="f1", issue_number="9")
    issue = types.SimpleNamespace(title="T")
    with pytest.raises(SystemExit):
        orch.finish(st, issue, {"status": "pr_opened", "pr_url": "https://github.com/o/r/pull/1", "summary": ""},
                    types.SimpleNamespace())
    assert steps.last_status("f1", "work") == "failed"
    assert steps.last_status("f1", "pr") == "skipped"
    assert "no review round passed" in COMMENTS[-1][1]


def test_finish_with_review_and_pr(repo, monkeypatch):
    steps.record("f2", "review", "done", label="Review")
    d = repo / "agents" / "f2" / "orchestrator"
    d.mkdir(parents=True)
    (d / "pr_url.txt").write_text("https://github.com/o/r/pull/8\n")
    orch.finish(FakeState(adw_id="f2", issue_number="9"), types.SimpleNamespace(title="T"),
                {"status": "pr_opened", "summary": "Done"}, None)
    assert "completed: https://github.com/o/r/pull/8" in COMMENTS[-1][1]


def test_finish_dropped_is_a_stop_not_a_failure(repo, monkeypatch):
    monkeypatch.setattr(orch, "open_pr_fallback", lambda *a: pytest.fail("nothing to open a PR for"))
    steps.record("f4", "plan", "running", label="Plan")
    orch.finish(FakeState(adw_id="f4", issue_number="9"), types.SimpleNamespace(title="T"),
                {"status": "dropped", "summary": "x", "reason": "The user dropped the item"}, None)   # no SystemExit
    assert steps.last_status("f4", "plan") == "skipped" and steps.last_status("f4", "pr") == "skipped"
    assert "⏹️ Orchestrated SDLC stopped, nothing to change: The user dropped the item" in COMMENTS[-1][1]
    assert not messages.schema_errors({"status": "dropped", "summary": "x"})


def test_finish_opens_the_pr_when_the_session_stopped_after_review(repo, monkeypatch):
    steps.record("f3", "review", "done", label="Review")
    called = []
    monkeypatch.setattr(orch, "open_pr_fallback", lambda *a: called.append(a) or "https://github.com/o/r/pull/9")
    # a session that died after the review (no structured result): status unknown, not "failed"
    orch.finish(FakeState(adw_id="f3", issue_number="9"), types.SimpleNamespace(title="T"),
                {"summary": "x"}, None)
    assert called and "pull/9" in COMMENTS[-1][1]


def test_run_session_reads_the_stream(tmp_path):
    """A fake `claude` that streams JSON lines: the session id is captured early, the result at the end."""
    fake = tmp_path / "fake_claude.py"
    fake.write_text("import json, sys, time\n"
                    "print(json.dumps({'type': 'system', 'session_id': 'sess-1'}), flush=True)\n"
                    "time.sleep(0.2)\n"
                    "sys.stdout.write(json.dumps({'type': 'result', 'session_id': 'sess-1', 'is_error': False,"
                    " 'structured_output': {'status': 'pr_opened', 'summary': 's'}}))\n")
    seen = []
    monkey_sleep = orch.time.sleep
    try:
        orch.time.sleep = lambda s: monkey_sleep(0.05)
        out = orch.run_session([sys.executable, str(fake)], str(tmp_path), dict(os.environ),
                               str(tmp_path / "o" / "raw.jsonl"), 30, seen.append)
    finally:
        orch.time.sleep = monkey_sleep
    assert seen == ["sess-1"] and not out["timed_out"]
    assert out["result"]["structured_output"]["status"] == "pr_opened"


def test_run_session_wall_clock_limit(tmp_path):
    fake = tmp_path / "slow.py"
    fake.write_text("import time\ntime.sleep(60)\n")
    t = time.time()
    out = orch.run_session([sys.executable, str(fake)], str(tmp_path), dict(os.environ),
                           str(tmp_path / "raw.jsonl"), 1, lambda s: None)
    assert out["timed_out"] and out["result"] is None and time.time() - t < 30


# ---- steps helpers ------------------------------------------------------------------

def test_close_open_fails_steps_another_process_left_running(repo):
    steps.record("c1", "plan", "done")
    steps.record("c1", "work", "running", label="Work")
    steps.record("c1", "api", "running", parent="work", label="API")
    steps.record("c1", "ui", "running", parent="work", label="UI")
    steps.record("c1", "ui", "done", parent="work", label="UI")
    steps._open.clear()                                   # as if recorded by another process
    assert steps.close_open("c1", "Session died") == 2
    out = lines("c1")[-2:]
    assert [(e["key"], e["status"], e["note"]) for e in out] == [("api", "failed", "Session died"),
                                                                  ("work", "failed", "Session died")]
    assert out[0]["label"] == "API"
    assert steps.last_status("c1", "ui", "work") == "done" and steps.last_status("c1", "nope") is None


# ---- adw_run_suites.py ----------------------------------------------------------------

def test_worker_count(monkeypatch):
    monkeypatch.delenv("ADW_ORCH_TEST_WORKERS", raising=False)
    assert suites.worker_count(cores=10, adws=1) == 10
    assert suites.worker_count(cores=10, adws=3) == 3
    assert suites.worker_count(cores=10, adws=8) == 2
    monkeypatch.setenv("ADW_ORCH_TEST_WORKERS", "4")
    assert suites.worker_count(cores=10, adws=8) == 4


def test_active_adws_and_slots_registry(repo, monkeypatch):
    """Default: running ADWs are the registry's workflow slots, full runs its full_suite slots (machine-wide)."""
    from adw_modules import resources
    monkeypatch.setenv("ADW_MAX_FULL_SUITES", "1")
    suites.register_active("a1")
    suites.register_active("a2", pid=99999999)            # dead: reclaimed, not counted
    assert suites.running_adws() == 1
    slot = suites.acquire_slot("a1", wait=0)
    assert slot and suites.acquire_slot("a2", wait=0) is None       # the only slot is taken
    assert resources.slot_usage(resources.FULL_SUITE) == (1, 1)
    suites.release_slot(slot)
    assert suites.acquire_slot("a2", wait=0)
    suites.unregister_active("a1")
    assert suites.running_adws() == 1                      # never below one
    assert not list((repo / "trees").glob("*")) if (repo / "trees").exists() else True   # no pid files


def test_active_adws_and_slots_static(repo, monkeypatch):
    monkeypatch.setenv("ADW_RESOURCES", "static")
    monkeypatch.setenv("ADW_MAX_FULL_SUITES", "1")
    suites.register_active("a1")
    suites.register_active("a2", pid=99999999)            # dead: not counted, and removed
    assert suites.running_adws() == 1
    slot = suites.acquire_slot("a1", wait=0)
    assert slot and suites.acquire_slot("a2", wait=0) is None       # the only slot is taken
    suites.release_slot(slot)
    assert suites.acquire_slot("a2", wait=0)
    suites.unregister_active("a1")
    assert suites.running_adws() == 1                      # never below one


def test_summaries_never_pass_on_no_tests():
    assert suites.pytest_summary("no tests ran in 0.01s", 5)[0] == "no tests collected"
    s, failed = suites.pytest_summary("FAILED tests/test_a.py::test_x - assert 1\n== 1 failed, 20 passed in 3s ==", 1)
    assert s == "1 failed, 20 passed" and failed == ["tests/test_a.py::test_x"]
    assert suites.vitest_summary("No test files found, exiting with code 1", 1)[0] == "no tests collected"
    assert suites.vitest_summary(" Tests  2 failed | 338 passed (340)", 1)[0] == "2 failed , 338 passed"


def test_targeted_fails_when_nothing_is_collected(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(suites, "run", lambda cmd, cwd, log, timeout: (5, "no tests ran in 0.01s"))
    assert suites.main(["--root", str(tmp_path), "targeted", "--backend", "tests/test_nothing.py"]) == 5
    assert "This is not a pass" in capsys.readouterr().out


def test_full_records_integrate_attempts(repo, monkeypatch):
    monkeypatch.setenv("ADW_ID", "s1")
    monkeypatch.setenv("ADW_MAX_FULL_SUITES", "2")
    outputs = iter([(0, ""), (1, "FAILED tests/t.py::test_a - x\n== 1 failed, 9 passed =="), (0, "")])
    monkeypatch.setattr(suites, "run", lambda cmd, cwd, log, timeout: next(outputs))
    assert suites.main(["--root", str(repo), "full", "--only", "build,backend"]) == 1
    assert suites.main(["--root", str(repo), "full", "--only", "build"]) == 0
    out = [(e["key"], e["status"]) for e in lines("s1")]
    assert out == [("integrate", "running"), ("integrate", "failed"), ("integrate", "running"), ("integrate", "done")]
    assert lines("s1")[1]["note"].startswith("Run 1: build ok; backend FAILED (1 failed, 9 passed)")
    tree, _ = ae.build_steps(ae.read_steps("s1"))
    assert len(by_key(tree)["integrate"]["attempts"]) == 2


# ---- read-only guard --------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "git diff origin/main...HEAD --stat", "git log --oneline -5 | head -3", "cat app/x.py | grep foo",
    "find . -name '*.py' | wc -l", "sed -n '1,40p' a.py", "git status --porcelain 2>/dev/null", "ls -la && pwd",
    "cd app/backend && git show HEAD:src/main.py", "rg -n organization_id src/ 2>&1 | head",
    "npx tsc --noEmit -p tsconfig.app.json"])
def test_guard_allows_read_only(cmd):
    assert guard.check(cmd) is None


@pytest.mark.parametrize("cmd", [
    "rm -rf app", "echo x > a.py", "cat a >> b", "git commit -am x", "git push origin HEAD", "git checkout main",
    "sed -i s/a/b/ f.py", "find . -delete", "find . -exec rm {} ;", "python -c 'open(\"x\",\"w\")'",
    "ls; touch x", "echo $(rm -rf /)", "git branch -D main", "npm install", ".venv/bin/pytest tests/",
    "cat a | tee b", "awk '{system(\"rm x\")}' f"])
def test_guard_blocks_writes(cmd):
    assert guard.check(cmd)


def test_guard_hook_protocol(monkeypatch, capsys):
    import io
    ev = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}, "agent_type": "adw-reviewer"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(ev)))
    assert guard.main(["--agents", "adw-reviewer,adw-investigator"]) == 2
    assert "read-only" in capsys.readouterr().err
    ev["agent_type"] = "adw-implementer"                         # other agents are not limited by the session hook
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(ev)))
    assert guard.main(["--agents", "adw-reviewer,adw-investigator"]) == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({**ev, "tool_name": "Read"})))
    assert guard.main(["--always"]) == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(ev)))
    assert guard.main(["--always"]) == 2


def test_the_state_keeps_the_ore_run_dir():
    """The trigger records its run folder in the state; without it `check` runs the full suites on every branch
    instead of once for the batch."""
    from adw_modules.data_types import ADWStateData
    from adw_modules.state import ADWState
    st = ADWState("keep1")
    st.update(ore_run_dir="/r/agents/ore/x")
    assert st.get("ore_run_dir") == "/r/agents/ore/x"
    assert ADWStateData(adw_id="keep1", ore_run_dir="/r").model_dump()["ore_run_dir"] == "/r"
