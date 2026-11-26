"""Messages between Ore (through the Ore trigger), an orchestrated workflow and its orchestrator agent, plus the
usage and screenshots a workflow reports. Plain files in the workflow's agents/<adw_id>/ folder, so every side
(trigger, workflow, adw_report.py) works across restarts and without sockets:

- inbox.jsonl, written by the trigger, read by the workflow (forwarded to the orchestrator session) and by
  `adw_report.py ask|wait`:
    {"ts", "type": "message", "id", "mode": "ask|amend|pause|resume", "text", "from"}
    {"ts", "type": "answer", "ask": <n>, "text"}            the user's answer to the orchestrator's question n
    {"ts", "type": "check_result", "n", "batch", "status": "green|failed|conflict|error", "yours", "combined",
     "preexisting", "unknown" (lists of {"suite", "key", "text"}), "conflict", "report", "error"}
                                                             this workflow's part of the batch's full check n
- outbox.jsonl, written by `adw_report.py reply|ask`, read by the trigger:
    {"ts", "type": "reply", "to": <message id>, "text"}
    {"ts", "type": "ask", "n", "question", "options": [...], "at"}   (at: epoch seconds it was asked)
    {"ts", "type": "ask_cancel", "n"}                         the agent stopped waiting (only with
                                                              ADW_ASK_TIMEOUT_MIN set) and decided itself
    {"ts", "type": "check", "n", "sha", "branch"}             `adw_report.py check`: the full check for this commit
- usage.json, written by the workflow from the orchestrator's stream-json output (see Usage), read by the trigger.
  Every rate_limit_event seen also goes machine-wide to ~/.adw/usage.json (resources.record_rate_limit).
- images.jsonl, written by `adw_report.py image`: {"ts", "label", "url"}.
- result.json, written by `adw_report.py result` when the orchestrator finishes (RESULT_SCHEMA; "force": true when
  it gives up while subagents still run), read by the workflow, which ends the session on it once no background
  task is running.
- report.md, written by `adw_report.py result --report-file`: the orchestrator's report of the whole workflow
  (summary, decisions and why, what wasn't done and why, what's pending, caveats). The trigger shows it in Ore
  with the result, and adw_merge_iso.py gives it to the agent that resolves merge conflicts.

Everything here is best effort: a reporting problem must never stop a workflow.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

MODES = ("ask", "amend", "pause", "resume", "follow_up")
INBOX, OUTBOX, USAGE, IMAGES = "inbox.jsonl", "outbox.jsonl", "usage.json", "images.jsonl"
RESULT = "result.json"
FOLLOW_UP = "followup.json"          # the follow-up the trigger hands a finished workflow (--follow-up)
REPORT = "report.md"
REPORT_LIMIT = 40_000          # characters kept of a report

# The orchestrator's final result (`adw_report.py result`).
RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["pr_opened", "failed", "dropped"]},
        "pr_url": {"type": "string"},
        "summary": {"type": "string", "description": "What was delivered, in 1-3 sentences"},
        "review_rounds": {"type": "integer"},
        "open_blockers": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string", "description": "Why it failed (failed), or why there is nothing to do "
                                                    "(dropped)"},
    },
    "required": ["status", "summary"],
}
_TYPES = {"object": dict, "string": str, "integer": int, "array": list, "boolean": bool}


def schema_errors(value, schema: dict = RESULT_SCHEMA, where: str = "result") -> list[str]:
    """What's wrong with value under the small JSON-schema subset RESULT_SCHEMA uses (type, enum, properties,
    required, items); [] when it's valid. Unknown properties are errors too."""
    kind = schema.get("type")
    if kind and (not isinstance(value, _TYPES[kind]) or (kind == "integer" and isinstance(value, bool))):
        return [f"{where} must be {'an' if kind[0] in 'aeiou' else 'a'} {kind}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{where} must be one of {', '.join(map(str, schema['enum']))}"]
    errors = []
    if kind == "object":
        props = schema.get("properties", {})
        errors += [f"{where}.{k} is required" for k in schema.get("required", []) if k not in value]
        errors += [f"{where}.{k} is not a known field" for k in value if k not in props]
        for k, v in value.items():
            if k in props:
                errors += schema_errors(v, props[k], f"{where}.{k}")
    if kind == "array" and "items" in schema:
        for i, v in enumerate(value):
            errors += schema_errors(v, schema["items"], f"{where}[{i}]")
    return errors


