#!/usr/bin/env python3
"""Tests for the machine-wide resource registry (adw_modules/resources.py), its use by worktree_ops /
database_ops, adw_resources.py, and the Ore trigger's slots, queueing and --simulate mode.

Run: uv run --with pytest --with pydantic --with python-dotenv pytest adws/adw_tests/test_resources.py
(conftest.py gives every test its own registry folder through ADW_SHARED_DIR.)
"""

import json
import os
import re
import shutil
import socket
import sys
import time
import types
from pathlib import Path

import pytest

ADWS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ADWS))

from adw_modules import resources  # noqa: E402

DEAD_PID = 99999999


@pytest.fixture(autouse=True)
def _no_redis_server(monkeypatch):
    """The Redis server's database count, without asking one (16, Redis' default)."""
    monkeypatch.setattr(resources, "_redis_count", [16])


@pytest.fixture
def ports(monkeypatch):
    """A small, unusual port pool, so the tests don't depend on what runs on 9100-9299 here."""
    monkeypatch.setenv("ADW_BACKEND_PORTS", "39100-39104")
    monkeypatch.setenv("ADW_FRONTEND_PORTS", "39200-39204")
    monkeypatch.setenv("ADW_REDIS_DBS", "2-6")
    monkeypatch.setattr(resources, "_redis_count", [16])


def codebases(tmp_path):
    a, b = tmp_path / "OneFan", tmp_path / "nextcase"
    for d in (a, b):
        (d / "trees").mkdir(parents=True)
    return str(a), str(b)


# ---- the registry ------------------------------------------------------------------

def test_two_codebases_share_one_pool(tmp_path, ports):
    a, b = codebases(tmp_path)
    la = resources.acquire("20261104-aaaa", root=a)
    lb = resources.acquire("20261104-bbbb", root=b)
    assert (la["backend_port"], la["frontend_port"]) == (39100, 39200)
    assert (lb["backend_port"], lb["frontend_port"]) == (39101, 39201)      # never the same pair...
    assert la["redis_db"] != lb["redis_db"]                                   # ...or Redis database
    assert la["codebase"]["name"] == "OneFan" and lb["codebase"]["name"] == "nextcase"
    assert la["host"] == socket.gethostname() and la["pid"] == os.getpid() and la["created"] and la["heartbeat"]
    assert resources.acquire("20261104-aaaa", root=a)["backend_port"] == 39100          # idempotent
    data = json.loads(Path(resources.registry_path()).read_text(encoding="utf-8"))
    assert set(data["leases"]) == {"20261104-aaaa", "20261104-bbbb"}
    assert resources.release("20261104-aaaa")["lease"]["redis_db"] == la["redis_db"]
    assert resources.acquire("20261104-cccc", root=b)["backend_port"] == 39100         # freed pair reused
    assert resources.release("nobody") == {"lease": None, "slots": []}


def test_exhausted_pools_raise(tmp_path, ports, monkeypatch):
    monkeypatch.setenv("ADW_REDIS_DBS", "2-3")
    resources.acquire("x1")
    resources.acquire("x2")
    with pytest.raises(resources.ResourcesExhausted, match="Redis"):
        resources.acquire("x3")
    monkeypatch.setenv("ADW_REDIS_DBS", "2-9")
    monkeypatch.setenv("ADW_BACKEND_PORTS", "39100-39102")
    resources.acquire("x3")
    with pytest.raises(resources.ResourcesExhausted, match="port"):
        resources.acquire("x4")
    assert issubclass(resources.ResourcesExhausted, RuntimeError)       # callers that catch RuntimeError still do


def test_ports_in_use_are_skipped(ports):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 39100))
        s.listen()
        lease = resources.acquire("busy")
    assert lease["backend_port"] == 39101


def test_redis_pool_is_clamped_to_the_server(monkeypatch):
    monkeypatch.setenv("ADW_REDIS_DBS", "2-14,30-164")
    monkeypatch.setattr(resources, "_redis_count", [165])
    assert len(resources.redis_pool()) == 13 + 135
    monkeypatch.setattr(resources, "_redis_count", [16])
    assert resources.redis_pool() == list(range(2, 15))       # a default Redis has 16 databases


