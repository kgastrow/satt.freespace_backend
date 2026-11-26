"""Machine-wide resource registry, shared by every codebase (and every Ore run) on this machine.

All ADW codebases on one machine share its ports, its Redis server and its CPU. Instead of each codebase owning
a fixed slice (the old ADW_CODEBASE_INDEX / ADW_MAX_CODEBASES split), they all lease from one registry file:

    ~/.adw/resources.json            (directory: ADW_SHARED_DIR; guarded by ~/.adw/resources.lock, fcntl)

Leases, keyed by adw_id: what one workflow holds.
    {"adw_id", "codebase": {"root", "name"}, "pid", "pgid", "host", "hold", "worktree",
     "created", "heartbeat", "backend_port", "frontend_port", "redis_db", "db_name"}
    - ports: a backend+frontend pair from a global pool (ADW_BACKEND_PORTS 9100-9199, ADW_FRONTEND_PORTS
      9200-9299, paired by offset), skipping ports any process is listening on;
    - redis_db: a Redis database index from ADW_REDIS_DBS (default 2-14,30-164, clamped to the server's
      `databases` setting; 0-1 are the main app's, 15-29 the Playwright e2e runs' (15 + ADW_CODEBASE_INDEX));
    - db_name: the isolated PostgreSQL database (already unique per adw_id), recorded for `status`.
    hold = "process": the lease lives while pid runs (the orchestrated workflow);
    hold = "worktree": it lives while the worktree exists (the classic workflows, whose phases are separate
    processes), until the worktree is removed.

Slots: machine-wide semaphores, {kind: {holder: {"adw_id", "pid", "host", "codebase", "created", "heartbeat"}}}
    "workflow"    ADW_MAX_WORKFLOWS (4): workflows running at once, across codebases and Ore runs;
    "full_suite"  ADW_MAX_FULL_SUITES (2): full test-suite runs at once (adw_run_suites.py full).

Waiting: {holder: {"adw_id", "label", "issue", "pid", "host", "codebase", "created", "heartbeat"}}
    workflows an Ore trigger has queued for a workflow slot (note_waiting); gone when the slot is taken, on
    release(), when the trigger's pid is dead, or after WAIT_TTL without a refresh. Only for display (Ore's
    machine view); nothing depends on it.

Stale entries are reclaimed automatically on every access: a lease or slot whose pid is dead on this host
(for hold=worktree: and whose worktree is gone), or whose heartbeat is older than ADW_LEASE_TTL_HOURS (24).
release(adw_id) frees a workflow's lease and slots (on success, failure, SIGTERM, the trigger's --cleanup).

Claude usage: ~/.adw/usage.json (guarded by ~/.adw/usage.lock) keeps the latest rate-limit windows any claude
process on this machine reported (rate_limit_event in stream-json; record_rate_limit), per window kind
("five_hour", "seven_day", ...): {"as_of", "windows": {kind: {"used_percent", "resets_at", "status", "seen"}}}.
machine_view() puts it all together for Ore's `machine` query (adw_triggers/trigger_ore.py --ore-query machine).

Limits and pools can also be set machine-wide in ~/.adw/config.json ({"max_workflows": 5, "max_full_suites": 2,
"backend_ports": "9100-9199", "frontend_ports": "9200-9299", "redis_dbs": "2-14,30-164", "lease_ttl_hours": 24});
the environment wins over the file. ADW_RESOURCES=static switches all of this off and brings back the static
per-codebase slices (ADW_CODEBASE_INDEX / ADW_MAX_CODEBASES).

Inspect it with `uv run adws/adw_resources.py status|release <adw_id>|gc`.
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime
from typing import Iterable, Optional

try:
    import fcntl  # POSIX
except ImportError:  # Windows: no cross-process lock (tests only; ADWs run on macOS / Linux)
    fcntl = None

WORKFLOW = "workflow"
FULL_SUITE = "full_suite"
_DEFAULTS = {"max_workflows": 4, "max_full_suites": 2, "backend_ports": "9100-9199",
             "frontend_ports": "9200-9299", "redis_dbs": "2-14,30-164", "lease_ttl_hours": 24}
_ENV = {"max_workflows": "ADW_MAX_WORKFLOWS", "max_full_suites": "ADW_MAX_FULL_SUITES",
        "backend_ports": "ADW_BACKEND_PORTS", "frontend_ports": "ADW_FRONTEND_PORTS",
        "redis_dbs": "ADW_REDIS_DBS", "lease_ttl_hours": "ADW_LEASE_TTL_HOURS"}
_LIMITS = {WORKFLOW: "max_workflows", FULL_SUITE: "max_full_suites"}


class ResourcesExhausted(RuntimeError):
    """No free port pair or Redis database right now. Temporary: try again when a workflow finishes."""


# ---- configuration -----------------------------------------------------------

def enabled() -> bool:
    """The registry is the default; ADW_RESOURCES=static brings back the per-codebase static slices."""
    return os.getenv("ADW_RESOURCES", "registry").strip().lower() != "static"


def shared_dir() -> str:
    return os.path.expanduser(os.getenv("ADW_SHARED_DIR") or os.path.join("~", ".adw"))


def registry_path() -> str:
    return os.path.join(shared_dir(), "resources.json")


def _file_config() -> dict:
    try:
        with open(os.path.join(shared_dir(), "config.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def setting(key: str):
    raw = os.getenv(_ENV[key], "").strip() or _file_config().get(key)
    default = _DEFAULTS[key]
    if raw in (None, ""):
        return default
    if isinstance(default, int):
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return default
    return str(raw)


def limit(kind: str) -> int:
    return setting(_LIMITS[kind]) if kind in _LIMITS else 1


def parse_ranges(spec: str) -> list[int]:
    """"9100-9199" or "2-14,30-164" -> the numbers, in order, without duplicates."""
    out: list[int] = []
    for part in str(spec).replace(" ", "").split(","):
        if not part:
            continue
        lo, _, hi = part.partition("-")
        try:
            a, b = int(lo), int(hi or lo)
        except ValueError:
            continue
        out += [n for n in range(a, b + 1) if n not in out]
    return out


def port_pairs() -> list[tuple[int, int]]:
    backend, frontend = parse_ranges(setting("backend_ports")), parse_ranges(setting("frontend_ports"))
    return list(zip(backend, frontend))


_redis_count: list = []


def redis_server_databases() -> Optional[int]:
    """The Redis server's `databases` setting (cached), or None when it can't be read."""
    if _redis_count:
        return _redis_count[0]
    count = None
    try:
        import redis  # noqa: PLC0415 - optional
        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1, socket_timeout=1)
        count = int(r.config_get("databases").get("databases"))
    except Exception:  # noqa: BLE001
        try:
            out = subprocess.run(["redis-cli", "config", "get", "databases"], capture_output=True, text=True,
                                 timeout=3).stdout.split()
            count = int(out[-1]) if len(out) >= 2 else None
        except Exception:  # noqa: BLE001
            count = None
    _redis_count.append(count)
    return count


def redis_pool() -> list[int]:
    """The Redis databases ADW worktrees may use: ADW_REDIS_DBS, minus what the server doesn't have
    (16, Redis' default, when the server can't be asked)."""
    count = redis_server_databases() or 16
    return [n for n in parse_ranges(setting("redis_dbs")) if 0 <= n < count]


# ---- identity, liveness -------------------------------------------------------

def host() -> str:
    return socket.gethostname()


def codebase_root(path: Optional[str] = None) -> str:
    """The main checkout this code belongs to (a worktree under trees/<id>/ maps to its main checkout)."""
    root = os.path.abspath(path or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    parts = root.replace("\\", "/").split("/")
    if "trees" in parts:
        i = len(parts) - 1 - parts[::-1].index("trees")
        if i + 1 < len(parts):
            root = "/".join(parts[:i]) or root
    return root


def codebase(path: Optional[str] = None) -> dict:
    root = codebase_root(path)
    return {"root": root, "name": os.path.basename(root.rstrip("/\\")) or root}


def pid_alive(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform == "win32":                 # os.kill(pid, 0) would terminate the process on Windows
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        code = ctypes.c_ulong()
        ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return code.value == 259                # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                             # someone else's process: alive
    except OSError:
        return False
    try:                                        # Linux: a zombie (exited, not reaped) is dead
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split()[2] != "Z"
    except (OSError, IndexError):
        return True


def port_free(port: int) -> bool:
    """Nothing listens on the port (on localhost or any interface)."""
    for addr in ("127.0.0.1", "0.0.0.0"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                if sys.platform != "win32":
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((addr, port))
            except OSError:
                return False
    return True


def now() -> float:
    return time.time()


def _iso(t) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)) if t else ""


# ---- the locked file ----------------------------------------------------------

def _empty() -> dict:
    return {"version": 1, "leases": {}, "slots": {}}


@contextlib.contextmanager
def _locked():
    """The registry, read under an exclusive lock and written back (atomically) when the block ends."""
    d = shared_dir()
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "resources.lock"), "a+") as lock:
        if fcntl is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            try:
                with open(registry_path(), encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    data = _empty()
            except (OSError, ValueError):
                data = _empty()
            data.setdefault("leases", {})
            data.setdefault("slots", {})
            data.setdefault("waiting", {})
            before = json.dumps(data, sort_keys=True)
            reclaimed = _reclaim(data)
            data["_reclaimed_now"] = reclaimed
            yield data
            data.pop("_reclaimed_now", None)
            if reclaimed:
                data["reclaimed"] = ((data.get("reclaimed") or []) + reclaimed)[-20:]
            if json.dumps(data, sort_keys=True) != before:
                tmp = registry_path() + f".{os.getpid()}.tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=1, sort_keys=True)
                os.replace(tmp, registry_path())
        finally:
            if fcntl is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def stale_reason(entry: dict, t: Optional[float] = None) -> Optional[str]:
    """Why a lease or slot holder no longer counts, or None while it does."""
    t = t or now()
    ttl = float(setting("lease_ttl_hours")) * 3600
    beat = entry.get("heartbeat") or entry.get("created") or 0
    if t - beat > ttl:
        return f"no heartbeat for {(t - beat) / 3600:.0f}h"
    if entry.get("host") and entry["host"] != host():
        return None                                  # another machine's (shared dir): can't check its pid
    alive = pid_alive(entry.get("pid"))
    if entry.get("hold") == "worktree":
        wt = entry.get("worktree")
        if not alive and (not wt or not os.path.isdir(wt)):
            return "process gone and worktree removed"
        return None
    if not alive:
        return f"process {entry.get('pid')} is gone"
    return None


def _reclaim(data: dict) -> list[dict]:
    out, t = [], now()
    for adw_id, lease in list(data["leases"].items()):
        why = stale_reason(lease, t)
        if why:
            del data["leases"][adw_id]
            out.append({"at": _iso(t), "what": "lease", "adw_id": adw_id, "why": why,
                        "codebase": (lease.get("codebase") or {}).get("name")})
    for kind, holders in data["slots"].items():
        for holder, entry in list(holders.items()):
            why = stale_reason(entry, t)
            if why:
                del holders[holder]
                out.append({"at": _iso(t), "what": f"{kind} slot", "adw_id": entry.get("adw_id") or holder,
                            "why": why, "codebase": (entry.get("codebase") or {}).get("name")})
    for holder, entry in list(data.get("waiting", {}).items()):      # display only: dropped quietly
        if t - (entry.get("heartbeat") or 0) > WAIT_TTL or stale_reason(entry, t):
            del data["waiting"][holder]
    return out


# ---- leases ---------------------------------------------------------------------

def _pick_ports(data: dict, prefer, exclude: set) -> Optional[tuple[int, int]]:
    taken = set()
    for lease in data["leases"].values():
        taken |= {lease.get("backend_port"), lease.get("frontend_port")}
    pairs = port_pairs()
    if prefer and tuple(prefer) in pairs:
        pairs = [tuple(prefer)] + [p for p in pairs if p != tuple(prefer)]
    for b, f in pairs:
        if b in taken or f in taken or (b, f) in exclude or b in exclude or f in exclude:
            continue
        if port_free(b) and port_free(f):
            return b, f
    return None


def _pick_redis(data: dict, prefer, exclude: set) -> Optional[int]:
    taken = {lease.get("redis_db") for lease in data["leases"].values()}
    pool = redis_pool()
    if prefer in pool:
        pool = [prefer] + [n for n in pool if n != prefer]
    return next((n for n in pool if n not in taken and n not in exclude), None)


def static_redis_db(adw_id: str) -> int:
    """The Redis database the static scheme (ADW_RESOURCES=static) gives an ADW: 2-14, sliced per codebase."""
    index = int(os.getenv("ADW_CODEBASE_INDEX", "0") or 0)
    slots = max(1, 13 // max(1, int(os.getenv("ADW_MAX_CODEBASES", "1") or 1)))
    try:
        n = int("".join(c for c in adw_id[-8:] if c.isalnum()), 16) % slots
    except ValueError:
        n = hash(adw_id) % slots
    return 2 + index * slots + n


def legacy_reservations(root: Optional[str] = None, max_age_hours: float = 24) -> list[tuple[str, int, int]]:
    """(adw_id, backend, frontend) of the static scheme's port reservation files in this codebase
    (trees/.port_reservations), younger than a day: ADWs started before the registry, still running."""
    folder = os.path.join(codebase_root(root), "trees", ".port_reservations")
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for name in names:
        parts = name.split("_")
        if not (name.endswith(".reserved") and len(parts) == 3):
            continue
        path = os.path.join(folder, name)
        try:
            if now() - os.path.getmtime(path) > max_age_hours * 3600:
                continue
            with open(path, encoding="utf-8") as f:
                adw_id = f.readline().strip()
            out.append((adw_id, int(parts[1]), int(parts[2].split(".")[0])))
        except (OSError, ValueError):
            continue
    return out


def acquire(adw_id: str, hold: str = "process", worktree: Optional[str] = None, pid: Optional[int] = None,
            prefer_ports=None, prefer_redis: Optional[int] = None, db_name: Optional[str] = None,
            exclude_ports: Iterable = (), exclude_redis: Iterable = (), root: Optional[str] = None) -> dict:
    """The workflow's lease: its existing one (heartbeat refreshed), or a new one with a free port pair and Redis
    database. Raises ResourcesExhausted when either pool is used up."""
    pid = pid or os.getpid()
    with _locked() as data:
        lease = data["leases"].get(adw_id)
        t = now()
        if lease:
            lease["heartbeat"] = t
            if hold == "process" or lease.get("hold") != "process":
                lease.update(pid=pid, pgid=_pgid(pid))
            if hold == "process":
                lease["hold"] = "process"
            if worktree:
                lease["worktree"] = worktree
            if db_name:
                lease["db_name"] = db_name
            if lease.get("redis_db") is None:
                lease["redis_db"] = _pick_redis(data, prefer_redis, set(exclude_redis))
            return dict(lease)
        legacy = [r for r in legacy_reservations(root) if r[0] not in data["leases"] and r[0] != adw_id]
        exclude_ports = set(exclude_ports) | {(b, f) for _, b, f in legacy}
        exclude_redis = set(exclude_redis) | {static_redis_db(a) for a, _, _ in legacy}
        ports = _pick_ports(data, prefer_ports, exclude_ports)
        if not ports:
            raise ResourcesExhausted(f"No free port pair in {setting('backend_ports')} / "
                                     f"{setting('frontend_ports')} ({len(data['leases'])} leases on this machine)")
        redis_db = _pick_redis(data, prefer_redis, exclude_redis)
        if redis_db is None:
            raise ResourcesExhausted(f"No free Redis database in {setting('redis_dbs')} "
                                     f"({len(data['leases'])} leases on this machine)")
        lease = {"adw_id": adw_id, "codebase": codebase(root), "pid": pid, "pgid": _pgid(pid), "host": host(),
                 "hold": hold, "worktree": worktree, "created": t, "heartbeat": t, "backend_port": ports[0],
                 "frontend_port": ports[1], "redis_db": redis_db, "db_name": db_name}
        data["leases"][adw_id] = lease
        return dict(lease)


def _pgid(pid) -> Optional[int]:
    try:
        return os.getpgid(int(pid))
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def get(adw_id: str) -> Optional[dict]:
    with _locked() as data:
        lease = data["leases"].get(adw_id)
        return dict(lease) if lease else None


def update(adw_id: str, **fields) -> Optional[dict]:
    with _locked() as data:
        lease = data["leases"].get(adw_id)
        if lease:
            lease.update({k: v for k, v in fields.items() if v is not None})
            return dict(lease)
        return None


def heartbeat(adw_id: str) -> None:
    """Keep a long-running workflow's lease and slots fresh (call it every minute or so)."""
    with _locked() as data:
        t = now()
        if adw_id in data["leases"]:
            data["leases"][adw_id]["heartbeat"] = t
        for holders in data["slots"].values():
            for entry in holders.values():
                if entry.get("adw_id") == adw_id:
                    entry["heartbeat"] = t


