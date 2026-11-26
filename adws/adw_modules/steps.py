"""Structured step reporting: what a workflow is doing, for tools that draw its flow (e.g. Ore).

Each call appends one JSON line to agents/<adw_id>/steps.jsonl (the same agents/ folder ADWState uses):
    {"ts": "2026-11-04T09:04:44", "key": "test", "parent": null, "label": null, "status": "failed",
     "note": "2 tests failed: test_login"}
Statuses: running, done, failed, skipped. A step that goes running again after failed is a new attempt.
Two special records: route() (key "route", with type/complexity/workflow) and plan() (key "phases", or
"work" for the orchestrated workflow's packages; status "planned", with the list), so a reader can show the
steps still to come.

Recording never raises: a broken disk or a bad value must not break a workflow.
"""

import json
import os
from datetime import datetime

STEPS_FILENAME = "steps.jsonl"
ROUND = "round"                     # status of a follow-up round marker: the steps after it start again
PARENT_ENV = "ADW_STEP_PARENT"      # set for a child script whose steps belong under a parent (e.g. "integration")

_open: dict = {}                    # (adw_id, parent, key) -> label of steps this process left running


def steps_path(adw_id: str) -> str:
    """agents/<adw_id>/steps.jsonl in the main repo (works from inside worktrees: the scripts run from it)."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "agents", adw_id, STEPS_FILENAME)


def _write(adw_id: str, entry: dict) -> None:
    try:
        if not adw_id:
            return
        path = steps_path(adw_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        line = json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **entry}, ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001 - reporting is best effort
        pass


def record(adw_id: str, key: str, status: str, label: str = None, note: str = "", parent: str = None) -> None:
    """One step event. Keys are unique within their parent (e.g. "build" under phase "phase-1")."""
    try:
        note = " ".join(str(note or "").split())[:300]
        _write(adw_id, {"key": str(key), "parent": parent, "label": label, "status": status, "note": note})
        if status == "running":
            _open[(adw_id, parent, str(key))] = label
        else:
            _open.pop((adw_id, parent, str(key)), None)
    except Exception:  # noqa: BLE001
        pass


def route(adw_id: str, type: str, complexity: str, workflow: str) -> None:  # noqa: A002 - matches the contract
    """The router's decision; recorded as step "route" done."""
    try:
        type = (type or "").lstrip("/")
        _write(adw_id, {"key": "route", "parent": None, "label": "Route", "status": "done",
                        "note": f"{type}, {complexity}" if type else complexity,
                        "type": type, "complexity": complexity, "workflow": workflow})
        _open.pop((adw_id, None, "route"), None)
    except Exception:  # noqa: BLE001
        pass


def plan(adw_id: str, phases, key: str = "phases", label: str = None) -> None:
    """The plan, [(id, name), ...] in execution order, so the steps still to come can be shown.

    They go under step `key`: the phases of a multi-phase workflow ("phases"), or the work packages of the
    orchestrated workflow ("work"). An item may also be a dict {"id", "name", "after": [ids]} (dependencies).
    """
    try:
        items = []
        for p in phases:
            if isinstance(p, dict):
                item = {"id": str(p["id"]), "name": str(p.get("name") or p["id"])}
                if p.get("after"):
                    item["after"] = [str(a) for a in p["after"]]
            else:
                i, n = p
                item = {"id": str(i), "name": str(n or i)}
            items.append(item)
        _write(adw_id, {"key": str(key), "parent": None, "label": label or str(key).replace("_", " ").capitalize(),
                        "status": "planned", "note": "", "phases": items})
    except Exception:  # noqa: BLE001
        pass


def inherited_parent():
    """The parent step a calling orchestrator put this script under, or None."""
    return os.environ.get(PARENT_ENV) or None


def child_env(parent: str) -> dict:
    """Environment for a child script whose steps belong under `parent`."""
    env = dict(os.environ)
    env[PARENT_ENV] = parent
    return env


def fail_open(note: str = "") -> None:
    """Mark every step this process left running as failed (innermost first)."""
    for (adw_id, parent, key), label in reversed(list(_open.items())):
        record(adw_id, key, "failed", label=label, note=note, parent=parent)


def read(adw_id: str) -> list:
    """The step events recorded so far for adw_id (by any process), oldest first."""
    events = []
    try:
        with open(steps_path(adw_id), encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if isinstance(e, dict) and e.get("key") and e.get("status"):
                    events.append(e)
    except (OSError, TypeError):
        pass
    return events


def new_round(adw_id: str, n: int, note: str = "", keep=("route", "setup")) -> None:
    """A follow-up round of a finished workflow: from here its steps start again, except keep (done once)."""
    try:
        _write(adw_id, {"key": ROUND, "parent": None, "label": f"Follow-up {n}", "status": ROUND, "round": n,
                        "keep": list(keep), "note": " ".join(str(note or "").split())[:300]})
        for k in [k for k in _open if k[0] == adw_id]:
            _open.pop(k, None)
    except Exception:  # noqa: BLE001
        pass


def current(events: list) -> list:
    """The events that count now: those after the last follow-up round (and, from before it, the steps it kept),
    without the round markers."""
    last = max((i for i, e in enumerate(events) if e.get("status") == ROUND), default=None)
    if last is None:
        return events
    keep = set(events[last].get("keep") or ())
    return [e for i, e in enumerate(events) if e.get("status") != ROUND
            and (i > last or (e.get("parent") is None and e["key"] in keep) or e.get("parent") in keep)]


def rounds(events: list) -> int:
    """How many follow-up rounds the workflow has had."""
    return sum(e.get("status") == ROUND for e in events)


def last_status(adw_id: str, key: str, parent: str = None):
    """The latest status of a step, from the file (None when it never ran, or not since the last follow-up round)."""
    st = None
    for e in current(read(adw_id)):
        if e["key"] == key and e.get("parent") == parent and e["status"] != "planned":
            st = e["status"]
    return st


def close_open(adw_id: str, note: str = "", status: str = "failed") -> int:
    """Mark every step still running in the file as failed, or `status` (innermost first): for steps another
    process (e.g. an agent calling adw_report.py) left running when it died. Returns how many were closed."""
    try:
        latest: dict = {}
        for e in current(read(adw_id)):
            if e["status"] != "planned":
                latest[(e.get("parent"), e["key"])] = e
        running = [e for e in latest.values() if e["status"] == "running"]
        running.sort(key=lambda e: e.get("parent") is None)          # sub-steps before their parents
        for e in running:
            record(adw_id, e["key"], status, label=e.get("label"), note=note, parent=e.get("parent"))
        return len(running)
    except Exception:  # noqa: BLE001
        return 0


def run_main(main) -> None:
    """Run a workflow's main(); if it stops with an error, its running steps are marked failed."""
    try:
        main()
    except SystemExit as e:
        if e.code not in (0, None):
            fail_open(e.code if isinstance(e.code, str) else "")
        raise
    except BaseException as e:
        fail_open(f"{type(e).__name__}: {e}")
        raise
