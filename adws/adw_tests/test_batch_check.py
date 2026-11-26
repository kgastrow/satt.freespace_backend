"""The full check once per batch: adw_run_suites.py changed and its failure parsing, the batch check
(adw_modules/batch_check.py) on real git branches with fake suites, `adw_report.py check`, and the Ore trigger
collecting the requests, running the check and handing out the results.

Run: uv run --with pytest --with pydantic --with python-dotenv pytest adws/adw_tests/test_batch_check.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

ADWS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ADWS))

import adw_orchestrated_sdlc_iso as orch  # noqa: E402
import adw_report  # noqa: E402
import adw_run_suites as suites  # noqa: E402
from adw_modules import batch_check, env_setup, messages, steps  # noqa: E402
from adw_triggers import trigger_ore as ae  # noqa: E402


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(steps, "steps_path", lambda adw_id: str(ae.steps_file(adw_id)))
    monkeypatch.setattr(steps, "_open", {})
    monkeypatch.setattr(orch, "MAIN_ROOT", str(tmp_path))
    monkeypatch.setattr(suites, "MAIN_ROOT", str(tmp_path))
    monkeypatch.setattr(suites, "SLOTS_DIR", str(tmp_path / "trees" / ".suite_slots"))
    monkeypatch.setattr(adw_report, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(ae, "emit", lambda msg: None)
    return tmp_path


def git(cwd, *args):
    out = subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@t", *args], cwd=cwd, capture_output=True,
                         text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def step_events(adw_id):
    return [json.loads(ln) for ln in ae.steps_file(adw_id).read_text(encoding="utf-8").splitlines()]


# ---- failures(): what each suite's output says failed ------------------------------------------

def test_failures_have_stable_keys_per_suite():
    root = "/w/tree"
    py = "FAILED tests/api/test_a.py::test_x - assert 1\nERROR tests/b.py::test_y\n== 1 failed, 1 error, 9 passed =="
    assert [i["key"] for i in suites.failures("backend", 1, py, root)] == ["backend:tests/api/test_a.py::test_x",
                                                                          "backend:tests/b.py::test_y"]
    vt = ("\x1b[31m FAIL \x1b[39m src/pages/A.test.tsx > A > shows it\n × shows it 12ms\n"
          " FAIL  src/pages/A.test.tsx > A > other\n FAIL  src/lib/b.spec.ts > b\n Tests  3 failed | 9 passed (12)")
    assert [i["key"] for i in suites.failures("frontend", 1, vt, root)] == [
        "frontend:app/frontend/src/pages/A.test.tsx", "frontend:app/frontend/src/lib/b.spec.ts"]
    assert suites.vitest_summary(vt, 1) == ("3 failed , 9 passed", ["src/lib/b.spec.ts", "src/pages/A.test.tsx"])
    tsc = ("src/pages/My.tsx(73,10): error TS2305: Module '\"./R\"' has no exported member 'R'.\n"
           "src/pages/My.tsx(80,1): error TS2305: Module '\"./R\"' has no exported member 'R'.")
    items = suites.failures("build", 2, tsc, root)
    assert len(items) == 1 and items[0]["key"].startswith("build:app/frontend/src/pages/My.tsx:TS2305:")
    lint = ("src/models/__init__.py:2:1: I001 [*] Import block is un-sorted\n"
            "tests/t.py:61:50: F811 Redefinition of unused `world`\ntests/t.py:91:5: F811 Redefinition of unused `w`\n"
            "/w/tree/app/frontend/src/x.tsx\n  12:5  error  'a' is assigned a value but never used  no-unused-vars\n"
            "  14:1  warning  Unexpected console statement  no-console\n")
    keys = {i["key"]: i for i in suites.failures("lint", 1, lint, root)}
    assert set(keys) == {"lint:app/backend/src/models/__init__.py:I001", "lint:app/backend/tests/t.py:F811",
                         "lint:app/frontend/src/x.tsx:no-unused-vars"}
    assert keys["lint:app/backend/tests/t.py:F811"]["count"] == 2
    # nothing specific: one item for the whole suite
    assert suites.failures("backend", 124, "....\nTIMED OUT after 2400s", root)[0]["key"] == "backend:*"
    assert suites.pytest_summary("....\nTIMED OUT after 2400s", 124)[0] == "timed out (2400s)"
    assert suites.failures("build", 0, "", root) == []


def test_lint_runs_ruff_and_eslint_even_when_ruff_fails(tmp_path, monkeypatch):
    seen = []

    def fake(cmd, cwd, log, timeout):
        seen.append(cmd[0])
        return (1, "src/a.py:1:1: F401 `os` imported but unused") if "ruff" in cmd[0] else (0, "")
    monkeypatch.setattr(suites, "run", fake)
    res = suites.run_suites(str(tmp_path), ["lint"], 2, None, echo=False)[0]
    assert len(seen) == 2 and not res["passed"] and res["items"][0]["key"] == "lint:app/backend/src/a.py:F401"


# ---- changed: checks on what the branch changed ------------------------------------------------

def make_app_repo(root: Path) -> Path:
    (root / "app/backend/src/billing").mkdir(parents=True)
    (root / "app/backend/tests/unit").mkdir(parents=True)
    (root / "app/frontend/src/pages").mkdir(parents=True)
    (root / "app/backend/src/billing/rates.py").write_text("RATE = 1\n")
    (root / "app/backend/src/billing/__init__.py").write_text("")
    (root / "app/backend/src/other.py").write_text("X = 1\n")
    (root / "app/backend/tests/unit/test_rates.py").write_text("from src.billing.rates import RATE\n")
    (root / "app/backend/tests/unit/test_import_from.py").write_text("from src.billing import rates\n")
    (root / "app/backend/tests/unit/test_other.py").write_text("import src.other\n")
    (root / "app/frontend/src/pages/A.tsx").write_text("export const A = 1\n")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "init")
    return root


def test_changed_runs_build_lint_and_the_tests_for_the_changed_code(tmp_path, monkeypatch, capsys):
    root = make_app_repo(tmp_path / "wt")
    (root / "app/backend/src/billing/rates.py").write_text("RATE = 2\n")            # unstaged
    (root / "app/frontend/src/pages/B.tsx").write_text("export const B = 2\n")       # untracked
    assert suites.changed_files(str(root), "main") == ["app/backend/src/billing/rates.py",
                                                       "app/frontend/src/pages/B.tsx"]
    assert suites.backend_tests_for(str(root), ["app/backend/src/billing/rates.py"]) == [
        "tests/unit/test_import_from.py", "tests/unit/test_rates.py"]
    cmds = []

    def fake(cmd, cwd, log, timeout):
        cmds.append(cmd)
        if os.path.basename(cmd[0]) == "pytest":
            return 1, "FAILED tests/unit/test_rates.py::test_rate - assert 2 == 1\n== 1 failed, 3 passed =="
        return 0, " Tests  4 passed (4)" if "vitest" in cmd else ""
    monkeypatch.setattr(suites, "run", fake)
    monkeypatch.setenv("ADW_ORCH_TEST_WORKERS", "3")
    rc = suites.main(["--root", str(root), "changed", "--base", "main", "--no-record"])
    out = capsys.readouterr().out
    assert rc == 1 and "backend: FAIL - 1 failed, 3 passed (2 test files)" in out
    assert ["npm", "run", "build:only"] in cmds
    assert any(c[0].endswith("ruff") and c[2:] == ["src/billing/rates.py"] for c in cmds)
    assert any(c[:2] == ["npx", "eslint"] and c[2:] == ["src/pages/B.tsx"] for c in cmds)
    py = next(c for c in cmds if c[0].endswith("pytest"))
    assert py[1:3] == ["tests/unit/test_import_from.py", "tests/unit/test_rates.py"] and py[-2:] == ["-n", "3"]
    vt = next(c for c in cmds if "vitest" in c)
    assert vt[:4] == ["npx", "vitest", "related", "--run"] and vt[-1] == "src/pages/B.tsx"


def test_changed_records_checks_on_integrate(repo, monkeypatch):
    root = make_app_repo(repo / "wt")
    (root / "app/backend/src/other.py").write_text("X = 2\n")
    monkeypatch.setattr(suites, "run", lambda cmd, cwd, log, timeout: (0, "== 1 passed =="))
    monkeypatch.setenv("ADW_ID", "c1")
    assert suites.main(["--root", str(root), "changed", "--base", "main"]) == 0
    ev = step_events("c1")
    assert [(e["key"], e["status"], e["label"]) for e in ev] == [("integrate", "running", "Checks"),
                                                                  ("integrate", "done", "Checks")]
    assert ev[1]["note"] == "Run 1: lint ok; backend ok (1 passed (1 test file))"


# ---- the batch check on real branches --------------------------------------------------------

def fake_suites(monkeypatch, combo=("a", "b")):
    """Suites that fail what the checked-out tree says: every line of fails/*.txt ("backend <node>",
    "frontend <file>", "build <tsc line>", "lint <ruff line>") fails, plus a backend test that fails only when the
    branches in `combo` are both merged. A rerun with node ids / files only reports those."""
    def fake(cmd, cwd, log, timeout):
        tree = Path(cwd).parent.parent
        lines = []
        for f in sorted((tree / "fails").glob("*.txt")) if (tree / "fails").is_dir() else []:
            lines += [ln.split(" ", 1) for ln in f.read_text().splitlines() if ln.strip()]
        if all((tree / "fails" / f"{c}.txt").exists() for c in combo):
            lines.append(["backend", "tests/test_combo.py::test_both"])
        by = {}
        for kind, what in lines:
            by.setdefault(kind, []).append(what)
        tool = os.path.basename(cmd[0])
        if tool == "pytest":
            asked = [a for a in cmd[1:] if a.startswith("tests/") and "::" in a]
            fails = [n for n in by.get("backend", []) if not asked or n in asked]
            out = "".join(f"FAILED {n} - boom\n" for n in fails) + f"== {len(fails)} failed, 100 passed =="
            return (1 if fails else 0), out
        if "vitest" in cmd:
            asked = [a for a in cmd if a.endswith(".tsx")]
            fails = [f for f in by.get("frontend", []) if not asked or f in asked]
            return (1 if fails else 0), "".join(f" FAIL  {f} > it\n" for f in fails) + " Tests  9 passed (9)"
        if cmd[:3] == ["npm", "run", "build:only"]:
            return (2 if by.get("build") else 0), "\n".join(by.get("build", []))
        if tool == "ruff":
            return (1 if by.get("lint") else 0), "\n".join(by.get("lint", []))
        return 0, ""
    monkeypatch.setattr(suites, "run", fake)
    monkeypatch.setattr(batch_check.Check, "deps", lambda self: "deps ok")
    monkeypatch.setattr(batch_check.Check, "types", lambda self: "types ok")


def make_batch_repo(root: Path) -> tuple[Path, dict]:
    """origin (bare) with main, a clone as the main checkout, and three workflow branches (as commits): a and b
    each break one test of their own, c conflicts with a. main itself already fails one test."""
    origin, main = root / "origin.git", root / "repo"
    git(root, "init", "-q", "--bare", "-b", "main", str(origin))
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    (main / "app/backend").mkdir(parents=True)
    (main / "app/frontend").mkdir(parents=True)
    (main / "fails").mkdir()
    (main / "fails/main.txt").write_text("backend tests/test_old.py::test_flaky\n")
    (main / "shared.py").write_text("x = 1\n")
    git(main, "add", "-A")
    git(main, "commit", "-qm", "main")
    git(main, "remote", "add", "origin", str(origin))
    git(main, "push", "-q", "origin", "main")
    shas = {}
    for name, body, shared in (("a", "backend tests/test_a.py::test_a\nfrontend src/pages/A.test.tsx\n", "x = 2\n"),
                               ("b", "backend tests/test_b.py::test_b\n", None),
                               ("c", "", "x = 3\n")):
        git(main, "checkout", "-q", "-b", f"feature-{name}", "main")
        (main / "fails" / f"{name}.txt").write_text(body)
        if shared:
            (main / "shared.py").write_text(shared)
        git(main, "add", "-A")
        git(main, "commit", "-qm", f"branch {name}")
        shas[name] = git(main, "rev-parse", "HEAD")
        git(main, "checkout", "-q", "main")
    return main, shas


def test_batch_check_attributes_each_failure(tmp_path, monkeypatch):
    main, shas = make_batch_repo(tmp_path)
    fake_suites(monkeypatch)
    d = tmp_path / "checks" / "1"
    request = {"n": 1, "run_id": "r1", "worktree": str(main / "trees" / "check-r1"),
               "branches": [{"adw_id": f"adw-{k}", "issue": str(i), "branch": f"feature-{k}", "sha": shas[k]}
                            for i, k in ((43, "c"), (41, "a"), (42, "b"))]}
    result = batch_check.Check(str(d), request, main_root=str(main)).run()
    assert not result.get("error"), result.get("error")
    assert result["merged"] == ["adw-a", "adw-b"]                         # issue order; c conflicts with a
    br = result["branches"]
    keys = lambda e, k: sorted(i["key"] for i in e[k])  # noqa: E731
    assert br["adw-a"]["status"] == "failed"
    assert keys(br["adw-a"], "yours") == ["backend:tests/test_a.py::test_a", "frontend:app/frontend/src/pages/A.test.tsx"]
    assert keys(br["adw-b"], "yours") == ["backend:tests/test_b.py::test_b"]
    for e in (br["adw-a"], br["adw-b"]):
        assert keys(e, "combined") == ["backend:tests/test_combo.py::test_both"]
        assert keys(e, "preexisting") == ["backend:tests/test_old.py::test_flaky"]
    c = br["adw-c"]
    assert c["status"] == "conflict" and c["conflict"] == {"files": ["shared.py"], "with": ["#41"]}
    report = Path(br["adw-a"]["report"]).read_text()
    assert "## Failures caused by your branch (2)" in report and "## Already failing on main (1)" in report
    assert "FAILED tests/test_a.py::test_a - boom" in report
    assert "Merge conflict" in Path(c["report"]).read_text()
    assert json.loads((d / "result.json").read_text())["branches"]["adw-b"]["status"] == "failed"
    assert json.loads((d / "status.json").read_text())["phase"] == "Done"
    # c alone, next: merges cleanly, green apart from main's own failure
    request2 = {"n": 2, "run_id": "r1", "worktree": request["worktree"],
                "branches": [{"adw_id": "adw-c", "issue": "43", "branch": "feature-c", "sha": shas["c"]}]}
    r2 = batch_check.Check(str(tmp_path / "checks" / "2"), request2, main_root=str(main)).run()
    assert r2["branches"]["adw-c"]["status"] == "green"
    assert keys(r2["branches"]["adw-c"], "preexisting") == ["backend:tests/test_old.py::test_flaky"]
    assert batch_check.remove_worktree(request["worktree"], str(main)) is None
    assert not Path(request["worktree"]).exists()


def test_batch_check_green_and_one_branch(tmp_path, monkeypatch):
    main, shas = make_batch_repo(tmp_path)
    (main / "fails/main.txt").unlink()
    git(main, "commit", "-qam", "main is green")
    git(main, "push", "-q", "origin", "main")
    fake_suites(monkeypatch)
    req = {"n": 1, "run_id": "r2", "branches": [{"adw_id": "adw-b", "issue": "42", "sha": shas["b"]}]}
    res = batch_check.Check(str(tmp_path / "chk"), req, main_root=str(main)).run()
    b = res["branches"]["adw-b"]
    assert b["status"] == "failed" and [i["key"] for i in b["yours"]] == ["backend:tests/test_b.py::test_b"]
    assert b["combined"] == [] and b["preexisting"] == []
    (main / "fails").mkdir(exist_ok=True)
    git(main, "checkout", "-q", "-b", "feature-d", "main")
    (main / "d.txt").write_text("d\n")
    git(main, "add", "-A")
    git(main, "commit", "-qm", "d")
    sha = git(main, "rev-parse", "HEAD")
    res = batch_check.Check(str(tmp_path / "chk2"), {"n": 2, "run_id": "r2", "branches": [
        {"adw_id": "adw-d", "issue": "44", "sha": sha}]}, main_root=str(main)).run()
    assert res["ok"] and res["branches"]["adw-d"]["status"] == "green"


def test_batch_check_reports_an_error_for_every_branch(tmp_path, monkeypatch):
    main, shas = make_batch_repo(tmp_path)
    fake_suites(monkeypatch)
    req = {"n": 1, "run_id": "r3", "branches": [{"adw_id": "adw-x", "issue": "9", "sha": "0" * 40}]}
    res = batch_check.Check(str(tmp_path / "chk"), req, main_root=str(main)).run()
    assert res["error"] and res["branches"]["adw-x"]["status"] == "error"


def test_frontend_env_is_copied_without_the_main_backend_urls(tmp_path):
    main, wt = tmp_path / "main", tmp_path / "wt"
    (main / "app/frontend").mkdir(parents=True)
    (wt / "app/frontend").mkdir(parents=True)
    (main / "app/frontend/.env").write_text("VITE_ORG_SLUG=onefan\nVITE_API_URL=http://localhost:8000/api/v1\n"
                                            "VITE_WS_URL=ws://localhost:8000\n")
    assert env_setup.copy_frontend_env(str(wt), str(main), "BACKEND_PORT=9100\nVITE_API_URL=http://localhost:9100/api/v1\n")
    assert (wt / "app/frontend/.env").read_text() == "VITE_ORG_SLUG=onefan\nVITE_API_URL=http://localhost:9100/api/v1\n"


# ---- adw_report.py check --------------------------------------------------------------------

def report_check(repo, monkeypatch, adw_id="w1", ore=True, **kw):
    wt = make_app_repo(repo / f"wt-{adw_id}") if not (repo / f"wt-{adw_id}").exists() else repo / f"wt-{adw_id}"
    state = repo / "agents" / adw_id / "adw_state.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"adw_id": adw_id, **({"ore_run_dir": str(repo / "agents/ore/r1")} if ore else {})}))
    monkeypatch.chdir(wt)
    return adw_report.main(["--adw-id", adw_id, "check", "--timeout-min", str(kw.get("timeout", 0.002))]), wt


def test_report_check_asks_once_per_commit_and_waits(repo, monkeypatch, capsys):
    rc, wt = report_check(repo, monkeypatch)
    out_path = repo / "agents/w1" / messages.OUTBOX
    asked = [e for e in messages.read_all(str(out_path)) if e["type"] == "check"]
    assert rc == adw_report.CHECK_WAITING and len(asked) == 1 and asked[0]["n"] == 1
    assert asked[0]["sha"] == git(wt, "rev-parse", "HEAD") and asked[0]["branch"] == "main"
    assert "Still waiting" in capsys.readouterr().out
    assert report_check(repo, monkeypatch)[0] == adw_report.CHECK_WAITING        # same commit: not asked again
    assert len([e for e in messages.read_all(str(out_path)) if e["type"] == "check"]) == 1
    assert messages.check_pending(messages.read_all(str(out_path)), [])
    inbox = str(repo / "agents/w1" / messages.INBOX)
    messages.append(inbox, {"type": "check_result", "n": 1, "status": "failed", "report": "/x/report.md",
                            "yours": [{"suite": "backend", "key": "backend:t::a", "text": "tests/t.py::a"}],
                            "preexisting": [{"suite": "lint", "key": "lint:x", "text": "x.py:1: F811"}]})
    assert report_check(repo, monkeypatch)[0] == 1
    out = capsys.readouterr().out
    assert "FULL CHECK FAILED" in out and "[yours] tests/t.py::a" in out and "already fail on origin/main" in out
    assert "/x/report.md" in out
    assert not messages.check_pending(messages.read_all(str(out_path)), messages.read_all(inbox))
    # a new commit asks again
    (wt / "fix.py").write_text("x\n")
    git(wt, "add", "-A")
    git(wt, "commit", "-qm", "fix")
    messages.append(inbox, {"type": "check_result", "n": 2, "status": "green"})
    assert report_check(repo, monkeypatch)[0] == 0
    assert "FULL CHECK GREEN" in capsys.readouterr().out
    assert [e["n"] for e in messages.read_all(str(out_path)) if e["type"] == "check"] == [1, 2]


def test_report_check_refuses_uncommitted_and_asks_again_after_a_conflict(repo, monkeypatch, capsys):
    report_check(repo, monkeypatch, "w2")
    inbox = str(repo / "agents/w2" / messages.INBOX)
    messages.append(inbox, {"type": "check_result", "n": 1, "status": "conflict",
                            "conflict": {"files": ["a.py"], "with": ["#41"]}})
    assert report_check(repo, monkeypatch, "w2")[0] == adw_report.CHECK_WAITING          # asked again: check 2
    assert "conflicts with #41" in capsys.readouterr().out
    assert report_check(repo, monkeypatch, "w2")[0] == adw_report.CHECK_WAITING          # still waiting for 2
    outbox = messages.read_all(str(repo / "agents/w2" / messages.OUTBOX))
    assert [e["n"] for e in outbox if e["type"] == "check"] == [1, 2]
    messages.append(inbox, {"type": "check_result", "n": 2, "status": "conflict", "conflict": {"files": ["a.py"]}})
    assert report_check(repo, monkeypatch, "w2")[0] == adw_report.CHECK_WAITING  # 3 asked at once
    messages.append(inbox, {"type": "check_result", "n": 3, "status": "green"})
    assert report_check(repo, monkeypatch, "w2")[0] == 0
    (repo / "wt-w2" / "dirty.txt").write_text("x")
    assert report_check(repo, monkeypatch, "w2")[0] == 2


def test_report_check_runs_the_full_suites_itself_outside_ore(repo, monkeypatch, capsys):
    calls, real = [], subprocess.run
    monkeypatch.setattr(adw_report.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or types.SimpleNamespace(
        returncode=0, stdout="ALL GREEN\n", stderr="") if cmd[0] == "uv" else real(cmd, **kw))
    rc, _ = report_check(repo, monkeypatch, "w3", ore=False)
    assert rc == 0 and calls and calls[0][3].endswith("adw_run_suites.py") and calls[0][4:6] == ["full", "--no-record"]
    assert [(e["key"], e["status"]) for e in step_events("w3")] == [("check", "running"), ("check", "done")]
    # and when the batch check couldn't run
    report_check(repo, monkeypatch, "w4")
    messages.append(str(repo / "agents/w4" / messages.INBOX), {"type": "check_result", "n": 1, "status": "error",
                                                              "error": "boom"})
    assert report_check(repo, monkeypatch, "w4")[0] == 0 and len(calls) == 2
    assert "couldn't run (boom)" in capsys.readouterr().out


# ---- the trigger: collect, run, deliver ----------------------------------------------------------

class FakeProc:
    pid = 777

    def __init__(self):
        self.code = None

    def poll(self):
        return self.code


def trigger_run(repo, groups):
    run = ae.Run(repo / "agents" / "ore" / "r1")
    run.dir.mkdir(parents=True, exist_ok=True)
    run.s = {"run_id": "r1", "dry_run": False, "groups": groups}
    return run


def group(adw_id, issue, status="running"):
    return {"title": f"G{issue}", "issue_number": str(issue), "issue_url": f"https://x/issues/{issue}",
            "adw_id": adw_id, "status": status, "workflow": "orchestrated"}


def ask_check(repo, g, n=1, sha="abc123"):
    messages.append(str(repo / "agents" / g["adw_id"] / messages.OUTBOX), {"type": "check", "n": n, "sha": sha,
                                                                         "branch": f"b-{g['adw_id']}"})
    ae.poll_outbox(types.SimpleNamespace(s={}), g)


def test_trigger_waits_for_every_workflow_then_runs_one_check(repo, monkeypatch):
    launched = []
    procs = []
    monkeypatch.setattr(ae.subprocess, "Popen", lambda cmd, **kw: launched.append(cmd) or procs.append(FakeProc())
                        or procs[-1])
    a, b, r = group("a1", 41), group("b1", 42), {**group("r1x", 50), "workflow": "router"}
    run = trigger_run(repo, [a, b, r])
    ask_check(repo, a, sha="sha-a")
    ae.full_checks(run)
    assert not launched and a["check"]["state"] == "waiting"
    assert step_events("a1")[-1]["note"] == "Waiting for #42 to finish (the full suites run once for the batch)"
    assert ae.parts(run)[0]["message"].startswith("Full check: Waiting for #42")
    ask_check(repo, b, sha="sha-b")
    ae.full_checks(run)
    assert len(launched) == 1 and launched[0][2].endswith("adw_batch_check.py")
    req = json.loads((run.dir / "checks/1/request.json").read_text())
    assert [(x["adw_id"], x["sha"], x["ask"]) for x in req["branches"]] == [("a1", "sha-a", 1), ("b1", "sha-b", 1)]
    assert req["worktree"].endswith("trees/check-r1") and run.s["check"]["groups"] == ["a1", "b1"]
    assert step_events("b1")[-1]["note"] == "Starting, together with #41"
    (run.dir / "checks/1/status.json").write_text(json.dumps({"phase": "Running the full suites", "note": "x"}))
    ae.full_checks(run)
    assert step_events("a1")[-1]["note"] == "Running the full suites: x"
    (run.dir / "checks/1/result.json").write_text(json.dumps({"ok": False, "branches": {
        "a1": {"status": "green", "preexisting": [{"key": "k", "text": "t"}], "report": "/r/a.md"},
        "b1": {"status": "failed", "yours": [{"key": "y", "text": "tests/t.py::y"}], "report": "/r/b.md"}}}))
    procs[0].code = 0
    ae.full_checks(run)
    got = {g: messages.read_all(str(repo / "agents" / g / messages.INBOX))[-1] for g in ("a1", "b1")}
    assert got["a1"]["type"] == "check_result" and got["a1"]["status"] == "green" and got["a1"]["n"] == 1
    assert got["b1"]["yours"][0]["text"] == "tests/t.py::y" and got["b1"]["report"] == "/r/b.md"
    assert (step_events("a1")[-1]["status"], step_events("a1")[-1]["note"]) == ("done", "Green (1 preexisting)")
    assert (step_events("b1")[-1]["status"], step_events("b1")[-1]["note"]) == ("failed", "Failures: 1 yours")
    assert run.s["check"] is None and run.s["checks"][0]["groups"] == ["a1", "b1"]
    # b fixes its failure and asks again: alone now (a is going to its PR), after the wait or when a finishes
    ask_check(repo, b, n=2, sha="sha-b2")
    ae.full_checks(run)
    assert len(launched) == 1                                      # a is still running (making its PR)
    a["status"] = "done"
    ae.full_checks(run)
    assert len(launched) == 2 and run.s["check"]["n"] == 2 and run.s["check"]["groups"] == ["b1"]


def test_trigger_check_after_wait_conflict_restart_and_error(repo, monkeypatch):
    procs = []
    monkeypatch.setattr(ae.subprocess, "Popen", lambda cmd, **kw: procs.append(FakeProc()) or procs[-1])
    a, b = group("a1", 41), group("b1", 42)
    run = trigger_run(repo, [a, b])
    ask_check(repo, a)
    a["check"]["since"] = time.time() - ae.CHECK_MAX_WAIT - 1           # waited long enough: run without b
    ae.full_checks(run)
    assert len(procs) == 1 and run.s["check"]["groups"] == ["a1"]
    procs[0].code = 1                                                   # died without a result: started again
    ae.full_checks(run)
    assert len(procs) == 2 and run.s["check"]["tries"] == 2
    procs[1].code = 1                                                   # and again: the workflow hears of it
    (run.dir / "checks/1/check.log").write_text("Traceback...\nOSError: disk full\n")
    ae.full_checks(run)
    res = messages.read_all(str(repo / "agents/a1" / messages.INBOX))[-1]
    assert res["status"] == "error" and "disk full" in res["error"]
    # a conflict: the next request of that workflow runs at once, on its own
    ask_check(repo, a, n=2, sha="s2")
    a["check"]["since"] = 0
    ae.full_checks(run)
    (run.dir / "checks/2/result.json").write_text(json.dumps({"branches": {"a1": {
        "status": "conflict", "conflict": {"files": ["x.py"], "with": ["#40"]}}}}))
    procs[-1].code = 0
    ae.full_checks(run)
    assert a["check"]["result"] == "conflict" and "Conflicts with #40" in step_events("a1")[-1]["note"]
    ask_check(repo, a, n=3, sha="s2")
    assert a["check"]["solo"]
    ae.full_checks(run)                                                 # b is still working, but a goes alone
    assert run.s["check"]["n"] == 3 and run.s["check"]["groups"] == ["a1"]


def test_cleanup_stops_the_check_and_removes_its_worktree(repo, monkeypatch):
    stopped, removed = [], []
    monkeypatch.setattr(ae, "_stop", lambda pid, group=False, looks_like=None: stopped.append((pid, group)))
    monkeypatch.setattr(ae.batch_check, "remove_worktree", lambda path, root: removed.append(path))
    monkeypatch.setattr(ae, "clean_group", lambda run, g, on_github: [])
    monkeypatch.setattr(ae, "result", lambda *a, **k: None)
    monkeypatch.setattr(ae, "status", lambda *a, **k: None)
    run = trigger_run(repo, [group("a1", 41)])
    run.s.update(check={"n": 1, "pid": 4321, "groups": ["a1"]}, check_worktree=str(repo / "trees/check-r1"))
    run.save()
    ae.clean(run.dir, set())
    assert (4321, True) in stopped and removed == [str(repo / "trees/check-r1")] and not run.dir.exists()


def test_the_wait_for_the_check_does_not_use_up_the_time_limit(repo):
    m = orch.Messenger("w9", "R")
    assert not m.checking()
    messages.append(m.outbox, {"type": "check", "n": 1, "sha": "s"})
    assert m.checking()
    messages.append(m.inbox, {"type": "check_result", "n": 1, "status": "green"})
    assert not m.checking() and m.poll() == []                        # a check result isn't forwarded as a message