def read_result(path: str) -> dict | None:
    """The result `adw_report.py result` wrote ("force" included), or None when there's none or it isn't valid."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    force = data.pop("force", False)
    if schema_errors(data):
        return None
    return {**data, "force": bool(force)}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def append(path: str, entry: dict) -> dict:
    """One JSON line (with a timestamp) appended to path; returns the entry written."""
    entry = {"ts": now_iso(), **entry}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_new(path: str, offset: int = 0) -> tuple[list[dict], int]:
    """The complete JSON lines after byte `offset`, and the offset after them (a half-written line waits)."""
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read()
    except OSError:
        return [], offset
    end = data.rfind(b"\n") + 1
    out = []
    for raw in data[:end].splitlines():
        try:
            entry = json.loads(raw.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out, offset + end


def read_all(path: str) -> list[dict]:
    return read_new(path, 0)[0]


def size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


# ---- what the orchestrator gets ---------------------------------------------------------

def sender(msg: dict) -> str:
    return str(msg.get("from") or "the user").strip() or "the user"


def for_orchestrator(msg: dict, report: str) -> str:
    """A message from Ore as the user message injected into the orchestrator's session."""
    mode = msg.get("mode") if msg.get("mode") in MODES else "ask"
    mid, text = msg.get("id") or "?", str(msg.get("text") or "").strip()
    head = f"[Message from {sender(msg)} ({mode}), id {mid}]: {text}\n\n"
    reply = f'`{report} reply {mid} "<text>"`'
    if mode == "ask":
        return head + (f"Answer briefly with {reply} (from what you know now; don't stop to investigate at length), "
                       "then continue your work.")
    if mode == "amend":
        return head + ("Take this into account from now on: adjust your plan; packages it affects that haven't "
                       "started get it in their brief, finished ones get a follow-up package, running subagents "
                       "can't be messaged (relay it when they report). Acknowledge in one line with "
                       f"{reply}, then continue.")
    if mode == "pause":
        return head + ("Pause at the next safe point: launch no new subagents, let the running ones report, commit "
                       "work in progress (`git add -A && git commit -m \"wip: ...\"`, skip if nothing changed), "
                       f"acknowledge with {reply}, then run `{report} wait` (Bash timeout 3600000). It blocks "
                       "until a resume or amend message arrives; run it again when it says so.")
    return head + (f"Resume the work where you left off (if you are still in `{report} wait`, it returns by itself). "
                   f"Acknowledge with {reply}.")


def late_answer(ask: dict, answer: dict) -> str:
    return (f"[Late answer from the user to your question {ask.get('n')} \"{ask.get('question', '')}\"]: "
            f"{answer.get('text', '')}\n\nYou already decided without it; if it changes anything that still matters, "
            "adjust now. Otherwise continue.")


def check_pending(outbox: list[dict], inbox: list[dict]) -> bool:
    """Whether the latest full-check request has no result yet (the workflow is waiting for the batch)."""
    asked = [e.get("n") for e in outbox if e.get("type") == "check"]
    return bool(asked) and not any(e.get("type") == "check_result" and e.get("n") == asked[-1] for e in inbox)


def ask_open(outbox: list[dict], inbox: list[dict]) -> bool:
    """Whether a question of the orchestrator's is still waiting for the user (no answer, not given up on)."""
    done = {e.get("ask") for e in inbox if e.get("type") == "answer"} | \
        {e.get("n") for e in outbox if e.get("type") == "ask_cancel"}
    return any(e.get("type") == "ask" and e.get("n") not in done for e in outbox)


def paused(entries: list[dict]) -> bool:
    """Whether the latest pause message has no resume or amend after it."""
    state = False
    for e in entries:
        if e.get("type") == "message" and e.get("mode") == "pause":
            state = True
        elif e.get("type") == "message" and e.get("mode") in ("resume", "amend"):
            state = False
    return state


# ---- usage (from claude's stream-json output) -------------------------------------------

def _limit(info: dict) -> dict:
    """A rate_limit_event's rate_limit_info as the protocol's usage.limit: {status, kind, resets_at, used_percent}."""
    out: dict = {}
    if info.get("status"):
        out["status"] = str(info["status"])
    kind = info.get("rateLimitType")
    if kind:
        out["kind"] = str(kind)
    resets = info.get("resetsAt")
    if isinstance(resets, (int, float)) and resets > 0:
        out["resets_at"] = datetime.fromtimestamp(resets).isoformat(timespec="seconds")
    window = (info.get("unifiedWindows") or {}).get(kind or "") or {}
    util = window.get("utilization", info.get("utilization"))
    if isinstance(util, (int, float)):
        out["used_percent"] = round(util * 100 if util <= 1 else util, 1)
    return out


def _run_usage(result: dict) -> dict:
    """One claude process's usage so far, from its latest result message (total_cost_usd and modelUsage are
    cumulative per process)."""
    models = {}
    for name, m in (result.get("modelUsage") or {}).items():
        if not isinstance(m, dict):
            continue
        models[name] = {"cost_usd": round(float(m.get("costUSD") or 0), 8),
                        "input_tokens": int(m.get("inputTokens") or 0) + int(m.get("cacheCreationInputTokens") or 0),
                        "output_tokens": int(m.get("outputTokens") or 0),
                        "cache_read_tokens": int(m.get("cacheReadInputTokens") or 0)}
    return {"cost_usd": round(float(result.get("total_cost_usd") or 0), 8), "models": models}