def test_stale_leases_are_reclaimed(tmp_path, ports, monkeypatch):
    a, b = codebases(tmp_path)
    worktree = Path(b) / "trees" / "wt1"
    worktree.mkdir()
    resources.acquire("dead", pid=DEAD_PID, root=a)                                   # process gone
    resources.acquire("wt-kept", hold="worktree", worktree=str(worktree), pid=DEAD_PID, root=b)
    resources.acquire("wt-gone", hold="worktree", worktree=str(Path(b) / "trees" / "nope"), pid=DEAD_PID, root=b)
    resources.acquire("alive", root=a)
    assert resources.try_acquire_slot(resources.WORKFLOW, "dead", pid=DEAD_PID)
    resources.gc()                                     # (every access reclaims; gc just forces one)
    snap = resources.snapshot()
    assert {(r["what"], r["adw_id"]) for r in snap["reclaimed"]} == {("lease", "dead"), ("lease", "wt-gone"),
                                                                     ("workflow slot", "dead")}
    assert set(snap["leases"]) == {"wt-kept", "alive"}
    # a heartbeat older than the TTL is stale even when the pid looks alive (pid reuse)
    data = json.loads(Path(resources.registry_path()).read_text(encoding="utf-8"))
    data["leases"]["alive"]["heartbeat"] = time.time() - 25 * 3600
    Path(resources.registry_path()).write_text(json.dumps(data), encoding="utf-8")
    assert [r["adw_id"] for r in resources.gc()] == ["alive"]
    resources.heartbeat("wt-kept")
    assert resources.get("wt-kept")["heartbeat"] > time.time() - 5
    # another host's lease (a shared folder) isn't judged by our pids
    data = json.loads(Path(resources.registry_path()).read_text(encoding="utf-8"))
    data["leases"]["remote"] = dict(data["leases"]["wt-kept"], adw_id="remote", host="other-mac", hold="process",
                                    backend_port=39104, frontend_port=39204, redis_db=6)
    Path(resources.registry_path()).write_text(json.dumps(data), encoding="utf-8")
    assert resources.gc() == [] and "remote" in resources.snapshot()["leases"]


def test_workflow_slots_are_machine_wide(tmp_path, monkeypatch):
    monkeypatch.setenv("ADW_MAX_WORKFLOWS", "2")
    assert resources.try_acquire_slot(resources.WORKFLOW, "w1")
    assert resources.try_acquire_slot(resources.WORKFLOW, "w2", pid=DEAD_PID)
    assert resources.try_acquire_slot(resources.WORKFLOW, "w1")                        # already holds one
    assert resources.try_acquire_slot(resources.WORKFLOW, "w3")                        # w2 was dead: reclaimed
    assert not resources.try_acquire_slot(resources.WORKFLOW, "w4")
    assert resources.slot_usage(resources.WORKFLOW) == (2, 2) and resources.free_slots() == 0
    waited = []
    assert not resources.acquire_slot(resources.WORKFLOW, "w4", wait=0.2, poll=0.05,
                                      on_wait=lambda used, cap: waited.append((used, cap)))
    assert waited == [(2, 2)]
    resources.release("w1")
    assert resources.acquire_slot(resources.WORKFLOW, "w4", wait=1, poll=0.05)
    # the limit can be set machine-wide in ~/.adw/config.json; the environment wins
    monkeypatch.delenv("ADW_MAX_WORKFLOWS")
    Path(resources.shared_dir(), "config.json").write_text('{"max_workflows": 6}', encoding="utf-8")
    assert resources.limit(resources.WORKFLOW) == 6


def test_legacy_reservations_are_respected(tmp_path, ports, monkeypatch):
    """ADWs started before the registry (static reservation files) keep their ports and Redis database."""
    a, _ = codebases(tmp_path)
    folder = Path(a) / "trees" / ".port_reservations"
    folder.mkdir()
    (folder / "ports_39100_39200.reserved").write_text("20261104-0000000002\n1\n", encoding="utf-8")
    lease = resources.acquire("new", root=a)
    assert lease["backend_port"] == 39101
    assert lease["redis_db"] != resources.static_redis_db("20261104-0000000002")


def test_codebase_root_of_a_worktree(tmp_path):
    root = str(tmp_path / "OneFan")
    assert resources.codebase_root(os.path.join(root, "trees", "abc")) == root.replace("\\", "/")
    assert resources.codebase_root(root) == os.path.abspath(root)