def release_lease(adw_id: str) -> Optional[dict]:
    """Free the workflow's ports and Redis database (its slots stay)."""
    with _locked() as data:
        return data["leases"].pop(adw_id, None)


def release(adw_id: str) -> dict:
    """Free everything the workflow holds: its lease and its slots. Safe to call twice."""
    with _locked() as data:
        lease = data["leases"].pop(adw_id, None)
        data["waiting"].pop(adw_id, None)
        slots = []
        for kind, holders in data["slots"].items():
            for holder, entry in list(holders.items()):
                if holder == adw_id or entry.get("adw_id") == adw_id:
                    del holders[holder]
                    slots.append(kind)
        return {"lease": lease, "slots": slots}


# ---- slots ----------------------------------------------------------------------

def try_acquire_slot(kind: str, holder: str, adw_id: Optional[str] = None, pid: Optional[int] = None,
                     max_slots: Optional[int] = None, label: Optional[str] = None, issue=None) -> bool:
    """Take one of the `kind` slots for holder (idempotent: a holder that has one keeps it, pid updated).
    label / issue (e.g. "#26 Get tickets", 26) are only for display (machine_view)."""
    pid = pid or os.getpid()
    cap = max_slots or limit(kind)
    extra = {k: v for k, v in (("label", label), ("issue", issue)) if v is not None}
    with _locked() as data:
        holders = data["slots"].setdefault(kind, {})
        t = now()
        if holder in holders:
            holders[holder].update(pid=pid, heartbeat=t, **extra)
            data["waiting"].pop(holder, None)
            return True
        if len(holders) >= cap:
            return False
        holders[holder] = {"adw_id": adw_id or holder, "pid": pid, "host": host(), "codebase": codebase(),
                           "created": t, "heartbeat": t, **extra}
        data["waiting"].pop(holder, None)
        return True