def _flatten(run: dict) -> dict:
    """A per-process record ({cost_usd, models}) in the protocol's shape, with the token totals."""
    out = {"cost_usd": run.get("cost_usd") or 0.0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
           "models": {}}
    for name, m in (run.get("models") or {}).items():
        for k in ("input_tokens", "output_tokens", "cache_read_tokens"):
            out[k] += int(m.get(k) or 0)
        out["models"][name] = {k: m.get(k, 0) for k in ("cost_usd", "input_tokens", "output_tokens")}
    return out


def result_usage(result: dict) -> dict:
    """The usage of one `claude -p --output-format json|stream-json` result, in the protocol's shape."""
    return _flatten(_run_usage(result))


def add_usage(total: dict, part: dict) -> dict:
    """Sum two usage dicts (the protocol's shape); `limit` is the later one's when both have it."""
    out = {"cost_usd": round(float(total.get("cost_usd") or 0) + float(part.get("cost_usd") or 0), 8)}
    for k in ("input_tokens", "output_tokens", "cache_read_tokens"):
        out[k] = int(total.get(k) or 0) + int(part.get(k) or 0)
    models = {n: dict(m) for n, m in (total.get("models") or {}).items()}
    for name, m in (part.get("models") or {}).items():
        cur = models.setdefault(name, {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0})
        cur["cost_usd"] = round(float(cur.get("cost_usd") or 0) + float(m.get("cost_usd") or 0), 8)
        for k in ("input_tokens", "output_tokens"):
            cur[k] = int(cur.get(k) or 0) + int(m.get(k) or 0)
    out["models"] = models
    limits = [x for x in (total.get("limit"), part.get("limit")) if x]
    if limits:
        out["limit"] = max(limits, key=lambda x: x.get("seen") or "")
    return out


def record_machine_usage(info: dict) -> None:
    """A rate_limit_event's rate_limit_info into the machine-wide ~/.adw/usage.json (resources.record_rate_limit),
    which Ore's machine view shows. Best effort."""
    try:
        from . import resources
        resources.record_rate_limit(info)
    except Exception:  # noqa: BLE001
        pass


class UsageTracker:
    """Keeps agents/<adw_id>/usage.json up to date from a session's stream: per claude process the latest
    cumulative numbers (a resumed session is a new process), summed; the latest rate-limit information."""

    def __init__(self, path: str):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("runs", [])
        self.current = None                  # index in runs of this process

    def new_process(self) -> None:
        self.data["runs"].append({"cost_usd": 0.0, "models": {}})
        self.current = len(self.data["runs"]) - 1

    def on_message(self, msg: dict) -> bool:
        """Feed one stream-json message; True when usage.json changed."""
        kind = msg.get("type")
        if kind == "result":
            if self.current is None:
                self.new_process()
            self.data["runs"][self.current] = _run_usage(msg)
        elif kind == "rate_limit_event" and isinstance(msg.get("rate_limit_info"), dict):
            record_machine_usage(msg["rate_limit_info"])
            limit = _limit(msg["rate_limit_info"])
            if not limit:
                return False
            self.data["limit"] = {**limit, "seen": now_iso()}
        else:
            return False
        self.save()
        return True

    def set_waiting(self, until_iso: str | None) -> None:
        if until_iso:
            self.data["waiting_until"] = until_iso
        else:
            self.data.pop("waiting_until", None)
        self.save()

    def totals(self) -> dict:
        out: dict = {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "models": {}}
        for run in self.data["runs"]:
            out = add_usage(out, _flatten(run))
        if self.data.get("limit"):
            out["limit"] = self.data["limit"]
        return out

    def save(self) -> None:
        try:
            self.data.update(self.totals())
            self.data["updated"] = now_iso()
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=1)
            os.replace(tmp, self.path)
        except Exception:  # noqa: BLE001 - best effort
            pass


def protocol_usage(data: dict) -> dict:
    """The protocol's usage object from a usage.json (or any dict in that shape): unknown keys dropped."""
    out = {k: data[k] for k in ("cost_usd", "input_tokens", "output_tokens", "cache_read_tokens") if k in data}
    if data.get("models"):
        out["models"] = {n: {k: m[k] for k in ("cost_usd", "input_tokens", "output_tokens") if k in m}
                         for n, m in data["models"].items()}
    if data.get("limit"):
        out["limit"] = {k: data["limit"][k] for k in ("status", "kind", "resets_at", "used_percent")
                        if k in data["limit"]}
    return out