# ---- worktree_ops / database_ops ---------------------------------------------------------

def test_worktree_ops_and_database_ops_use_the_lease(tmp_path, ports, monkeypatch):
    from adw_modules import database_ops, worktree_ops
    import logging
    monkeypatch.setattr(worktree_ops, "_get_project_root", lambda: str(tmp_path))
    b, f = worktree_ops.get_ports_for_adw("20261104-abcdef")
    lease = resources.get("20261104-abcdef")
    assert (b, f) == (lease["backend_port"], lease["frontend_port"]) and lease["hold"] == "worktree"
    assert worktree_ops.find_next_available_ports("20261104-abcdef") == (b, f)
    assert worktree_ops._reserve_ports("20261104-abcdef", b, f)
    assert worktree_ops._is_port_reserved(b, f) and not worktree_ops._is_port_reserved(39104, 39204)
    assert database_ops.get_redis_db_for_adw("20261104-abcdef") == lease["redis_db"]
    assert database_ops.get_redis_db_for_adw("20261104-other") != lease["redis_db"]      # leases one itself
    worktree_ops.release_ports("20261104-abcdef", b, f)
    assert resources.get("20261104-abcdef") is None
    ok, err = database_ops.flush_redis_db_for_adw("20261104-abcdef", logging.getLogger("t"))
    assert ok and err is None                                    # no lease: nothing to flush, no error


def test_static_mode_is_the_old_scheme(tmp_path, monkeypatch):
    from adw_modules import database_ops, worktree_ops
    monkeypatch.setenv("ADW_RESOURCES", "static")
    monkeypatch.setattr(worktree_ops, "_get_project_root", lambda: str(tmp_path))
    b, f = worktree_ops.get_ports_for_adw("20261104143052-a1b2c3d4e5f6")
    assert 9100 <= b <= 9114 and f == b + 100
    assert 2 <= database_ops.get_redis_db_for_adw("20261104143052-a1b2c3d4") <= 14
    assert database_ops.get_redis_db_for_adw("x-a1b2c3d4") == resources.static_redis_db("x-a1b2c3d4")
    assert not Path(resources.registry_path()).exists()          # the registry wasn't touched


# ---- adw_resources.py --------------------------------------------------------------------

def test_cli_status_release_gc(tmp_path, ports, capsys):
    import adw_resources
    a, b = codebases(tmp_path)
    resources.acquire("20261104-one", root=a, db_name="appdb_one")
    resources.acquire("20261104-two", root=b)
    resources.try_acquire_slot(resources.WORKFLOW, "20261104-one")
    resources.acquire("20261104-dead", pid=DEAD_PID, root=b)
    assert adw_resources.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "OneFan" in out and "nextcase" in out and "appdb_one" in out and "'workflow': 1/4" in out
    assert "20261104-dead" in out and "process 99999999 is gone" in out      # reclaimed, and said so
    assert adw_resources.main(["release", "20261104-one"]) == 0
    assert "Released 20261104-one" in capsys.readouterr().out and resources.get("20261104-one") is None
    assert adw_resources.main(["release", "20261104-one"]) == 1
    assert adw_resources.main(["gc"]) == 0
    assert adw_resources.main(["status", "--json"]) == 0
    assert set(json.loads(capsys.readouterr().out.split("\n", 2)[-1])["leases"]) == {"20261104-two"}


# ---- the Ore trigger ----------------------------------------------------------------------

@pytest.fixture
def trigger(tmp_path, monkeypatch):
    from adw_modules import steps
    from adw_triggers import trigger_ore as ae
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(steps, "steps_path", lambda adw_id: str(ae.steps_file(adw_id)))
    monkeypatch.setattr(ae, "check_claude_auth", lambda: "test")
    monkeypatch.setattr(ae, "_children", {})
    return ae


class Stop(Exception):
    pass


def one_round(ae, run, monkeypatch, sent):
    """Run the trigger's workflow loop for one round."""
    def sleep(_):
        raise Stop
    monkeypatch.setattr(ae.time, "sleep", sleep)
    monkeypatch.setattr(ae, "status", lambda *a, **kw: sent.append({"message": a[0] if a else kw["message"], **kw}))
    try:
        ae.workflows(run)
    except Stop:
        pass