WAIT_TTL = 15 * 60                       # a waiter not refreshed for this long is dropped


def note_waiting(holder: str, label: Optional[str] = None, issue=None, pid: Optional[int] = None,
                 root: Optional[str] = None) -> None:
    """Record that holder waits for a workflow slot (display only). Cheap to call often: the file is only
    rewritten when the entry is new, changed, or its heartbeat is a minute old."""
    pid = pid or os.getpid()
    with _locked() as data:
        t = now()
        entry = data["waiting"].get(holder)
        if entry and t - (entry.get("heartbeat") or 0) < 60 and entry.get("label") == label:
            return
        if entry:
            entry.update(heartbeat=t, pid=pid, label=label, issue=issue)
        else:
            data["waiting"][holder] = {"adw_id": holder, "label": label, "issue": issue, "pid": pid, "host": host(),
                                       "codebase": codebase(root), "created": t, "heartbeat": t}


def stop_waiting(holder: str) -> None:
    with _locked() as data:
        data["waiting"].pop(holder, None)


def set_slot_pid(kind: str, holder: str, pid: int) -> None:
    with _locked() as data:
        entry = data["slots"].get(kind, {}).get(holder)
        if entry:
            entry.update(pid=pid, heartbeat=now())


def acquire_slot(kind: str, holder: str, adw_id: Optional[str] = None, wait: float = 0, poll: float = 5.0,
                 on_wait=None) -> bool:
    """try_acquire_slot, waiting up to `wait` seconds (None: forever) for a free one; on_wait(used, cap) is
    called once when it has to wait."""
    deadline = None if wait is None else now() + wait
    told = False
    while True:
        if try_acquire_slot(kind, holder, adw_id=adw_id):
            return True
        if deadline is not None and now() >= deadline:
            return False
        if not told and on_wait:
            on_wait(*slot_usage(kind))
            told = True
        time.sleep(poll)


