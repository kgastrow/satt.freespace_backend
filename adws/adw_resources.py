#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///

"""
The machine-wide ADW resource registry (adw_modules/resources.py), across every codebase on this machine.

Usage:
  uv run adws/adw_resources.py status [--json]     # leases (ports, Redis, database), slots, pools, limits
  uv run adws/adw_resources.py release <adw_id>    # free a workflow's lease and slots by hand
  uv run adws/adw_resources.py gc                  # reclaim stale leases and slots now (dead pid, old heartbeat)
  uv run adws/adw_resources.py redis <adw_id>      # the ADW's Redis database number (leased if it has none;
                                                   # ADW_RESOURCES=static: the static formula), for /install_worktree

The registry lives in ~/.adw/resources.json (ADW_SHARED_DIR overrides the folder). Stale entries are also
reclaimed automatically whenever any ADW touches the registry.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adw_modules import resources  # noqa: E402


def _age(t) -> str:
    if not t:
        return "-"
    s = max(0, int(time.time() - t))
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def _alive(entry: dict) -> str:
    if entry.get("host") and entry["host"] != resources.host():
        return f"on {entry['host']}"
    return "alive" if resources.pid_alive(entry.get("pid")) else "gone"


def status(as_json: bool = False) -> int:
    snap = resources.snapshot()
    if as_json:
        print(json.dumps(snap, indent=1, sort_keys=True))
        return 0
    mode = "registry" if resources.enabled() else "static (ADW_RESOURCES=static: this codebase doesn't use it)"
    print(f"Registry: {snap['path']}  [{mode}]")
    print(f"Pools: ports {snap['pools']['ports']}; Redis {snap['pools']['redis']}")
    leases = sorted(snap["leases"].values(), key=lambda x: x.get("created") or 0)
    print(f"\nLeases ({len(leases)}):")
    if leases:
        print(f"  {'adw_id':<28} {'codebase':<18} {'ports':<11} {'redis':>5}  {'database':<22} {'hold':<8} "
              f"{'pid':>7} {'proc':<6} {'age':>7} {'beat':>7}")
    for lease in leases:
        ports = f"{lease.get('backend_port')}/{lease.get('frontend_port')}"
        print(f"  {lease.get('adw_id', '?'):<28} {(lease.get('codebase') or {}).get('name', '?')[:18]:<18} "
              f"{ports:<11} {str(lease.get('redis_db')):>5}  {str(lease.get('db_name') or '-')[:22]:<22} "
              f"{lease.get('hold', '?'):<8} {str(lease.get('pid')):>7} {_alive(lease):<6} "
              f"{_age(lease.get('created')):>7} {_age(lease.get('heartbeat')):>7}")
    for kind, cap in snap["limits"].items():
        holders = (snap["slots"].get(kind) or {})
        print(f"\nSlots '{kind}': {len(holders)}/{cap} in use")
        for holder, e in sorted(holders.items(), key=lambda kv: kv[1].get("created") or 0):
            print(f"  {holder:<40} {(e.get('codebase') or {}).get('name', '?')[:18]:<18} pid {e.get('pid')} "
                  f"({_alive(e)}), {_age(e.get('created'))}")
    waiting = sorted((snap.get("waiting") or {}).values(), key=lambda e: e.get("created") or 0)
    if waiting:
        print(f"\nWaiting for a workflow slot ({len(waiting)}):")
        for e in waiting:
            print(f"  {str(e.get('label') or e.get('adw_id'))[:40]:<40} "
                  f"{(e.get('codebase') or {}).get('name', '?')[:18]:<18} {_age(e.get('created'))}")
    room = resources.capacity()
    print(f"\nFree now: {room['ports']} port pairs, {room['redis']} Redis databases, "
          f"{resources.free_slots(resources.WORKFLOW)} workflow slots")
    if snap.get("reclaimed"):
        print("\nRecently reclaimed:")
        for r in snap["reclaimed"][-5:]:
            print(f"  {r.get('at')} {r.get('what')} {r.get('adw_id')} ({r.get('codebase')}): {r.get('why')}")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0 if argv else 2
    cmd = argv[0]
    if cmd == "status":
        return status("--json" in argv)
    if cmd == "release" and len(argv) == 2:
        out = resources.release(argv[1])
        if not out["lease"] and not out["slots"]:
            print(f"{argv[1]} holds nothing in the registry")
            return 1
        lease = out["lease"] or {}
        print(f"Released {argv[1]}: " + ", ".join(
            filter(None, [f"ports {lease.get('backend_port')}/{lease.get('frontend_port')}" if lease else "",
                          f"Redis {lease.get('redis_db')}" if lease else "",
                          f"slots: {', '.join(out['slots'])}" if out["slots"] else ""])))
        return 0
    if cmd == "redis" and len(argv) == 2:
        if not resources.enabled():
            print(resources.static_redis_db(argv[1]))
            return 0
        lease = resources.get(argv[1]) or resources.acquire(
            argv[1], hold="worktree", worktree=os.path.join(resources.codebase_root(), "trees", argv[1]))
        print(lease["redis_db"])
        return 0
    if cmd == "gc":
        gone = resources.gc()
        for r in gone:
            print(f"Reclaimed {r['what']} {r['adw_id']} ({r.get('codebase')}): {r['why']}")
        print(f"{len(gone)} stale entr{'y' if len(gone) == 1 else 'ies'} reclaimed")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