def fake_launch(ae, monkeypatch, codes):
    launched = []

    class Proc:
        def __init__(self, cmd):
            self.pid, self.cmd = os.getpid(), cmd          # alive, as a running ADW is

        def poll(self):
            return codes.get(self.cmd[3])

    monkeypatch.setattr(ae.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd) or Proc(cmd))
    monkeypatch.setattr(ae.os, "getpgid", lambda pid: pid, raising=False)

    class State:
        def __init__(self, adw_id):
            self.data = {}

        def update(self, **kw):
            self.data.update(kw)

        def save(self, *_):
            pass

    monkeypatch.setattr(ae, "ADWState", State)
    return launched


def launched_pid(ae, g):
    return ae._children[g["adw_id"]].pid


def new_run(ae, tmp_path, groups):
    run = ae.Run(tmp_path / "agents" / "ore" / "r1")
    run.dir.mkdir(parents=True)
    run.s = {"run_id": "r1", "dry_run": False, "groups": groups, "phase": "workflows", "stages": {}}
    return run


def test_trigger_queues_until_a_slot_is_free(trigger, tmp_path, monkeypatch):
    ae = trigger
    monkeypatch.setenv("ADW_MAX_WORKFLOWS", "1")
    resources.try_acquire_slot(resources.WORKFLOW, "other-codebase-adw")       # alive: this process
    launched = fake_launch(ae, monkeypatch, {})
    g = {"title": "Orders", "status": "queued", "issue_number": "26", "issue_url": "https://github.com/o/r/issues/26"}
    run = new_run(ae, tmp_path, [g])
    sent = []
    one_round(ae, run, monkeypatch, sent)
    assert not launched and g["status"] == "queued"
    assert g["message"] == f"Waiting for a free slot: 1 workflow running on {ae.MACHINE}"
    assert sent[-1]["parts"][0]["status"] == "queued" and "Waiting for a free slot" in sent[-1]["parts"][0]["message"]
    resources.release("other-codebase-adw")
    one_round(ae, run, monkeypatch, sent)
    assert len(launched) == 1 and g["status"] == "running" and launched[0][2].endswith(ae.ORCHESTRATED)
    holder = resources.snapshot()["slots"]["workflow"][g["adw_id"]]
    assert holder["pid"] == launched_pid(ae, g)                    # the slot belongs to the ADW now


def test_trigger_requeues_a_launch_without_resources(trigger, tmp_path, monkeypatch):
    ae = trigger
    g = {"title": "Orders", "status": "queued", "issue_number": "26", "issue_url": "https://github.com/o/r/issues/26"}
    run = new_run(ae, tmp_path, [g])
    codes = {}
    launched = fake_launch(ae, monkeypatch, codes)
    sent = []
    one_round(ae, run, monkeypatch, sent)
    first = g["adw_id"]
    codes["26"] = ae.EXIT_NO_RESOURCES                    # the workflow found no free ports / Redis
    one_round(ae, run, monkeypatch, sent)
    assert g["status"] == "queued" and "adw_id" not in g and g["not_before"] > time.time() + 30
    assert g["message"].startswith("Waiting for free resources")
    assert resources.snapshot()["slots"].get("workflow", {}).get(first) is None       # its slot is free again
    one_round(ae, run, monkeypatch, sent)
    assert len(launched) == 1                             # not before the delay
    g["not_before"] = 0
    codes.clear()
    one_round(ae, run, monkeypatch, sent)
    assert len(launched) == 2 and g["status"] == "running" and g["adw_id"] != first


def test_trigger_waits_when_ports_are_all_leased(trigger, tmp_path, monkeypatch, ports):
    ae = trigger
    monkeypatch.setenv("ADW_BACKEND_PORTS", "39100-39100")
    resources.acquire("someone-else")
    launched = fake_launch(ae, monkeypatch, {})
    g = {"title": "Orders", "status": "queued", "issue_number": "26", "issue_url": "https://github.com/o/r/issues/26"}
    run = new_run(ae, tmp_path, [g])
    one_round(ae, run, monkeypatch, [])
    assert not launched and g["status"] == "queued" and "Waiting for free ports" in g["message"]