def release_slot(kind: str, holder: str) -> None:
    with _locked() as data:
        data["slots"].get(kind, {}).pop(holder, None)


def slot_usage(kind: str) -> tuple[int, int]:
    """(slots in use machine-wide, the limit)."""
    with _locked() as data:
        return len(data["slots"].get(kind, {})), limit(kind)


def free_slots(kind: str = WORKFLOW) -> int:
    used, cap = slot_usage(kind)
    return max(0, cap - used)


def holds_slot(kind: str, holder: str) -> bool:
    with _locked() as data:
        return holder in data["slots"].get(kind, {})


def capacity(probe_ports: bool = False) -> dict:
    """What a new workflow could get now: free port pairs and Redis databases (not reserved)."""
    with _locked() as data:
        taken = set()
        for lease in data["leases"].values():
            taken |= {lease.get("backend_port"), lease.get("frontend_port")}
        pairs = [(b, f) for b, f in port_pairs() if b not in taken and f not in taken]
        if probe_ports:
            pairs = [(b, f) for b, f in pairs if port_free(b) and port_free(f)]
        redis_taken = {lease.get("redis_db") for lease in data["leases"].values()}
        return {"ports": len(pairs), "redis": sum(1 for n in redis_pool() if n not in redis_taken)}


def gc() -> list[dict]:
    """Reclaim stale leases and slots now; returns what was reclaimed."""
    with _locked() as data:
        return list(data["_reclaimed_now"])


