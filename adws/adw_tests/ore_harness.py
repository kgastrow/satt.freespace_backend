#!/usr/bin/env python3
"""Run a workspace script the way Ore does and answer its questions automatically (tests, rehearsals).

    python adws/adw_tests/ore_harness.py [--out messages.jsonl] [--change-once] [--messages] -- \\
        adws/adw_triggers/trigger_ore.py --simulate

Ore's protocol (docs/script-protocol.md in Ore): JSON lines on stdout, answers as {"id", "value"} lines on stdin.
Questions get their first option (all options for multiSelect), a text question "Go ahead as you think best", a
group review is started as proposed (or, with --change-once, sent back once with feedback first), and every review
(prototype, risks, the build check) is approved. With
--messages (for a script whose status says "accepts": ["message"]), it talks to the first running part like a
user would: an ask, then a pause, a resume a few status messages later, then an amend to the whole run, each once
the previous one got its reply. Every message is written to --out; the summary goes to stderr. The script gets an ore_sdk on PYTHONPATH: ORE_SDK_DIR, ~/.ore/sdk (where Ore copies it over SSH), or a
minimal built-in one.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

STUB_SDK = '''import json, os, sys, itertools
_ids = itertools.count(1)
def _emit(m):
    sys.stdout.write(json.dumps(m, ensure_ascii=False) + "\\n"); sys.stdout.flush()
def _wait(key):
    for line in sys.stdin:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get("id") == key:
            return m.get("value")
    raise EOFError("stdin closed")
def status(message, progress=None, parts=None):
    m = {"type": "status", "message": message, "progress": progress}
    if parts is not None: m["parts"] = parts
    _emit(m)
def checkpoint(*a): _emit({"type": "checkpoint", "args": [str(x) for x in a]})
def cleanup(*a, description="", options=()):
    _emit({"type": "cleanup", "args": [str(x) for x in a], "description": description, "options": list(options)})
def cleanup_options(): return {k for k in os.environ.get("ORE_CLEANUP_OPTIONS", "").split(",") if k}
def log(message): print(message, file=sys.stderr, flush=True)
def ask_questions(questions, prompt="", key=None):
    key = key or f"q{next(_ids)}"
    _emit({"type": "input_request", "id": key, "prompt": prompt or "Please answer", "kind": "questions",
           "questions": questions}); return _wait(key)
def review_groups(groups, prompt="", key=None):
    key = key or f"g{next(_ids)}"
    _emit({"type": "input_request", "id": key, "prompt": prompt or "Review the groups", "kind": "groups",
           "groups": groups}); return _wait(key)
def result(summary, links=(), actions=(), data=None):
    _emit({"type": "result", "summary": summary,
           "links": [{"label": l[0], "url": l[1]} if isinstance(l, (list, tuple)) else l for l in links],
           "actions": list(actions), "data": data})
def error(message, exit_code=1):
    _emit({"type": "error", "message": message}); raise SystemExit(exit_code)
'''


def sdk_dir() -> str:
    for d in (os.environ.get("ORE_SDK_DIR"), str(Path.home() / ".ore" / "sdk")):
        if d and (Path(d) / "ore_sdk.py").exists():
            return d
    d = tempfile.mkdtemp(prefix="ore-sdk-stub-")
    (Path(d) / "ore_sdk.py").write_text(STUB_SDK, encoding="utf-8")
    return d


def answer(msg: dict, state: dict):
    kind = msg.get("kind", "text")
    if kind == "questions":
        out = {}
        for q in msg.get("questions") or []:
            labels = [o["label"] for o in q.get("options") or []]
            out[q["question"]] = labels if q.get("multiSelect") else labels[0]
        return out
    if kind == "groups":
        if state.get("change_once") and not state.get("changed"):
            state["changed"] = True
            return {"action": "change", "feedback": "Keep the checkout typo apart from the rest"}
        return {"action": "start", "groups": [{"title": g["title"], "item_ids": [i["id"] for i in g["items"]]}
                                              for g in msg.get("groups") or []]}
    if kind == "review":                  # a prototype, risks or the build check: approved
        return {"action": "approve"}
    if kind in ("choice", "confirm"):
        return (msg.get("options") or ["Yes"])[0]
    return "Go ahead as you think best"


class Talker:
    """--messages: one conversation with the first running part, each step after the previous step's reply (the
    resume a few seconds after the pause was acknowledged). Runs in its own thread: a paused run may go quiet."""

    PLAN = [("ask", "How far along are you?", False), ("pause", "Hold on a moment, please.", False),
            ("resume", "Carry on.", False), ("amend", "Please keep the CSV export's column order stable.", True)]

    def __init__(self, send, msgs: list):
        self.send, self.msgs = send, msgs
        self.step, self.part, self.waiting_for, self.ready_at = 0, None, None, 0.0
        self.replies: dict = {}
        self.lock = threading.Lock()

    def on_message(self, msg: dict) -> None:
        with self.lock:
            if msg["type"] == "reply":
                self.replies.setdefault(msg.get("to"), []).append(msg)
                if msg.get("to") == self.waiting_for:
                    self.waiting_for = None
                    self.ready_at = time.time() + (3.0 if self.step == 2 else 0.0)
            elif msg["type"] == "status" and "message" in (msg.get("accepts") or []) and self.part is None:
                running = [p for p in msg.get("parts") or [] if p.get("status") == "running"]
                if running:
                    self.part = running[0]["key"]

    def loop(self, proc) -> None:
        while proc.poll() is None:
            time.sleep(0.3)
            with self.lock:
                if self.part is None or self.waiting_for or self.step >= len(self.PLAN) or \
                        time.time() < self.ready_at:
                    continue
                mode, text, whole_run = self.PLAN[self.step]
                self.step += 1
                out = {"type": "message", "id": f"m{self.step}", "part": None if whole_run else self.part,
                       "text": text, "mode": mode, "from": "Harness"}
                self.waiting_for = out["id"]
                self.msgs.append(out)
            self.send(out)


def run(script_args: list[str], env: dict | None = None, cwd: str | None = None, change_once: bool = False,
        timeout: float = 900, python: str | None = None, talk: bool = False) -> tuple[int, list[dict], str]:
    """(exit code, every protocol message, stderr) of one run of `python -u <script_args>`. With talk, the
    messages the harness sent are in the list too (type "message", as sent)."""
    env = {**os.environ, **(env or {})}
    env.update(PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", ORE_PROTOCOL="1", ORE_RUN_ID="harness",
               ORE_RESUMED="0", ORE_WORKSPACE="harness", ORE_WORKSPACE_KIND="code",
               PYTHONPATH=os.pathsep.join(filter(None, [sdk_dir(), env.get("PYTHONPATH")])))
    proc = subprocess.Popen([python or sys.executable, "-u", *script_args], cwd=cwd, env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    errf = tempfile.TemporaryFile()
    threading.Thread(target=lambda: [errf.write(b) for b in iter(proc.stderr.readline, b"")], daemon=True).start()
    msgs, state = [], {"change_once": change_once}
    lock = threading.Lock()

    def send(out: dict) -> None:
        with lock:
            try:
                proc.stdin.write((json.dumps(out, ensure_ascii=False) + "\n").encode())
                proc.stdin.flush()
            except OSError:
                pass

    talker = Talker(send, msgs) if talk else None
    if talker:
        threading.Thread(target=talker.loop, args=(proc,), daemon=True).start()
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    try:
        for raw in iter(proc.stdout.readline, b""):
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(msg, dict) or "type" not in msg:
                continue
            msgs.append(msg)
            if msg["type"] == "input_request":
                send({"id": msg["id"], "value": answer(msg, state)})
            elif talker:
                talker.on_message(msg)
        code = proc.wait()
    finally:
        timer.cancel()
    errf.seek(0)
    return code, msgs, errf.read().decode("utf-8", "replace")


def main(argv: list[str]) -> int:
    out, change_once = None, False
    if "--" not in argv:
        print(__doc__, file=sys.stderr)
        return 2
    i = argv.index("--")
    opts, script_args = argv[:i], argv[i + 1:]
    if "--out" in opts:
        out = opts[opts.index("--out") + 1]
    change_once = "--change-once" in opts
    code, msgs, err = run(script_args, change_once=change_once, talk="--messages" in opts)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            for m in msgs:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
    kinds = {}
    for m in msgs:
        kinds[m["type"]] = kinds.get(m["type"], 0) + 1
    final = next((m for m in reversed(msgs) if m["type"] in ("result", "error")), None)
    print(f"exit {code}; messages: {json.dumps(kinds)}", file=sys.stderr)
    for m in msgs:
        if m["type"] == "input_request":
            print(f"asked ({m.get('kind')}, {m.get('id')}): {m.get('prompt')}", file=sys.stderr)
        elif m["type"] == "message":
            print(f"sent {m['mode']} {m['id']} to {m.get('part') or 'the run'}: {m['text']}", file=sys.stderr)
        elif m["type"] == "reply":
            print(f"reply to {m.get('to')} ({m.get('part') or 'run'}): {m.get('text')}", file=sys.stderr)
    if final:
        print(f"final: {json.dumps(final, ensure_ascii=False)[:600]}", file=sys.stderr)
    if code:
        print(err[-2000:], file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