def test_finished_workflows_give_their_slot_and_lease_back(trigger, tmp_path, monkeypatch):
    ae = trigger
    codes = {}
    fake_launch(ae, monkeypatch, codes)
    g = {"title": "Orders", "status": "queued", "issue_number": "26", "issue_url": "https://github.com/o/r/issues/26"}
    run = new_run(ae, tmp_path, [g])
    one_round(ae, run, monkeypatch, [])
    resources.acquire(g["adw_id"], pid=os.getpid())   # what the ADW itself would lease
    codes["26"] = 0
    monkeypatch.setattr(ae, "result", lambda *a, **kw: None)
    one_round(ae, run, monkeypatch, [])
    assert g["status"] == "done"
    snap = resources.snapshot()
    assert not snap["leases"] and not snap["slots"].get("workflow")


def test_grouping_prompt_includes_the_free_slots(trigger, tmp_path, monkeypatch):
    ae = trigger
    monkeypatch.setenv("ADW_MAX_WORKFLOWS", "5")
    resources.try_acquire_slot(resources.WORKFLOW, "busy-1")
    resources.try_acquire_slot(resources.WORKFLOW, "busy-2")
    assert ae.free_workflow_slots() == 3
    rules = ae.clarify_rules(ae.free_workflow_slots())
    assert "at most 3 group(s)" in rules and f"free on {ae.MACHINE}" in rules
    assert "same pages, modules or services" in rules and "small chores and polish" in rules
    assert "large AND independent" in rules and "in parallel inside one worktree" in rules
    assert "grouping_reason" in json.dumps(ae.SCHEMA)
    seen = {}

    class P:
        returncode, stderr = 0, ""
        stdout = json.dumps({"session_id": "s1", "structured_output": {"status": "ready", "groups": []}})

    monkeypatch.setattr(ae.subprocess, "run", lambda cmd, **kw: seen.setdefault("cmd", cmd) and P())
    run = types.SimpleNamespace(s={"session_id": None, "items": []}, save=lambda: None)
    ae.claude_turn(run, "hello")
    cmd = seen["cmd"]
    assert "at most 3 group(s)" in cmd[cmd.index("--append-system-prompt") + 1]
    assert "Workflow slots free on" in cmd[2] and ": 3." in cmd[2]
    # and the user sees the number and the reason
    run = types.SimpleNamespace(s={"groups": [{}, {}, {}, {}], "grouping": {"slots_free": 3, "reason":
                                   "The export and the import are large and independent"}})
    text = ae.review_prompt(run)
    assert f"Grouped into 4 workflows (3 slots free on {ae.MACHINE})" in text
    assert "large and independent" in text and "1 will wait for a free slot" in text
    # a slot count can never be zero (the target is at least one group)
    for n in range(3, 6):
        resources.try_acquire_slot(resources.WORKFLOW, f"busy-{n}")
    assert ae.free_workflow_slots() == 1


