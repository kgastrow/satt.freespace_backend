#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///

"""
Test runner for agents in a worktree: checks on the changed code while a workflow works, the full suites, and
targeted tests that can't silently find nothing.

Usage (run from the worktree root; ADW_ID comes from the environment the workflow sets):
  uv run adws/adw_run_suites.py changed [--base origin/main] [--regen-types] [--no-record]
  uv run adws/adw_run_suites.py full [--only build,backend,frontend,lint] [--regen-types] [--no-record]
  uv run adws/adw_run_suites.py targeted [--backend tests/x/test_y.py[::test_z] ...] [-k EXPR]
                                         [--frontend src/a/b.test.tsx ...] [--related src/a/b.tsx ...]

changed: what an orchestrated workflow runs while it works (the full suites run once at the end, for the whole
  batch: adw_report.py check). Against the merge base with --base, committed or not:
    build     the frontend build (tsc + vite), when frontend files changed or --regen-types
    lint      ruff on the changed backend files, eslint on the changed frontend files
    backend   pytest on the changed test files and the tests that import a changed backend module
    frontend  vitest related on the changed frontend files (their own tests and the tests that import them)
  Recorded as an attempt on step "integrate" (label "Checks"), unless --no-record.
full: frontend build (tsc + vite), backend pytest, frontend vitest, lint (ruff, eslint), in that order, with a
  worker count that leaves room for the other ADWs on this machine:
      workers = max(2, cpu_count // running ADWs)      (ADW_ORCH_TEST_WORKERS overrides)
  and at most ADW_MAX_FULL_SUITES (default 2) full runs at once on this machine, across all codebases (others
  wait their turn). Both come from the machine-wide resource registry (adw_modules/resources.py): running ADWs
  are its "workflow" slots, full runs its "full_suite" slots. ADW_RESOURCES=static: pid files under trees/.
  Each run is recorded as an attempt on step "integrate" (adw_modules/steps.py), unless --no-record.
  Full logs: agents/<adw_id>/suites/<n>-<suite>.log; the failures' tails are printed.
targeted: just the given test files / names, 2 workers at most. Collecting no tests is a FAILURE (exit 5),
  never a pass: fix the path or filter.

Exit code 0 only when everything that ran passed.

The batch check (adw_modules/batch_check.py) reuses run_suites() and failures(): every failure as an item with a
stable key (a pytest node id, a vitest file, a tsc error or lint finding by file and code), so it can rerun just
those on main and on each branch.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

ADWS_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN_ROOT = os.path.dirname(ADWS_DIR)
sys.path.insert(0, ADWS_DIR)

from adw_modules import resources, steps  # noqa: E402

SLOTS_DIR = os.path.join(MAIN_ROOT, "trees", ".suite_slots")
ACTIVE_DIR = os.path.join(MAIN_ROOT, "trees", ".active_adws")
SLOT_WAIT_SECONDS = 45 * 60
TAIL_LINES = 60


# ---- machine load ----------------------------------------------------------

def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _live_entries(folder: str) -> list[str]:
    """Files in folder whose first line is a live pid; stale ones are removed."""
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for name in names:
        path = os.path.join(folder, name)
        try:
            with open(path, encoding="utf-8") as f:
                pid = int((f.readline() or "0").split()[0])
        except (OSError, ValueError, IndexError):
            continue
        if _alive(pid):
            out.append(name)
        else:
            try:
                os.remove(path)
            except OSError:
                pass
    return out


def register_active(adw_id: str, pid: int | None = None) -> str:
    """The orchestrated workflow registers itself while it runs, so suites know how many ADWs share the machine.
    Registry: a "workflow" slot (adw_orchestrated_sdlc_iso.py takes it itself; this only records the pid)."""
    if resources.enabled():
        resources.try_acquire_slot(resources.WORKFLOW, adw_id, pid=pid, max_slots=10 ** 6)
        return resources.registry_path()
    os.makedirs(ACTIVE_DIR, exist_ok=True)
    path = os.path.join(ACTIVE_DIR, f"{adw_id}.pid")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{pid or os.getpid()} {adw_id}\n")
    return path


def unregister_active(adw_id: str) -> None:
    if resources.enabled():
        resources.release_slot(resources.WORKFLOW, adw_id)
        return
    try:
        os.remove(os.path.join(ACTIVE_DIR, f"{adw_id}.pid"))
    except OSError:
        pass


def running_adws() -> int:
    if resources.enabled():
        return max(1, resources.running_workflows())
    return max(1, len(_live_entries(ACTIVE_DIR)))


def worker_count(cores: int | None = None, adws: int | None = None) -> int:
    if os.environ.get("ADW_ORCH_TEST_WORKERS", "").isdigit():
        return max(1, int(os.environ["ADW_ORCH_TEST_WORKERS"]))
    cores = cores or os.cpu_count() or 4
    adws = adws or running_adws()
    return max(2, cores // max(1, adws))


def max_full_suites() -> int:
    if resources.enabled():
        return resources.limit(resources.FULL_SUITE)
    v = os.environ.get("ADW_MAX_FULL_SUITES", "2")
    return max(1, int(v)) if v.isdigit() else 2


def acquire_slot(adw_id: str, wait: int | None = SLOT_WAIT_SECONDS, poll: float = 5.0) -> str | None:
    """A full-suite slot; waits while all are taken (wait None: as long as it takes). None when the wait ran out.
    Registry: a machine-wide "full_suite" slot; ADW_RESOURCES=static: an O_EXCL pid file in trees/.suite_slots."""
    if resources.enabled():
        holder = f"{adw_id}:{os.getpid()}"

        def told(used, cap):
            print(f"All {cap} full-suite slots on this machine are busy (other ADWs, any codebase); waiting for "
                  "one...", flush=True)
        ok = resources.acquire_slot(resources.FULL_SUITE, holder, adw_id=adw_id, wait=wait, poll=poll, on_wait=told)
        return f"registry:{holder}" if ok else None
    os.makedirs(SLOTS_DIR, exist_ok=True)
    deadline, told = (time.time() + wait if wait is not None else None), False
    while True:
        _live_entries(SLOTS_DIR)                         # clears slots of runs that died
        for i in range(max_full_suites()):
            path = os.path.join(SLOTS_DIR, f"slot-{i}.pid")
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                continue
            with os.fdopen(fd, "w") as f:
                f.write(f"{os.getpid()} {adw_id}\n")
            return path
        if deadline is not None and time.time() > deadline:
            return None
        if not told:
            print(f"All {max_full_suites()} full-suite slots are busy (other ADWs); waiting for one...", flush=True)
            told = True
        time.sleep(poll)


def release_slot(path: str | None) -> None:
    if path and path.startswith("registry:"):
        resources.release_slot(resources.FULL_SUITE, path[len("registry:"):])
        return
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


# ---- running and reading test output --------------------------------------

def run(cmd: list[str], cwd: str, log_path: str | None, timeout: int) -> tuple[int, str]:
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    env.setdefault("CI", "1")                     # vitest/npm: no watch mode, no interactive prompts
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
        code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired as e:
        code = 124
        partial = [x.decode(errors="replace") if isinstance(x, bytes) else (x or "") for x in (e.stdout, e.stderr)]
        out = f"{partial[0]}{partial[1]}\nTIMED OUT after {timeout}s"
    except FileNotFoundError as e:
        code, out = 127, str(e)
    if log_path:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"$ {' '.join(cmd)}  (in {cwd})\nexit {code}\n\n{out}")
    return code, out


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
VITEST_FAIL = re.compile(r"^\s*FAIL\s+(\S+\.(?:test|spec)\.[cm]?[jt]sx?)\b", re.M)
TSC_ERROR = re.compile(r"^(\S+?)\((\d+),(\d+)\): error (TS\d+): (.*)$", re.M)
RUFF = re.compile(r"^(\S+?\.pyi?):(\d+):(\d+): ([A-Z]+\d+) (.*)$", re.M)
ESLINT_FILE = re.compile(r"^(/\S+|[A-Za-z]:\\\S+|\S+\.[cm]?[jt]sx?)$")
ESLINT_LINE = re.compile(r"^\s+(\d+):(\d+)\s+(error|warning)\s+(.*?)\s{2,}(\S+)\s*$")


def pytest_summary(out: str, code: int) -> tuple[str, list[str]]:
    counts = dict((k, int(n)) for n, k in re.findall(r"(\d+) (passed|failed|errors?|skipped|xfailed)", out[-3000:]))
    failed = re.findall(r"^(?:FAILED|ERROR) (\S+)", out, re.M)
    if code == 5 or (not counts and "no tests ran" in out):
        return "no tests collected", failed
    if code == 124:
        return f"timed out ({out.strip().rsplit(' ', 1)[-1]})" if "TIMED OUT" in out else "timed out", failed
    parts = [f"{counts[k]} {k}" for k in ("failed", "error", "errors", "passed", "skipped") if counts.get(k)]
    return ", ".join(parts) or f"exit {code}", failed


def vitest_summary(out: str, code: int) -> tuple[str, list[str]]:
    """(summary, failing test files)."""
    out = ANSI.sub("", out)
    if re.search(r"No test files found", out):
        return "no tests collected", []
    m = re.search(r"Tests\s+(.+?)\s*\(\d+\)", out)
    failed = sorted(set(VITEST_FAIL.findall(out)))
    if code == 124:
        return "timed out", failed
    return (m.group(1).replace("|", ",").strip() if m else f"exit {code}"), failed


def tail(text: str, n: int = TAIL_LINES) -> str:
    return "\n".join(text.rstrip().splitlines()[-n:])


def _rel(path: str, root: str, sub: str) -> str:
    """A path from tool output as repo-relative (app/frontend/src/x.ts)."""
    path = path.replace("\\", "/")
    root = root.replace("\\", "/").rstrip("/") + "/"
    if path.startswith(root):
        return path[len(root):]
    return f"{sub}/{path}" if not path.startswith("app/") else path


def failures(name: str, code: int, out: str, root: str = "") -> list[dict]:
    """The failures in one suite's output, each {"suite", "key", "text"}. The key is stable across runs and
    branches (no line numbers), so the same failure can be found again elsewhere. A failed suite whose output
    names nothing specific gives one item "<suite>:*" (a crash, a timeout, a vite error)."""
    out = ANSI.sub("", out or "")
    items: dict[str, dict] = {}
    if name == "backend":
        for node in re.findall(r"^(?:FAILED|ERROR) (\S+)", out, re.M):
            items.setdefault(f"backend:{node}", {"suite": "backend", "key": f"backend:{node}", "text": node})
    elif name == "frontend":
        for path in VITEST_FAIL.findall(out):
            rel = _rel(path, root, "app/frontend")
            items.setdefault(f"frontend:{rel}", {"suite": "frontend", "key": f"frontend:{rel}", "text": rel})
    elif name == "build":
        for path, line, _col, ts, msg in TSC_ERROR.findall(out):
            rel = _rel(path, root, "app/frontend")
            items.setdefault(f"build:{rel}:{ts}:{msg[:120]}",
                             {"suite": "build", "key": f"build:{rel}:{ts}:{msg[:120]}",
                              "text": f"{rel}({line}): {ts} {msg}"})
    elif name == "lint":
        for path, line, _col, rule, msg in RUFF.findall(out):
            rel = _rel(path, root, "app/backend")
            key = f"lint:{rel}:{rule}"
            item = items.setdefault(key, {"suite": "lint", "key": key, "text": f"{rel}:{line}: {rule} {msg}"})
            item["count"] = item.get("count", 0) + 1
        current = None
        for ln in out.splitlines():
            if ESLINT_FILE.match(ln.strip()) and not ln.startswith(" "):
                current = _rel(ln.strip(), root, "app/frontend")
                continue
            m = ESLINT_LINE.match(ln)
            if current and m and m.group(3) == "error":
                key = f"lint:{current}:{m.group(5)}"
                item = items.setdefault(key, {"suite": "lint", "key": key,
                                              "text": f"{current}:{m.group(1)}: {m.group(5)} {m.group(4)}"})
                item["count"] = item.get("count", 0) + 1
    if code != 0 and not items:
        why = "timed out" if code == 124 else f"failed (exit {code})"
        last = next((ln.strip() for ln in reversed(out.strip().splitlines()) if ln.strip()), "")
        items[f"{name}:*"] = {"suite": name, "key": f"{name}:*", "text": f"{name} {why}: {last[:200]}"}
    return list(items.values())


def suite_commands(root: str, name: str, workers: int, regen_types: bool,
                   timeout_scale: float = 1.0) -> list[tuple[list[str], str, int]]:
    backend, frontend = os.path.join(root, "app", "backend"), os.path.join(root, "app", "frontend")
    venv_bin = os.path.join(backend, ".venv", "bin")
    t = lambda s: int(s * timeout_scale)  # noqa: E731
    if name == "build":
        cmds = []
        if regen_types:
            cmds.append((["npm", "run", "generate:types"], frontend, 180))
        return cmds + [(["npm", "run", "build:only"], frontend, t(900))]
    if name == "backend":
        return [([os.path.join(venv_bin, "pytest"), "tests/", "-q", "--tb=short", "-n", str(workers)], backend, t(2400))]
    if name == "frontend":
        return [(["npx", "vitest", "run", f"--maxWorkers={workers}"], frontend, t(1800))]
    if name == "lint":
        return [([os.path.join(venv_bin, "ruff"), "check", "src/", "tests/"], backend, t(300)),
                (["npm", "run", "lint"], frontend, t(600))]
    raise ValueError(name)


SUITES = ("build", "backend", "frontend", "lint")


def run_suites(root: str, only, workers: int, log_dir: str | None, prefix: str = "", regen_types: bool = False,
               stop_on_failure: bool = False, timeout_scale: float = 1.0, echo: bool = True) -> list[dict]:
    """Run the suites in order; one result per suite that ran: {"suite", "passed", "summary", "failed" (test ids or
    files), "items" (failures()), "seconds", "out" (the failing command's output, or the last one's)}.
    Logs go to <log_dir>/<prefix><suite>-<i>.log."""
    results = []
    for name in only:
        started = time.time()
        ok, summary, failed, out, code = True, "", [], "", 0
        outs = []                                   # lint: ruff and eslint both run, their outputs together
        for i, (cmd, cwd, timeout) in enumerate(suite_commands(root, name, workers, regen_types, timeout_scale)):
            log = os.path.join(log_dir, f"{prefix}{name}-{i}.log") if log_dir else None
            c, out = run(cmd, cwd, log, timeout)
            code = code or c
            if name == "backend":
                summary, failed = pytest_summary(out, c)
            elif name == "frontend":
                summary, failed = vitest_summary(out, c)
            else:
                summary = "ok" if code == 0 else ("timed out" if code == 124 else f"failed (exit {code})")
            if c != 0 or summary == "no tests collected":
                ok = False
                if name != "lint":
                    break
            outs.append(out)
        if name == "lint":
            out = "\n".join(outs)
        items = [] if ok else failures(name, code or 1, out, root)
        results.append({"suite": name, "passed": ok, "summary": summary, "failed": failed, "items": items,
                        "seconds": round(time.time() - started), "out": out})
        if echo:
            print(f"{name}: {'PASS' if ok else 'FAIL'} - {summary} ({time.time() - started:.0f}s)", flush=True)
            if not ok:
                if failed:
                    print("  failing: " + ", ".join(failed[:30]))
                print(tail(out))
        if not ok and stop_on_failure:
            break
    return results


def attempt_number(adw_id: str | None) -> int:
    if not adw_id:
        return 1
    try:
        with open(steps.steps_path(adw_id), encoding="utf-8") as f:
            return 1 + sum(1 for ln in f if '"key": "integrate"' in ln and '"status": "running"' in ln)
    except OSError:
        return 1


def note_of(n: int, results: list[dict]) -> str:
    return f"Run {n}: " + "; ".join(f"{r['suite']} {'ok' if r['passed'] else 'FAILED'}"
                                    + (f" ({r['summary']})" if r["summary"] not in ("ok", "") else "")
                                    for r in results)


def save_summary(adw_id: str | None, n: int, results: list[dict], name: str = "summary") -> None:
    if not adw_id:
        return
    path = os.path.join(MAIN_ROOT, "agents", adw_id, "suites", f"{n}-{name}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([{k: v for k, v in r.items() if k != "out"} for r in results], f, indent=1)


def cmd_full(args) -> int:
    root, adw_id = os.path.abspath(args.root), os.environ.get("ADW_ID") or args.adw_id
    only = [s.strip() for s in (args.only or ",".join(SUITES)).split(",") if s.strip()]
    bad = [s for s in only if s not in SUITES]
    if bad:
        print(f"unknown suite(s): {', '.join(bad)} (choose from {', '.join(SUITES)})", file=sys.stderr)
        return 2
    record = adw_id and not args.no_record
    n = attempt_number(adw_id)
    slot = acquire_slot(adw_id or "manual")
    if not slot:
        print("No full-suite slot became free in time; try again later.", file=sys.stderr)
        return 3
    try:
        workers = worker_count()
        if record:
            steps.record(adw_id, "integrate", "running", label="Integrate",
                         note=f"Run {n}: {', '.join(only)} ({workers} workers)")
        print(f"Full suites, run {n}: {', '.join(only)} with {workers} workers "
              f"({os.cpu_count()} cores, {running_adws()} ADW(s) running)", flush=True)
        log_dir = os.path.join(MAIN_ROOT, "agents", adw_id, "suites") if adw_id else None
        results = run_suites(root, only, workers, log_dir, prefix=f"{n}-", regen_types=args.regen_types,
                             stop_on_failure=args.stop_on_failure)
        ok_all = all(r["passed"] for r in results)
        if record:
            steps.record(adw_id, "integrate", "done" if ok_all else "failed", label="Integrate",
                         note=note_of(n, results))
        save_summary(adw_id, n, results)
        print("ALL GREEN" if ok_all else "NOT GREEN: fix the failures above, then run the full suites again.")
        return 0 if ok_all else 1
    finally:
        release_slot(slot)


# ---- changed: checks on what this branch changed ------------------------------------

def _git_lines(root: str, *args: str) -> list[str]:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()] if proc.returncode == 0 else []


def changed_files(root: str, base: str = "origin/main") -> list[str]:
    """Repo-relative paths changed against the merge base with base: committed, staged, unstaged and untracked
    (deleted files included; callers check what still exists)."""
    merge_base = (_git_lines(root, "merge-base", base, "HEAD") or [base])[0]
    files = set(_git_lines(root, "diff", "--name-only", merge_base))
    files |= set(_git_lines(root, "ls-files", "--others", "--exclude-standard"))
    return sorted(files)


def backend_tests_for(root: str, files: list[str]) -> list[str]:
    """Backend test files (relative to app/backend) for the changed backend files: changed test files, and the
    tests that import a changed module (src/a/b.py: "src.a.b", or "from src.a import b")."""
    backend = os.path.join(root, "app", "backend")
    tests, modules = set(), []
    for f in files:
        if not f.startswith("app/backend/") or not f.endswith(".py"):
            continue
        rel = f[len("app/backend/"):]
        if rel.startswith("tests/") and os.path.basename(rel).startswith("test_"):
            if os.path.exists(os.path.join(backend, rel)):
                tests.add(rel)
        elif rel.startswith("src/"):
            dotted = rel[:-3].replace("/", ".")
            if dotted.endswith(".__init__"):
                dotted = dotted[:-len(".__init__")]
            parent, _, leaf = dotted.rpartition(".")
            modules.append(re.compile(rf"\b{re.escape(dotted)}\b|from\s+{re.escape(parent)}\s+import\s+[^\n]*\b{re.escape(leaf)}\b"))
    if modules:
        for dirpath, dirnames, names in os.walk(os.path.join(backend, "tests")):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".venv", "node_modules")]
            for name in names:
                if not (name.startswith("test_") and name.endswith(".py")):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        text = fh.read()
                except OSError:
                    continue
                if any(m.search(text) for m in modules):
                    tests.add(os.path.relpath(path, backend).replace(os.sep, "/"))
    return sorted(tests)


FRONTEND_CODE = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs")


def cmd_changed(args) -> int:
    root, adw_id = os.path.abspath(args.root), os.environ.get("ADW_ID") or args.adw_id
    record = adw_id and not args.no_record
    files = changed_files(root, args.base)
    exists = lambda f: os.path.exists(os.path.join(root, f))  # noqa: E731
    fe = [f for f in files if f.startswith("app/frontend/") and f.endswith(FRONTEND_CODE) and exists(f)
          and "/node_modules/" not in f]
    fe_src = [f for f in fe if f.startswith("app/frontend/src/")]
    py = [f for f in files if f.startswith("app/backend/") and f.endswith(".py") and exists(f)]
    be_tests = backend_tests_for(root, files)
    n = attempt_number(adw_id)
    workers = worker_count()
    print(f"Checks on the changed code, run {n}: {len(files)} changed file(s), {workers} workers", flush=True)
    if record:
        steps.record(adw_id, "integrate", "running", label="Checks", note=f"Run {n}: checks on the changed code")
    backend, frontend = os.path.join(root, "app", "backend"), os.path.join(root, "app", "frontend")
    log_dir = os.path.join(MAIN_ROOT, "agents", adw_id, "suites") if adw_id else None
    log = lambda name: os.path.join(log_dir, f"{n}-changed-{name}.log") if log_dir else None  # noqa: E731
    results = []

    def add(name, code, out, summary, failed=()):
        ok = code == 0
        results.append({"suite": name, "passed": ok, "summary": summary, "failed": list(failed),
                        "items": [] if ok else failures(name, code, out, root), "out": out})
        print(f"{name}: {'PASS' if ok else 'FAIL'} - {summary}", flush=True)
        if not ok:
            if failed:
                print("  failing: " + ", ".join(list(failed)[:30]))
            print(tail(out))

    if fe or args.regen_types:
        out_all, code = "", 0
        for i, (cmd, cwd, timeout) in enumerate(suite_commands(root, "build", workers, args.regen_types)):
            code, out = run(cmd, cwd, log(f"build-{i}"), timeout)
            out_all = out
            if code:
                break
        add("build", code, out_all, "ok" if code == 0 else f"failed (exit {code})")
    else:
        print("build: skipped - no frontend changes")
    lint_out, lint_code = [], 0
    if py:
        code, out = run([os.path.join(backend, ".venv", "bin", "ruff"), "check",
                         *[f[len("app/backend/"):] for f in py]], backend, log("ruff"), 300)
        lint_code, lint_out = lint_code or code, lint_out + [out]
    if fe:
        code, out = run(["npx", "eslint", *[f[len("app/frontend/"):] for f in fe]], frontend, log("eslint"), 600)
        lint_code, lint_out = lint_code or code, lint_out + [out]
    if py or fe:
        add("lint", lint_code, "\n".join(lint_out), "ok" if lint_code == 0 else f"failed (exit {lint_code})")
    if be_tests:
        cmd = [os.path.join(backend, ".venv", "bin", "pytest"), *be_tests, "-q", "--tb=short", "-n", str(workers)]
        code, out = run(cmd, backend, log("backend"), 2400)
        summary, failed = pytest_summary(out, code)
        add("backend", code if summary != "no tests collected" else 5, out,
            f"{summary} ({len(be_tests)} test file{'s' if len(be_tests) != 1 else ''})", failed)
    elif py:
        print("backend: no tests import the changed backend files: add tests, or run them with `targeted`")
    if fe_src:
        cmd = ["npx", "vitest", "related", "--run", "--passWithNoTests", f"--maxWorkers={workers}",
               *[f[len("app/frontend/"):] for f in fe_src]]
        code, out = run(cmd, frontend, log("frontend"), 1800)
        summary, failed = vitest_summary(out, code)
        add("frontend", code, out, summary, failed)
    ok_all = all(r["passed"] for r in results)
    note = note_of(n, results) if results else f"Run {n}: nothing to check"
    if record:
        steps.record(adw_id, "integrate", "done" if ok_all else "failed", label="Checks", note=note)
    save_summary(adw_id, n, results, "changed")
    if not results:
        print("Nothing to check: no app files changed.")
    print("CHANGED CODE GREEN (the full suites run once at the end: adw_report.py check)" if ok_all else
          "NOT GREEN: fix the failures above, then run the checks again.")
    return 0 if ok_all else 1


def cmd_targeted(args) -> int:
    root = os.path.abspath(args.root)
    if not (args.backend or args.frontend or args.related):
        print("give --backend, --frontend or --related paths", file=sys.stderr)
        return 2
    workers = min(2, worker_count())
    rc = 0
    if args.backend:
        backend = os.path.join(root, "app", "backend")
        paths = [p[len("app/backend/"):] if p.startswith("app/backend/") else p for p in args.backend]
        cmd = [os.path.join(backend, ".venv", "bin", "pytest"), *paths, "-q", "--tb=short"]
        if args.k:
            cmd += ["-k", args.k]
        if len(paths) > 1 or not args.k:
            cmd += ["-n", str(workers)]
        code, out = run(cmd, backend, None, 1200)
        summary, failed = pytest_summary(out, code)
        print(f"backend: {summary}")
        if summary == "no tests collected":
            print("No tests were collected: the path or -k filter is wrong. This is not a pass.")
            rc = rc or 5
        elif code != 0:
            print(tail(out, 120))
            rc = rc or 1
    if args.frontend or args.related:
        frontend = os.path.join(root, "app", "frontend")
        strip = (lambda p: p[len("app/frontend/"):] if p.startswith("app/frontend/") else p)
        if args.related:
            cmd = ["npx", "vitest", "related", "--run", *map(strip, args.related)]
        else:
            cmd = ["npx", "vitest", "run", *map(strip, args.frontend)]
        code, out = run(cmd + [f"--maxWorkers={workers}"], frontend, None, 1200)
        summary, failed = vitest_summary(out, code)
        print(f"frontend: {summary}")
        if summary == "no tests collected":
            print("No test files were found: the paths are wrong. This is not a pass.")
            rc = rc or 5
        elif code != 0:
            print(tail(out, 120))
            rc = rc or 1
    return rc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="adw_run_suites.py")
    p.add_argument("--root", default=os.getcwd(), help="worktree root (default: the current directory)")
    p.add_argument("--adw-id", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("changed", help="build, lint and the tests for what this branch changed")
    c.add_argument("--base", default="origin/main")
    c.add_argument("--regen-types", action="store_true", help="npm run generate:types before the build (API changed)")
    c.add_argument("--no-record", action="store_true")
    c.set_defaults(func=cmd_changed)
    f = sub.add_parser("full")
    f.add_argument("--only", help="comma-separated: " + ",".join(SUITES))
    f.add_argument("--regen-types", action="store_true", help="npm run generate:types before the build (API changed)")
    f.add_argument("--no-record", action="store_true")
    f.add_argument("--stop-on-failure", action="store_true")
    f.set_defaults(func=cmd_full)
    t = sub.add_parser("targeted")
    t.add_argument("--backend", nargs="+", default=[])
    t.add_argument("-k", default=None)
    t.add_argument("--frontend", nargs="+", default=[])
    t.add_argument("--related", nargs="+", default=[])
    t.set_defaults(func=cmd_targeted)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