def snapshot() -> dict:
    """The whole registry (stale entries reclaimed first), for `adw_resources.py status`."""
    with _locked() as data:
        out = json.loads(json.dumps(data))
    now_ = out.pop("_reclaimed_now", None) or []
    out["reclaimed"] = ((out.get("reclaimed") or []) + now_)[-20:]
    out["limits"] = {k: limit(k) for k in _LIMITS}
    out["pools"] = {"ports": f"{setting('backend_ports')} / {setting('frontend_ports')} ({len(port_pairs())} pairs)",
                    "redis": f"{setting('redis_dbs')} -> {len(redis_pool())} usable "
                             f"(server has {redis_server_databases() or 'unknown'})"}
    out["path"] = registry_path()
    return out


def running_workflows() -> int:
    return slot_usage(WORKFLOW)[0]


# ---- Claude usage (machine-wide) ---------------------------------------------------

def usage_path() -> str:
    return os.path.join(shared_dir(), "usage.json")


def iso_local(epoch: Optional[float] = None) -> str:
    """An ISO time with the local UTC offset, e.g. 2026-11-04T10:02:11+02:00."""
    return datetime.fromtimestamp(time.time() if epoch is None else epoch).astimezone().isoformat(timespec="seconds")


def _percent(util) -> Optional[float]:
    if not isinstance(util, (int, float)) or isinstance(util, bool):
        return None
    value = round(util * 100 if util <= 1 else util, 1)
    return int(value) if value == int(value) else value