def test_simulate_runs_the_whole_flow_with_valid_messages(tmp_path):
    """--simulate end to end, as Ore runs it: canned questions, the group review, fake issues, simulated
    orchestrated workflows that lease real resources and give them back."""
    from adw_tests import ore_harness
    repo = tmp_path / "repo"
    shutil.copytree(ADWS, repo / "adws", ignore=shutil.ignore_patterns("__pycache__", "agents", "trees"))
    env = {"ORE_SIM_SPEED": "60", "PYTHONPATH": os.environ.get("PYTHONPATH", "")}
    code, msgs, err = ore_harness.run([str(repo / "adws" / "adw_triggers" / "trigger_ore.py"), "--simulate"],
                                      env=env, change_once=True, timeout=240)
    assert code == 0, err[-2000:]
    kinds = [m["type"] for m in msgs]
    assert kinds[0] == "checkpoint" and kinds[1] == "cleanup" and kinds[-1] == "result"
    asks = [m for m in msgs if m["type"] == "input_request" and not m["id"].startswith("ask-")]
    assert [a["kind"] for a in asks] == ["questions", "groups", "groups"]       # one change round, then start
    # each simulated orchestrator asks one question after its plan (answered with the first option)
    assert [m["kind"] for m in msgs if m["type"] == "input_request" and m["id"].startswith("ask-")] == ["choice"] * 2
    assert asks[0]["id"] == "clarify-1" and len(asks[0]["questions"]) == 2
    assert "slots free on" in asks[1]["prompt"] and asks[1]["prompt"].startswith("Claude has no more questions.")
    statuses = [m for m in msgs if m["type"] == "status"]
    last = statuses[-1]
    assert [st["status"] for st in last["stages"]] == ["done"] * 4
    assert last["stages"][2]["note"].endswith("(simulated)")
    for part in last["parts"]:
        assert part["status"] == "done" and part["route"]["workflow"] == "Orchestrated SDLC"
        steps_ = {s["key"]: s for s in part["steps"]}
        assert len(steps_["integrate"]["attempts"]) == 2 and steps_["integrate"]["attempts"][0]["status"] == "failed"
        assert [a["status"] for a in steps_["review"]["attempts"]] == ["failed", "done"]
        assert len(steps_["work"]["steps"]) == 3
        assert any("/pull/" in (link[1] if isinstance(link, list) else link["url"]) for link in part["links"])
    running = [p for m in statuses for p in m.get("parts") or [] if p["status"] == "running"]
    setup_notes = [s["note"] for p in running for s in p.get("steps") or [] if s["key"] == "setup" and s["note"]]
    assert any(re.search(r"app on :91\d\d/:92\d\d", n) for n in setup_notes)     # the ports it really leased
    result = msgs[-1]
    assert result["summary"].endswith("workflows finished") and result["links"]
    snap = json.loads(Path(resources.registry_path()).read_text(encoding="utf-8"))
    assert not snap["leases"] and not snap["slots"].get("workflow")           # all given back
    try:
        from ore.protocol import check_message
    except ImportError:
        check_message = None
    for m in msgs:
        assert isinstance(m, dict) and m.get("type")
        if check_message:
            assert check_message(m) == [], m


# ---- the orchestrated workflow's setup and teardown ----------------------------------------

def test_orchestrated_setup_postpones_without_resources_and_gives_back(tmp_path, ports, monkeypatch):
    import adw_orchestrated_sdlc_iso as orch
    from adw_modules import steps
    import logging
    monkeypatch.setattr(orch, "MAIN_ROOT", str(tmp_path))
    monkeypatch.setattr(steps, "steps_path", lambda adw_id: str(tmp_path / "agents" / adw_id / "steps.jsonl"))
    monkeypatch.setattr(steps, "_open", {})
    posted = []
    monkeypatch.setattr(orch, "comment", lambda issue, text, **kw: posted.append(text))
    monkeypatch.setenv("ADW_BACKEND_PORTS", "39100-39100")
    resources.acquire("someone-else")

    class State(dict):
        def update(self, **kw):
            super().update(kw)

        def save(self, *_):
            pass

    state = State(adw_id="o-1", issue_number="5")
    with pytest.raises(SystemExit) as e:
        orch.setup(state, types.SimpleNamespace(title="t", body=""), logging.getLogger("t"))
    assert e.value.code == orch.EXIT_NO_RESOURCES == 75
    events = [json.loads(ln) for ln in (tmp_path / "agents" / "o-1" / "steps.jsonl").read_text().splitlines()]
    assert events[-1]["status"] == "failed" and events[-1]["note"].startswith("Waiting for resources")
    assert posted and "No free resources" in posted[0]
    # the workflow slot: taken at the start (idempotent with the trigger's), released at the end with the lease
    monkeypatch.setenv("ADW_BACKEND_PORTS", "39100-39104")
    orch.take_workflow_slot("o-2")
    resources.acquire("o-2")
    snap = resources.snapshot()
    assert "o-2" in snap["slots"]["workflow"] and "o-2" in snap["leases"]
    orch.give_back("o-2")
    snap = resources.snapshot()
    assert "o-2" not in snap["slots"]["workflow"] and "o-2" not in snap["leases"]
    orch.take_workflow_slot("o-3")
    resources.acquire("o-3")
    orch.give_back("o-3", keep_lease=True)                  # ADW_ORCH_KEEP_APP: the app keeps its ports
    snap = resources.snapshot()
    assert "o-3" not in snap["slots"]["workflow"] and "o-3" in snap["leases"]
