"""The batch's full check: the full suites once for all the workflows of an Ore run, instead of once per workflow.

Orchestrated workflows run only checks on their changed code while they work (adw_run_suites.py changed). When one
is done (reviewed, docs written, everything committed) it asks for the full check (`adw_report.py check`), and the
Ore trigger collects these requests: once every running workflow of the run has asked (or the first has waited
ORE_CHECK_MAX_WAIT_MIN), it starts adws/adw_batch_check.py with the waiting branches. That runs Check.run():

1. A throwaway worktree, trees/check-<run_id>, detached at origin/main (reused by the run's later checks).
2. Each branch's commit merged in (issue order, --no-ff). A branch that conflicts with the ones before it is left
   out and checked on its own next (status "conflict", with the files and the branches it conflicts with).
3. Dependencies (cloned from the main checkout, then synced), the config files, and the API types generated from
   the merged backend without running it (main:app's openapi(), then openapi-typescript).
4. The full suites (adw_run_suites.run_suites) with most of the machine's cores (ADW_CHECK_WORKERS, default 3/4),
   in a machine-wide full-suite slot, timeouts x ADW_CHECK_TIMEOUT_SCALE (default 1.5).
5. When something fails, who caused it: just the failing items (test ids, test files, tsc errors and lint
   findings by file and code) are run again on origin/main ("preexisting": not the workflows' fault), then on each
   branch alone ("yours" for the branches where it fails). What fails only with the branches merged together is
   "combined" (an interaction) and goes to every merged branch. A failure that names nothing to rerun (a suite
   that timed out or crashed) is "unknown".
6. result.json: per branch its status (green, failed, conflict) and a Markdown report with the failures and their
   output (report-<adw_id>.md). The trigger hands each workflow its part (inbox "check_result").

The backend tests use an in-memory database and fake Redis (tests/conftest.py), so the check needs no Postgres
database, ports or Redis lease.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime

ADWS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_ROOT = os.path.dirname(ADWS_DIR)
if ADWS_DIR not in sys.path:
    sys.path.insert(0, ADWS_DIR)

import adw_run_suites as suites  # noqa: E402

GIT_ID = ["-c", "user.name=ADW batch check", "-c", "user.email=adw-check@localhost"]
MAX_NODE_ARGS = 200                      # more failing pytest ids than this: rerun their files instead
EXCERPT_LINES = 30


def check_workers() -> int:
    v = os.environ.get("ADW_CHECK_WORKERS", "")
    return max(1, int(v)) if v.isdigit() else max(2, (os.cpu_count() or 4) * 3 // 4)


def timeout_scale() -> float:
    try:
        return max(0.5, float(os.environ.get("ADW_CHECK_TIMEOUT_SCALE", "1.5")))
    except ValueError:
        return 1.5


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, path)


def worktree_path(run_id: str, main_root: str = MAIN_ROOT) -> str:
    return os.path.join(main_root, "trees", f"check-{run_id}")


def remove_worktree(path: str, main_root: str = MAIN_ROOT) -> str | None:
    """Remove a check worktree (git's record and the folder); an error message, or None."""
    if not os.path.exists(path):
        subprocess.run(["git", "worktree", "prune"], cwd=main_root, capture_output=True, text=True)
        return None
    proc = subprocess.run(["git", "worktree", "remove", "--force", path], cwd=main_root, capture_output=True,
                          text=True, timeout=300)
    shutil.rmtree(path, ignore_errors=True)
    subprocess.run(["git", "worktree", "prune"], cwd=main_root, capture_output=True, text=True)
    if os.path.exists(path):
        return f"couldn't remove {path}: {(proc.stderr or proc.stdout).strip()[-300:]}"
    return None


# ---- excerpts for the reports ------------------------------------------------------------

def excerpt(out: str, item: dict) -> str:
    """The part of a suite's output about one failure, for the report."""
    out = suites.ANSI.sub("", out or "")
    lines = out.splitlines()
    key, suite = item["key"], item["suite"]
    if suite == "backend" and not key.endswith(":*"):
        node = key[len("backend:"):]
        name = re.sub(r"\[.*$", "", node.rsplit("::", 1)[-1])
        header = re.compile(rf"^_{{3,}} .*\b{re.escape(name)}\b.* _{{3,}}$")
        for i, ln in enumerate(lines):
            if header.match(ln):
                block = [ln]
                for nxt in lines[i + 1:]:
                    if re.match(r"^(_{3,} .* _{3,}|={3,} )", nxt):
                        break
                    block.append(nxt)
                return "\n".join(block[:EXCERPT_LINES])
        return next((ln for ln in lines if ln.startswith(("FAILED " + node, "ERROR " + node))), item["text"])
    if suite == "frontend" and not key.endswith(":*"):
        rel = key[len("frontend:"):]
        short = rel[len("app/frontend/"):] if rel.startswith("app/frontend/") else rel
        blocks, i = [], 0
        while i < len(lines) and len(blocks) < 3:
            if re.match(rf"^\s*FAIL\s+{re.escape(short)}\b", lines[i]):
                blocks.append("\n".join(lines[i:i + 12]))
                i += 12
            else:
                i += 1
        return "\n\n".join(blocks) or item["text"]
    if suite in ("build", "lint") and not key.endswith(":*"):
        return item["text"] + (f"   ({item['count']} times)" if item.get("count", 1) > 1 else "")
    return suites.tail(out, EXCERPT_LINES)


# ---- the check ------------------------------------------------------------------------

class Check:
    """One full check of a batch of branches (see the module docstring). request: {"n", "run_id", "worktree"
    (optional), "branches": [{"adw_id", "issue", "title", "branch", "sha"}]}."""

    def __init__(self, check_dir: str, request: dict, main_root: str = MAIN_ROOT, logger: logging.Logger | None = None):
        self.dir = check_dir
        self.req = request
        self.root = main_root
        self.wt = request.get("worktree") or worktree_path(request.get("run_id") or "batch", main_root)
        self.log_dir = os.path.join(check_dir, "suites")
        self.logger = logger or logging.getLogger("batch_check")
        self.workers = check_workers()
        self.main_sha: str | None = None
        self.types_note = ""

    # -- small helpers
    def status(self, phase: str, note: str = "") -> None:
        self.logger.info(f"{phase}{': ' + note if note else ''}")
        write_json(os.path.join(self.dir, "status.json"), {"phase": phase, "note": note, "ts": now_iso(),
                                                           "pid": os.getpid()})

    def git(self, *args: str, cwd: str | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
        proc = subprocess.run(["git", *GIT_ID, *args], cwd=cwd or self.wt, capture_output=True, text=True,
                              timeout=timeout, stdin=subprocess.DEVNULL)
        if proc.returncode != 0:
            self.logger.info(f"git {' '.join(args)}: exit {proc.returncode}: {(proc.stderr or proc.stdout).strip()[-500:]}")
        return proc

    def label(self, b: dict) -> str:
        return f"#{b['issue']}" if b.get("issue") else b["adw_id"]

    # -- 1. the worktree
    def prepare(self) -> None:
        self.status("Preparing the check worktree", self.wt)
        self.git("fetch", "--quiet", "origin", "main", cwd=self.root, timeout=300)
        self.main_sha = self.git("rev-parse", "origin/main", cwd=self.root).stdout.strip() or "origin/main"
        if not os.path.isdir(os.path.join(self.wt, ".git")) and not os.path.isfile(os.path.join(self.wt, ".git")):
            os.makedirs(os.path.dirname(self.wt), exist_ok=True)
            subprocess.run(["git", "worktree", "prune"], cwd=self.root, capture_output=True, text=True)
            proc = self.git("worktree", "add", "--detach", self.wt, self.main_sha, cwd=self.root)
            if proc.returncode != 0:
                raise RuntimeError(f"couldn't create the check worktree: {proc.stderr.strip()[-300:]}")
        self.checkout(self.main_sha)

    def checkout(self, ref: str) -> None:
        merging = subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=self.wt, capture_output=True)
        if merging.returncode == 0:
            self.git("merge", "--abort")                 # a merge left half done by a killed check
        proc = self.git("checkout", "--detach", "--force", ref)
        if proc.returncode != 0:
            raise RuntimeError(f"couldn't check out {ref}: {proc.stderr.strip()[-300:]}")
        self.git("clean", "-fdq")                        # untracked files only; node_modules/.venv are ignored

    # -- 2. merges
    def merge_all(self, branches: list[dict]) -> tuple[list[dict], dict]:
        """Merge the branches in; (merged, conflicts {adw_id: {"files", "with"}})."""
        merged, conflicts = [], {}
        touched: dict[str, set] = {}
        for b in branches:
            self.status("Merging the branches", f"{self.label(b)} ({len(merged) + 1} of {len(branches)})")
            base = self.git("merge-base", self.main_sha, b["sha"]).stdout.strip() or self.main_sha
            touched[b["adw_id"]] = set(self.git("diff", "--name-only", base, b["sha"]).stdout.split())
            proc = self.git("merge", "--no-ff", "--no-edit", "-m", f"check: {self.label(b)} {b.get('branch', '')}",
                            b["sha"])
            if proc.returncode == 0:
                merged.append(b)
                continue
            files = self.git("diff", "--name-only", "--diff-filter=U").stdout.split()
            self.git("merge", "--abort")
            if not files:                                # not a conflict: an unknown commit, a git error
                raise RuntimeError(f"couldn't merge {self.label(b)} ({b['sha'][:12]}): "
                                   f"{(proc.stderr or proc.stdout).strip()[-300:]}")
            others = [self.label(m) for m in merged if touched.get(m["adw_id"], set()) & set(files)]
            conflicts[b["adw_id"]] = {"files": files, "with": others}
        return merged, conflicts

    # -- 3. dependencies, config, types
    def config_files(self) -> None:
        from adw_modules import env_setup
        for rel in (".env", os.path.join("app", "backend", ".env"), os.path.join("app", "backend", "config.json")):
            src, dst = os.path.join(self.root, rel), os.path.join(self.wt, rel)
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy(src, dst)
        env_setup.copy_frontend_env(self.wt, self.root)

    def deps(self) -> str:
        from adw_modules import env_setup
        self.status("Installing dependencies")
        self.config_files()
        return env_setup.install_dependencies(self.wt, self.logger, self.root)

    def types(self) -> str:
        """api-generated.ts for what is checked out, from the backend's own openapi() (no server needed); the main
        checkout's copy when that fails."""
        backend, frontend = os.path.join(self.wt, "app", "backend"), os.path.join(self.wt, "app", "frontend")
        target = os.path.join(frontend, "src", "types", "api-generated.ts")
        schema = os.path.join(self.dir, "openapi.json")
        py = os.path.join(backend, ".venv", "bin", "python")
        dump = ("import json, sys; sys.path.insert(0, '.'); from main import app; "
                "json.dump(app.openapi(), open(sys.argv[1], 'w'))")
        code, out = suites.run([py, "-c", dump, schema], backend, os.path.join(self.log_dir, "types.log"), 300)
        if code == 0:
            code, out = suites.run(["npx", "openapi-typescript", schema, "-o", "src/types/api-generated.ts"], frontend,
                                   os.path.join(self.log_dir, "types-ts.log"), 300)
            if code == 0:
                return "API types generated"
        main_types = os.path.join(self.root, "app", "frontend", "src", "types", "api-generated.ts")
        if os.path.exists(main_types):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy(main_types, target)
            return f"API types copied from the main checkout (couldn't generate them: {out.strip()[-160:]})"
        return f"no API types (couldn't generate them: {out.strip()[-160:]})"

    # -- 4. the full suites
    def full(self) -> list[dict]:
        self.status("Waiting for a full-suite slot")
        slot = suites.acquire_slot(f"check-{self.req.get('run_id', 'batch')}", wait=None)
        try:
            self.status("Running the full suites", f"build, backend, frontend, lint with {self.workers} workers")
            return suites.run_suites(self.wt, suites.SUITES, self.workers, self.log_dir, prefix="full-",
                                     timeout_scale=timeout_scale(), echo=False)
        finally:
            suites.release_slot(slot)

    # -- 5. who caused what
    def rerun(self, items: list[dict], prefix: str) -> set:
        """The keys of these items that fail at what is checked out now."""
        by: dict[str, list[dict]] = {}
        for it in items:
            by.setdefault(it["suite"], []).append(it)
        failing: set = set()
        for name in ("build", "lint"):
            if name in by:
                res = suites.run_suites(self.wt, [name], self.workers, self.log_dir, prefix=prefix,
                                        timeout_scale=timeout_scale(), echo=False)[0]
                keys = {it["key"] for it in res["items"]}
                if not res["passed"]:
                    keys.add(f"{name}:*")
                failing |= keys & {it["key"] for it in by[name]}
        backend = os.path.join(self.wt, "app", "backend")
        nodes = [it["key"][len("backend:"):] for it in by.get("backend", []) if not it["key"].endswith(":*")]
        if nodes:
            targets = nodes if len(nodes) <= MAX_NODE_ARGS else sorted({n.split("::")[0] for n in nodes})
            cmd = [os.path.join(backend, ".venv", "bin", "pytest"), *targets, "-q", "--tb=short", "-p", "no:cacheprovider",
                   "-n", str(max(1, min(self.workers, len(targets))))]
            code, out = suites.run(cmd, backend, os.path.join(self.log_dir, f"{prefix}backend.log"),
                                   int(2400 * timeout_scale()))
            failing |= {it["key"] for it in suites.failures("backend", code, out, self.wt)} & \
                {it["key"] for it in by["backend"]}
        files = [it["key"][len("frontend:"):] for it in by.get("frontend", []) if not it["key"].endswith(":*")]
        if files:
            frontend = os.path.join(self.wt, "app", "frontend")
            rel = [f[len("app/frontend/"):] if f.startswith("app/frontend/") else f for f in files]
            code, out = suites.run(["npx", "vitest", "run", f"--maxWorkers={self.workers}", *rel], frontend,
                                   os.path.join(self.log_dir, f"{prefix}frontend.log"), int(1800 * timeout_scale()))
            failing |= {it["key"] for it in suites.failures("frontend", code, out, self.wt)} & \
                {it["key"] for it in by["frontend"]}
        return failing

    def attribute(self, items: list[dict], merged: list[dict]) -> tuple[set, dict, set, set]:
        """(preexisting, {adw_id: keys}, combined, unknown) for the failing items of the merged run."""
        unknown = {it["key"] for it in items if it["key"].endswith(":*") and it["suite"] in ("backend", "frontend")}
        todo = [it for it in items if it["key"] not in unknown]
        if not todo:
            return set(), {b["adw_id"]: set() for b in merged}, set(), unknown
        self.status("Finding the cause", f"{len(todo)} failure{'s' if len(todo) != 1 else ''} again on main")
        self.checkout(self.main_sha)
        if any(it["suite"] == "build" for it in todo):
            self.types()
        pre = self.rerun(todo, "main-")
        left = [it for it in todo if it["key"] not in pre]
        yours: dict[str, set] = {b["adw_id"]: set() for b in merged}
        if left and len(merged) == 1:
            yours[merged[0]["adw_id"]] = {it["key"] for it in left}
            left = []
        for b in merged if left else []:
            self.status("Finding the cause", f"{len(left)} failure{'s' if len(left) != 1 else ''} on "
                                             f"{self.label(b)}'s branch alone")
            self.checkout(b["sha"])
            if any(it["suite"] == "build" for it in left):
                self.types()
            yours[b["adw_id"]] = self.rerun(left, f"{b['adw_id']}-")
        found = set().union(*yours.values()) if yours else set()
        combined = {it["key"] for it in left} - found
        return pre, yours, combined, unknown

    # -- 6. reports
    def report(self, b: dict, entry: dict, results: list[dict], merged: list[dict]) -> str:
        outs = {r["suite"]: r.get("out", "") for r in results}
        lines = [f"# Full check {self.req.get('n', '')} for {self.label(b)}: {entry['status']}", "",
                 f"origin/main {str(self.main_sha)[:12]} with "
                 + (", ".join(f"{self.label(m)} ({m['sha'][:10]})" for m in merged) or "no branch merged"), "",
                 "Suites: " + "; ".join(f"{r['suite']} {'ok' if r['passed'] else 'FAILED'}"
                                        + (f" ({r['summary']})" if r["summary"] not in ("ok", "") else "")
                                        for r in results)]
        if self.types_note:
            lines += ["", self.types_note]
        if entry.get("conflict"):
            c = entry["conflict"]
            lines += ["", "## Merge conflict", "",
                      f"Your branch conflicts with {', '.join(c['with']) or 'the branches merged before it'} in: "
                      + ", ".join(f"`{f}`" for f in c["files"]) + ". It was left out of this check and is checked "
                      "on its own next. The second of these PRs to be merged will need the conflict resolved."]
        sections = [("yours", "Failures caused by your branch",
                     "They fail on your branch alone and not on main. Fix them."),
                    ("combined", "Failures that only appear with the other branches merged",
                     "Neither main nor any branch alone fails them. Fix them if the failing code or test is in files "
                     "your branch changed; otherwise list them in the PR."),
                    ("preexisting", "Already failing on main",
                     "Not caused by this batch. Don't fix them here; list them in the PR."),
                    ("unknown", "Couldn't be attributed",
                     "The suite stopped without naming failures (a timeout or a crash). List them in the PR.")]
        for key, title, what in sections:
            its = entry.get(key) or []
            if not its:
                continue
            lines += ["", f"## {title} ({len(its)})", "", what, ""]
            for it in its:
                lines += [f"### {it['text']}", "", "```", excerpt(outs.get(it["suite"], ""), it), "```", ""]
        lines += ["", f"Logs: {self.log_dir}"]
        path = os.path.join(self.dir, f"report-{b['adw_id']}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def run(self) -> dict:
        branches = sorted(self.req.get("branches") or [],
                          key=lambda b: (int(b["issue"]) if str(b.get("issue", "")).isdigit() else 10 ** 9, b["adw_id"]))
        result = {"n": self.req.get("n"), "started": now_iso(), "worktree": self.wt, "branches": {}, "suites": []}
        try:
            self.prepare()
            result["main_sha"] = self.main_sha
            merged, conflicts = self.merge_all(branches)
            result["merged"] = [b["adw_id"] for b in merged]
            deps = self.deps()
            self.status("Generating the API types")
            self.types_note = self.types()
            result["setup"] = f"{deps}; {self.types_note}"
            results = self.full() if merged else []
            result["suites"] = [{k: r[k] for k in ("suite", "passed", "summary", "seconds")} for r in results]
            items = [it for r in results for it in r["items"]]
            pre, yours, combined, unknown = self.attribute(items, merged) if items else (set(), {}, set(), set())
            pick = lambda keys: [it for it in items if it["key"] in keys]  # noqa: E731
            for b in branches:
                c = conflicts.get(b["adw_id"])
                mine = yours.get(b["adw_id"], set())
                entry = {"issue": b.get("issue"), "sha": b["sha"],
                         "status": "conflict" if c else "failed" if (mine or combined) else "green",
                         "yours": pick(mine), "combined": pick(combined) if not c else [],
                         "preexisting": pick(pre) if not c else [], "unknown": pick(unknown) if not c else []}
                if c:
                    entry["conflict"] = c
                entry["report"] = self.report(b, entry, results, merged)
                result["branches"][b["adw_id"]] = entry
            result["ok"] = all(r["passed"] for r in results) and not conflicts
        except Exception as e:  # noqa: BLE001 - the trigger tells the workflows; they fall back to their own run
            self.logger.exception("The full check failed")
            result["error"] = f"{type(e).__name__}: {e}"
            result["ok"] = False
            for b in branches:
                result["branches"].setdefault(b["adw_id"], {"issue": b.get("issue"), "sha": b["sha"], "status": "error"})
        result["ended"] = now_iso()
        self.status("Done", "green" if result.get("ok") else (result.get("error") or "failures found"))
        write_json(os.path.join(self.dir, "result.json"), result)
        return result


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: adw_batch_check.py <check-dir with request.json>", file=sys.stderr)
        return 2
    check_dir = os.path.abspath(argv[0])
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    with open(os.path.join(check_dir, "request.json"), encoding="utf-8") as f:
        request = json.load(f)
    Check(check_dir, request).run()
    return 0