def _window(w: dict) -> dict:
    out: dict = {}
    pct = _percent(w.get("utilization"))
    if pct is not None:
        out["used_percent"] = pct
    resets = w.get("resetsAt")
    if isinstance(resets, (int, float)) and resets > 0:
        out["resets_at"] = iso_local(resets)
    if w.get("status"):
        out["status"] = str(w["status"])
    return out


def usage_windows(info: dict) -> dict:
    """{kind: {"used_percent", "resets_at", "status"}} from a rate_limit_event's rate_limit_info: every window in
    unifiedWindows, and the event's own rateLimitType (top-level resetsAt / utilization) when it isn't there."""
    out: dict = {}
    for kind, w in (info.get("unifiedWindows") or {}).items():
        if isinstance(w, dict) and _window(w):
            out[str(kind)] = _window(w)
    kind = info.get("rateLimitType")
    if kind and str(kind) not in out and _window(info):
        out[str(kind)] = _window(info)
    return out


@contextlib.contextmanager
def _file_lock(name: str):
    d = shared_dir()
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "a+") as lock:
        if fcntl is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def read_usage() -> dict:
    try:
        with open(usage_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def record_rate_limit(info: dict) -> bool:
    """Merge one rate_limit_event's rate_limit_info into ~/.adw/usage.json (machine-wide; atomic, locked).
    Best effort: never raises. True when something was recorded."""
    try:
        windows = usage_windows(info) if isinstance(info, dict) else {}
        if not windows:
            return False
        with _file_lock("usage.lock"):
            data = read_usage()
            known = data.get("windows") if isinstance(data.get("windows"), dict) else {}
            seen = iso_local()
            for kind, w in windows.items():
                old = known.get(kind) or {}
                if "used_percent" not in w and old.get("resets_at") == w.get("resets_at"):
                    w = {**old, **w}              # same window, no new figure: keep the last one
                known[kind] = {**w, "seen": seen}
            data.update(windows=known, as_of=seen)
            tmp = usage_path() + f".{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1, sort_keys=True)
            os.replace(tmp, usage_path())
        return True
    except Exception:  # noqa: BLE001 - reporting must never stop a workflow
        return False


def claude_account() -> Optional[str]:
    """The Claude plan this machine's `claude` is signed in with (from ~/.claude.json, offline), e.g. "Claude Max";
    "API key" when ANTHROPIC_API_KEY is set; None when unknown."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return "API key"
    try:
        with open(os.path.expanduser(os.path.join("~", ".claude.json")), encoding="utf-8") as f:
            account = json.load(f).get("oauthAccount") or {}
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(account, dict):
        return None
    plan = str(account.get("planDisplayName") or "").strip()
    if not plan:
        plan = {"claude_max": "Max", "claude_pro": "Pro", "claude_team": "Team",
                "claude_enterprise": "Enterprise"}.get(str(account.get("organizationType") or ""), "")
    if not plan:
        return None
    return plan if plan.lower().startswith("claude") else f"Claude {plan}"


def usage_view(t: Optional[float] = None) -> Optional[dict]:
    """The machine query's usage: {"account", "as_of", "windows": [{"kind", "used_percent", "resets_at"}]}.
    A window whose reset time has passed shows 0% without a reset time (it has reset; no newer figure yet)."""
    t = t or now()
    data = read_usage()
    windows = []
    order = {"five_hour": 0, "seven_day": 1}
    for kind, w in sorted((data.get("windows") or {}).items(), key=lambda kv: (order.get(kv[0], 9), kv[0])):
        if not isinstance(w, dict):
            continue
        item = {"kind": kind}
        try:
            reset = datetime.fromisoformat(w["resets_at"]).timestamp() if w.get("resets_at") else None
        except (TypeError, ValueError):
            reset = None
        if reset is not None and reset <= t:
            item["used_percent"] = 0
        else:
            if "used_percent" in w:
                item["used_percent"] = w["used_percent"]
            if w.get("resets_at"):
                item["resets_at"] = w["resets_at"]
        if w.get("status"):
            item["status"] = w["status"]
        windows.append(item)
    out: dict = {}
    account = claude_account()
    if account:
        out["account"] = account
    if data.get("as_of"):
        out["as_of"] = data["as_of"]
    if windows:
        out["windows"] = windows
    return out or None


# ---- the machine view (Ore's `machine` query) ------------------------------------------

def machine_name() -> str:
    if sys.platform == "darwin":
        try:
            name = subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, text=True,
                                  timeout=5).stdout.strip()
            if name:
                return name
        except Exception:  # noqa: BLE001
            pass
    return host().split(".")[0]


def os_kind() -> Optional[str]:
    if sys.platform == "darwin":
        version = platform.mac_ver()[0]
        return f"macOS {version}" if version else "macOS"
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return f"{platform.system()} {platform.release()}".strip() or None


def cpu_percent() -> Optional[int]:
    """A cheap estimate: the 1-minute load average per CPU, as a percentage (capped at 100)."""
    try:
        load = os.getloadavg()[0]
        return min(100, round(load / max(1, os.cpu_count() or 1) * 100))
    except (AttributeError, OSError):
        return None


def _adw_state(root: Optional[str], adw_id: str) -> dict:
    if not root:
        return {}
    try:
        with open(os.path.join(root, "agents", adw_id, "adw_state.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _issue_number(value) -> Optional[int]:
    try:
        return int(str(value).lstrip("#"))
    except (TypeError, ValueError):
        return None


def _workflow_label(entry: dict, state: dict, adw_id: str) -> tuple:
    """("#26 Get tickets", 26) from the slot's label, else the workflow's state, else (adw_id, None)."""
    issue = _issue_number(entry.get("issue")) or _issue_number(state.get("issue_number"))
    if entry.get("label"):
        return str(entry["label"]), issue
    if issue:
        return f"#{issue} {state.get('issue_title') or ''}".strip(), issue
    return adw_id, None


def _entry(project: Optional[str], label: str, adw_id: Optional[str], issue, since) -> dict:
    item = {"project": project or "?", "workflow": label}
    if adw_id:
        item["adw_id"] = adw_id
    if issue:
        item["issue"] = issue
    if since:
        item["since"] = iso_local(since)
    return item


def machine_view() -> dict:
    """Ore's `machine` query: this machine, its workflow and suite slots, the leases of every codebase (a workflow
    slot without a lease too), what waits for a slot, the free pools, and the latest Claude usage windows.
    Every field is best effort."""
    with _locked() as data:
        snap = json.loads(json.dumps({k: data.get(k) or {} for k in ("leases", "slots", "waiting")}))
    workflow_slots = snap["slots"].get(WORKFLOW) or {}
    by_adw = {(e.get("adw_id") or h): e for h, e in workflow_slots.items()}
    leases = []
    for adw_id, lease in sorted(snap["leases"].items(), key=lambda kv: kv[1].get("created") or 0):
        slot = by_adw.get(adw_id) or {}
        cb = lease.get("codebase") or slot.get("codebase") or {}
        label, issue = _workflow_label(slot, _adw_state(cb.get("root"), adw_id), adw_id)
        item = _entry(cb.get("name"), label, adw_id, issue, slot.get("created") or lease.get("created"))
        if lease.get("backend_port"):
            item["ports"] = f"{lease.get('backend_port')} / {lease.get('frontend_port')}"
        if lease.get("redis_db") is not None:
            item["redis"] = lease["redis_db"]
        leases.append(item)
    for adw_id, slot in sorted(by_adw.items(), key=lambda kv: kv[1].get("created") or 0):
        if adw_id not in snap["leases"]:
            cb = slot.get("codebase") or {}
            label, issue = _workflow_label(slot, _adw_state(cb.get("root"), adw_id), adw_id)
            leases.append(_entry(cb.get("name"), label, adw_id, issue, slot.get("created")))
    queue = [_entry((w.get("codebase") or {}).get("name"), w.get("label") or holder, None,
                    _issue_number(w.get("issue")), w.get("created"))
             for holder, w in sorted(snap["waiting"].items(), key=lambda kv: kv[1].get("created") or 0)]
    room = capacity()
    out: dict = {"name": machine_name(), "host": host()}
    kind = os_kind()
    if kind:
        out["kind"] = kind
    cpu = cpu_percent()
    if cpu is not None:
        out["cpu_percent"] = cpu
    out.update({
        "workflows": {"used": len(workflow_slots), "max": limit(WORKFLOW)},
        "suites": {"used": len(snap["slots"].get(FULL_SUITE) or {}), "max": limit(FULL_SUITE)},
        "leases": leases,
        "queue": queue,
        "free": {"ports": room["ports"], "ports_total": len(port_pairs()),
                 "redis": room["redis"], "redis_total": len(redis_pool())},
        "config": os.path.join(shared_dir(), "config.json").replace(os.path.expanduser("~"), "~", 1),
    })
    usage = usage_view()
    if usage:
        out["usage"] = usage
    return out
