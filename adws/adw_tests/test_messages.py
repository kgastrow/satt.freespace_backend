"""Messages between Ore, the trigger and the orchestrated workflow; the streaming orchestrator session; usage and
screenshots; Resume that continues an orchestrated workflow; --simulate with messages."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import types
from pathlib import Path

import pytest

ADWS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ADWS))

import adw_orchestrated_sdlc_iso as orch  # noqa: E402
import adw_report  # noqa: E402
from adw_modules import messages, orchestrated_sim, resources, steps  # noqa: E402
from adw_triggers import trigger_ore as ae  # noqa: E402

# What claude 2.1.318 really sent (a tiny Haiku run): the rate-limit event and a result's usage fields.
RATE_EVENT = {"type": "rate_limit_event", "rate_limit_info": {
    "status": "allowed", "resetsAt": 1794214800, "rateLimitType": "seven_day", "overageStatus": "allowed",
    "isUsingOverage": False, "unifiedWindows": {"seven_day": {"utilization": 0.31, "resetsAt": 1794214800,
                                                             "status": "allowed"}}},
    "session_id": "s1"}
RESULT = {"type": "result", "subtype": "success", "is_error": False, "session_id": "s1",
          "total_cost_usd": 0.0022916, "modelUsage": {"claude-haiku-5-5": {
              "inputTokens": 4, "outputTokens": 10, "cacheReadInputTokens": 25820, "cacheCreationInputTokens": 10140,
              "costUSD": 0.0022916}}}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setattr(ae, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(steps, "steps_path", lambda adw_id: str(ae.steps_file(adw_id)))
    monkeypatch.setattr(steps, "_open", {})
    monkeypatch.setattr(orch, "MAIN_ROOT", str(tmp_path))
    monkeypatch.setattr(adw_report, "POLL_SECONDS", 0.05)
    sent = []
    monkeypatch.setattr(ae, "emit", lambda msg: sent.append(msg))
    monkeypatch.setattr(ae, "IO", ae.OreInput())
    ae.IO.enabled = True
    return types.SimpleNamespace(root=tmp_path, sent=sent)


# ---- messages.py ----------------------------------------------------------------------------

def test_files_are_read_line_by_line_with_offsets(tmp_path):
    path = str(tmp_path / "a" / "inbox.jsonl")
    messages.append(path, {"type": "message", "id": "m1"})
    entries, off = messages.read_new(path, 0)
    assert [e["id"] for e in entries] == ["m1"] and entries[0]["ts"]
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"type": "message", "id": "m2"')                   # half written: waits
    assert messages.read_new(path, off) == ([], off)
    with open(path, "a", encoding="utf-8") as f:
        f.write("}\n")
    assert [e["id"] for e in messages.read_new(path, off)[0]] == ["m2"]


def test_messages_for_the_orchestrator():
    ask = messages.for_orchestrator({"id": "m1", "mode": "ask", "text": "Status?", "from": "Konrad"}, "R")
    assert ask.startswith("[Message from Konrad (ask), id m1]: Status?") and '`R reply m1 "<text>"`' in ask
    amend = messages.for_orchestrator({"id": "m2", "mode": "amend", "text": "Use EUR"}, "R")
    assert "(amend)" in amend and "from now on" in amend and "the user" in amend
    pause = messages.for_orchestrator({"id": "m3", "mode": "pause", "text": "wait"}, "R")
    assert "`R wait`" in pause and "commit" in pause
    assert "Resume" in messages.for_orchestrator({"id": "m4", "mode": "resume", "text": ""}, "R")
    entries = [{"type": "message", "mode": "pause"}, {"type": "message", "mode": "ask"}]
    assert messages.paused(entries)
    assert not messages.paused(entries + [{"type": "message", "mode": "amend"}])


def test_usage_tracker_sums_processes_and_keeps_the_latest_limit(tmp_path):
    path = str(tmp_path / "usage.json")
    t = messages.UsageTracker(path)
    t.new_process()
    assert t.on_message(RATE_EVENT)
    assert t.on_message({**RESULT, "total_cost_usd": 0.001})
    assert t.on_message(RESULT)                                   # cumulative per process: replaces
    t.new_process()                                               # a resumed session: added
    t.on_message(RESULT)
    data = json.loads(Path(path).read_text())
    assert data["cost_usd"] == pytest.approx(0.0045832)
    assert data["models"]["claude-haiku-5-5"]["input_tokens"] == 2 * (4 + 10140)
    assert data["cache_read_tokens"] == 2 * 25820
    assert data["limit"]["kind"] == "seven_day" and data["limit"]["used_percent"] == 31.0
    assert data["limit"]["resets_at"].startswith("2026-11-")
    out = messages.protocol_usage(data)
    assert set(out) == {"cost_usd", "input_tokens", "output_tokens", "cache_read_tokens", "models", "limit"}
    assert set(out["limit"]) == {"status", "kind", "resets_at", "used_percent"}
    assert messages.UsageTracker(path).totals()["cost_usd"] == pytest.approx(0.0045832)     # survives a restart


# ---- adw_report.py: reply, ask, wait, image, comment --file ---------------------------------

def test_report_reply_ask_wait(repo, monkeypatch):
    base = repo.root / "agents" / "r1"
    assert adw_report.main(["--adw-id", "r1", "reply", "m1", "Almost done"]) == 0
    assert messages.read_all(str(base / "outbox.jsonl"))[-1] == {**messages.read_all(str(base / "outbox.jsonl"))[-1],
                                                                 "type": "reply", "to": "m1", "text": "Almost done"}
    # ask: the answer arrives in the inbox while it waits
    import threading

    def answer_later():
        time.sleep(0.3)
        messages.append(str(base / "inbox.jsonl"), {"type": "answer", "ask": 1, "text": "Hide them"})

    threading.Thread(target=answer_later).start()
    assert adw_report.main(["--adw-id", "r1", "ask", "Show cancelled orders?", "--options", "Show,Hide",
                            "--timeout-min", "0.2"]) == 0
    ask = [e for e in messages.read_all(str(base / "outbox.jsonl")) if e["type"] == "ask"][0]
    assert ask["n"] == 1 and ask["options"] == ["Show", "Hide"]
    # no answer yet: the question stays open, and `ask --wait` picks up the answer, also one that came between calls
    out = str(base / "outbox.jsonl")
    assert adw_report.main(["--adw-id", "r1", "ask", "Second?", "--wait-min", "0.005"]) == 0
    assert not any(e["type"] == "ask_cancel" for e in messages.read_all(out))
    assert messages.ask_open(messages.read_all(out), messages.read_all(str(base / "inbox.jsonl")))
    messages.append(str(base / "inbox.jsonl"), {"type": "answer", "ask": 2, "text": "Yes"})
    assert adw_report.main(["--adw-id", "r1", "ask", "--wait", "2", "--wait-min", "0.005"]) == 0
    assert not messages.ask_open(messages.read_all(out), messages.read_all(str(base / "inbox.jsonl")))
    assert adw_report.main(["--adw-id", "r1", "ask", "--wait", "9"]) == 2
    # only with a timeout does the agent give up on it and decide
    assert adw_report.main(["--adw-id", "r1", "ask", "Third?", "--timeout-min", "0.005"]) == 0
    assert messages.read_all(out)[-1] == {**messages.read_all(out)[-1], "type": "ask_cancel", "n": 3}
    # wait: returns at once when not paused; blocks until resume when paused
    assert adw_report.main(["--adw-id", "r1", "wait"]) == 0
    messages.append(str(base / "inbox.jsonl"), {"type": "message", "id": "p", "mode": "pause", "text": "hold"})

    def resume_later():
        time.sleep(0.3)
        messages.append(str(base / "inbox.jsonl"), {"type": "message", "id": "r", "mode": "resume", "text": "go"})

    threading.Thread(target=resume_later).start()
    t = time.time()
    assert adw_report.main(["--adw-id", "r1", "wait", "--timeout-min", "0.2"]) == 0
    assert time.time() - t < 10


def test_report_image_and_comment_file(repo, monkeypatch, tmp_path, capsys):
    posted = []
    monkeypatch.setattr(adw_report, "post_comment", lambda adw_id, issue, text, agent="o": posted.append(text) or True)
    md = tmp_path / "plan.md"
    md.write_text("## Plan\n\n1. Model\n", encoding="utf-8")
    assert adw_report.main(["--adw-id", "i1", "--issue", "4", "comment", "--file", str(md)]) == 0
    assert posted == ["## Plan\n\n1. Model"]
    assert adw_report.main(["--adw-id", "i1", "comment"]) == 2                    # nothing to post
    url = "https://placehold.co/10x10/png"
    assert adw_report.main(["--adw-id", "i1", "image", "Orders, mobile", url]) == 0
    assert f"![Orders, mobile]({url})" in capsys.readouterr().out
    shot = tmp_path / "x.png"
    shot.write_bytes(b"\x89PNG")
    from adw_modules import image_upload
    monkeypatch.setattr(image_upload, "upload", lambda path, adw_id, cwd, logger=None: ("https://r2.example/x.png", "r2"))
    assert adw_report.main(["--adw-id", "i1", "image", "Orders, desktop", str(shot)]) == 0
    assert [e["url"] for e in adw_report.recorded_images("i1")] == [url, "https://r2.example/x.png"]
    section = adw_report.screenshots_section("i1", f"body with ![a]({url})")
    assert "## Screenshots" in section and "r2.example" in section and url not in section


def test_image_upload_falls_back_to_the_screenshot_branch(tmp_path, monkeypatch):
    from adw_modules import image_upload
    monkeypatch.delenv("CLOUDFLARE_R2_BUCKET_NAME", raising=False)
    calls = []
    monkeypatch.setattr(image_upload, "repo_slug", lambda cwd: "o/r")

    def fake_git(args, cwd, env=None, timeout=120):
        calls.append(args)
        out = {"hash-object": "blob1", "write-tree": "tree1", "commit-tree": "commit1"}.get(args[0], "")
        code = 1 if args[0] == "fetch" else 0                    # the branch doesn't exist yet: an orphan commit
        return types.SimpleNamespace(stdout=out + "\n", returncode=code)

    monkeypatch.setattr(image_upload, "_git", fake_git)
    url, how = image_upload.upload(str(tmp_path / "a.png"), "adw1", str(tmp_path))
    assert (url, how) == ("https://github.com/o/r/raw/adw-screenshots/adw1/a.png", "branch")
    assert ["read-tree", "--empty"] in calls and ["push", "--quiet", "origin", "commit1:refs/heads/adw-screenshots"] \
        in calls
    commit = next(c for c in calls if c[0] == "commit-tree")
    assert "-p" not in commit


# ---- the streaming orchestrator session --------------------------------------------------------

FAKE_CLAUDE = r'''
import json, os, sys, time
log = open(sys.argv[1], "a")
RESULT_FILE = sys.argv[2]
def out(m):
    print(json.dumps(m), flush=True)
def read():
    line = sys.stdin.readline()
    if line:
        log.write(line); log.flush()
    return json.loads(line) if line.strip() else None
def report(result):                                     # what `adw_report.py result` does, then the turn ends
    time.sleep(0.3)                                     # (the workflow has seen the task events by now)
    with open(RESULT_FILE + ".tmp", "w") as f:
        json.dump(result, f)
    os.replace(RESULT_FILE + ".tmp", RESULT_FILE)
out({"type": "system", "subtype": "init", "session_id": "sess-1"})
first = read()
out(RATE)
out({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Agent", "input": {}}]}})
out({"type": "system", "subtype": "task_started", "task_id": "t1", "description": "Orders API"})
if MODE == "early":                                     # reports while its subagent still runs: told to wait
    report({"status": "failed", "summary": "gave up"})
    nxt = read()
    out({**RESULT, "result": "waiting"})
elif MODE == "force":                                   # gives up on purpose: accepted with the subagent running
    report({"status": "failed", "summary": "gave up", "reason": "no way", "force": True})
elif MODE == "server":                                  # left a dev server running in the background
    import subprocess
    srv = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    open(RESULT_FILE + ".server", "w").write(str(srv.pid))
    report({"status": "pr_opened", "summary": "done", "pr_url": "https://github.com/o/r/pull/1", "force": True})
else:
    out({**RESULT, "total_cost_usd": 0.001})           # the turn ends while the subagent works: no final yet
    nxt = read()                                        # the forwarded message (or the nudge)
if MODE not in ("force", "server"):
    out({"type": "system", "subtype": "task_notification", "task_id": "t1", "status": "completed"})
    out({"type": "system", "subtype": "background_tasks_changed", "tasks": []})
    if MODE == "nudge":
        out({**RESULT, "total_cost_usd": 0.0015})       # ends again, nothing running: gets nudged
        nxt = read()
    report({"status": "pr_opened", "summary": "done", "pr_url": "https://github.com/o/r/pull/1"})
    out({**RESULT, "result": "Result recorded."})
while read() is not None:                               # stdin closed: exit
    pass
if MODE == "server":                                    # like claude: waits for its background command first
    srv.wait()
'''


def fake_claude(tmp_path, mode):
    path = tmp_path / f"fake_{mode}.py"
    path.write_text(f"RATE = {RATE_EVENT!r}\nRESULT = {json.dumps(RESULT)}\nMODE = {mode!r}\n"
                    .replace("false", "False").replace("true", "True") + FAKE_CLAUDE)
    return path


def run_fake(repo, mode, adw_id, **kw):
    tmp = repo.root
    stdin_log = tmp / f"stdin_{mode}.jsonl"
    result = tmp / "agents" / adw_id / "result.json"
    result.parent.mkdir(parents=True, exist_ok=True)
    out = orch.run_session([sys.executable, str(fake_claude(tmp, mode)), str(stdin_log), str(result)], str(tmp),
                           dict(os.environ), str(tmp / "o" / f"raw_{mode}.jsonl"), 60, kw.pop("on_session", lambda s: None),
                           first_message=kw.pop("first_message", "P"), poll=0.05, result_file=str(result),
                           report="REPORT", **kw)
    sent = [json.loads(ln) for ln in stdin_log.read_text().splitlines()] if stdin_log.exists() else []
    return out, sent, result


def test_session_streams_messages_in_and_usage_out(repo, monkeypatch):
    tmp = repo.root
    messages.append(str(tmp / "agents" / "s1" / "inbox.jsonl"),
                    {"type": "message", "id": "m1", "mode": "ask", "text": "How far?", "from": "Konrad"})
    messenger = orch.Messenger("s1", "REPORT")
    usage = messages.UsageTracker(str(tmp / "agents" / "s1" / "usage.json"))
    seen = []
    out, sent, result = run_fake(repo, "inbox", "s1", on_session=seen.append, first_message="THE PROMPT",
                                 messenger=messenger, usage=usage)
    assert not out["timed_out"] and out["returncode"] == 0 and seen[0] == "sess-1"
    # result.json with nothing running ends the session; the file stays for orchestrate() to read
    assert out["final"]["status"] == "pr_opened" and messages.read_result(str(result))["summary"] == "done"
    assert sent[0] == {"type": "user", "message": {"role": "user", "content": "THE PROMPT"}}
    assert sent[1]["priority"] == "next"
    assert sent[1]["message"]["content"].startswith("[Message from Konrad (ask), id m1]: How far?")
    data = json.loads((tmp / "agents" / "s1" / "usage.json").read_text())
    assert data["cost_usd"] == pytest.approx(0.0022916) and data["limit"]["status"] == "allowed"
    # a second messenger (a resumed workflow) doesn't forward m1 again
    assert orch.Messenger("s1", "REPORT").poll() == []


def test_session_nudges_a_turn_that_ends_without_a_result(repo, monkeypatch):
    tmp = repo.root
    monkeypatch.setattr(orch, "NUDGE_AFTER", 0.2)
    messages.append(str(tmp / "agents" / "s2" / "inbox.jsonl"), {"type": "message", "id": "m1", "mode": "amend",
                                                                  "text": "x"})
    out, sent, _ = run_fake(repo, "nudge", "s2", messenger=orch.Messenger("s2", "R"))
    assert out["final"]["status"] == "pr_opened"
    sent = [m["message"]["content"] for m in sent]
    assert sent[0] == "P" and "(amend)" in sent[1] and sent[2] == orch.NUDGE.replace("{report}", "REPORT")
    assert "REPORT result" in sent[2] and "JSON" not in sent[2]


def test_a_result_while_subagents_run_is_set_aside(repo):
    """The #37 failure: a result while background subagents still run must not end the session. It is removed,
    the orchestrator is told to wait for them (by name), and its later result, with nothing running, ends it."""
    out, sent, result = run_fake(repo, "early", "s4")
    assert not out["timed_out"] and out["returncode"] == 0
    wait = sent[1]
    assert wait["priority"] == "next" and "NOT recorded" in wait["message"]["content"]
    assert '"Orders API"' in wait["message"]["content"] and "--force" in wait["message"]["content"]
    assert out["final"]["status"] == "pr_opened"                    # the first ("failed") one never counted
    assert messages.read_result(str(result))["status"] == "pr_opened"


@pytest.mark.skipif(sys.platform == "win32", reason="process groups")
def test_a_dev_server_left_running_does_not_keep_the_session_open(repo, monkeypatch):
    """#43: the orchestrator started the dev servers in the background; claude waited for them after the result,
    and the workflow never ended. Now the session's process group is stopped once the result is in."""
    monkeypatch.setattr(orch, "EXIT_GRACE", 1)
    t = time.time()
    out, _, result = run_fake(repo, "server", "s6")
    assert out["final"]["status"] == "pr_opened" and time.time() - t < 30
    pid = int(open(str(result) + ".server").read())
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("the background server is still running")


def test_a_forced_result_ends_the_session_with_subagents_running(repo):
    out, sent, _ = run_fake(repo, "force", "s5")
    assert out["final"] == {"status": "failed", "summary": "gave up", "reason": "no way", "force": True}
    assert len(sent) == 1                                             # just the prompt: no wait message


def test_orchestrate_clears_a_stale_result_and_resumes_past_a_forced_one(repo, monkeypatch):
    """Resume of a run whose last session ended on the StructuredOutput "failed" the CLI forced (--json-schema):
    same session, the resume prompt says it was a bug; an old result.json never ends the new session."""
    adw = "a37"
    odir = repo.root / "agents" / adw / "orchestrator"
    odir.mkdir(parents=True)
    old = [{"type": "system", "subtype": "init", "session_id": "sess-37"},
           {"type": "system", "subtype": "task_started", "task_id": "t1", "description": "Investigate revenue"},
           {"type": "result", "subtype": "success", "is_error": False, "session_id": "sess-37"},
           {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text":
               "[structured-output-enforce] You MUST call the StructuredOutput tool to complete this request."}]}},
           {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "StructuredOutput",
                                                          "input": {"status": "failed", "summary": "x"}}]}}]
    (odir / "raw_output-20261104-161047.jsonl").write_text("\n".join(json.dumps(m) for m in old) + "\n")
    (repo.root / "agents" / adw / "result.json").write_text(json.dumps({"status": "failed", "summary": "stale"}))
    wt = repo.root / "trees" / adw
    wt.mkdir(parents=True)
    calls = []

    def fake_run(cmd, cwd, env, out_path, timeout_s, on_session, **kw):
        calls.append({"cmd": cmd, "first": kw["first_message"], "stale": os.path.exists(kw["result_file"])})
        assert kw["result_file"] == orch.result_path(adw)
        with open(kw["result_file"], "w") as f:
            json.dump({"status": "pr_opened", "summary": "delivered", "pr_url": "https://github.com/o/r/pull/5"}, f)
        return {"result": None, "final": {"status": "pr_opened"}, "timed_out": False, "returncode": 0, "stderr": ""}

    monkeypatch.setattr(orch, "run_session", fake_run)
    monkeypatch.setattr(orch.resources, "enabled", lambda: False)

    class State(dict):
        def update(self, **kw):
            super().update(kw)

        def save(self, *_):
            pass

    state = State(adw_id=adw, issue_number="37", worktree_path=str(wt), branch_name="b", issue_class="/feature",
                  backend_port=9101, frontend_port=9201, orchestrator_session_id="sess-37")
    log = types.SimpleNamespace(info=lambda *a: None, warning=lambda *a: None)
    outcome = orch.orchestrate(state, types.SimpleNamespace(title="T", body="B"), log, fresh=False)
    assert outcome == {"status": "pr_opened", "summary": "delivered", "pr_url": "https://github.com/o/r/pull/5"}
    call = calls[0]
    assert not call["stale"] and call["cmd"][-2:] == ["--resume", "sess-37"] and "--json-schema" not in call["cmd"]
    assert call["first"].startswith(orch.FORCED_RESULT_NOTE) and "forced" in call["first"]
    assert "continue planning from what the investigations found" in call["first"].lower()
    assert "{report}" not in call["first"] and "result ..." in call["first"]
    # a session that gave up on its own (nothing running) resumes with the plain resume prompt
    assert orch.forced_result_in(str(odir / "raw_output-20261104-161047.jsonl"))
    plain = [old[0], {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "StructuredOutput", "input": {"status": "failed", "summary": "x"}}]}}]
    (odir / "raw_output-20261105-090000.jsonl").write_text("\n".join(json.dumps(m) for m in plain) + "\n")
    calls.clear()
    orch.orchestrate(state, types.SimpleNamespace(title="T", body="B"), log, fresh=False)
    assert not calls[0]["first"].startswith(orch.FORCED_RESULT_NOTE) and "interrupted" in calls[0]["first"]


def test_paused_time_does_not_count_and_late_answers_are_forwarded(repo):
    base = repo.root / "agents" / "s3"
    messages.append(str(base / "outbox.jsonl"), {"type": "ask", "n": 1, "question": "Q?"})
    messages.append(str(base / "outbox.jsonl"), {"type": "ask_cancel", "n": 1})
    messages.append(str(base / "inbox.jsonl"), {"type": "answer", "ask": 1, "text": "Late"})
    messages.append(str(base / "inbox.jsonl"), {"type": "message", "id": "p", "mode": "pause", "text": ""})
    m = orch.Messenger("s3", "R")
    assert not m.asking()
    messages.append(str(base / "outbox.jsonl"), {"type": "ask", "n": 2, "question": "Open?"})
    assert m.asking()                                  # an open question: its time doesn't count either
    texts = m.poll()
    assert "Late answer" in texts[0] and "Q?" in texts[0] and "(pause)" in texts[1] and m.paused
    # a message the session never took (usage-limit wait, or the workflow ended) gets one reply
    messages.append(str(base / "inbox.jsonl"), {"type": "message", "id": "late", "mode": "ask", "text": "?"})
    m.reply_busy("Claude usage limit reached until 13:05.")
    m.reply_busy("Claude usage limit reached until 13:05.")
    replies = [e for e in messages.read_all(str(base / "outbox.jsonl")) if e["type"] == "reply"]
    assert len(replies) == 1 and replies[0]["to"] == "late" and "13:05" in replies[0]["text"]


def test_limit_wait_until_the_reset(monkeypatch):
    from datetime import datetime, timedelta
    at = (datetime.now() + timedelta(minutes=30)).replace(microsecond=0)
    usage = types.SimpleNamespace(data={"limit": {"status": "rejected", "resets_at": at.isoformat()}})
    secs, hhmm = orch.limit_wait(usage, "Claude AI usage limit reached")
    assert 30 * 60 < secs <= 31 * 60 + 5 and hhmm == at.strftime("%H:%M")
    assert orch.limit_wait(None, "overloaded") == (orch.LIMIT_WAIT_SECONDS, None)


# ---- the trigger: messages, questions, usage, screenshots ------------------------------------------

def workflow_run(repo, *groups, simulate=False):
    run = ae.Run(repo.root / "agents" / "ore" / "rm")
    run.dir.mkdir(parents=True, exist_ok=True)
    run.s = {"run_id": "rm", "dry_run": False, "simulate": simulate, "groups": list(groups), "phase": "workflows",
             "stages": {}}
    return run


def test_trigger_delivers_messages_to_the_parts(repo):
    a = {"title": "Orders", "status": "running", "adw_id": "a1", "issue_number": "7"}
    b = {"title": "Invoices", "status": "queued", "issue_number": "8"}
    c = {"title": "Footer", "status": "done", "adw_id": "c1", "pr_url": "https://github.com/o/r/pull/2"}
    run = workflow_run(repo, a, b, c)
    ae.IO.messages = [{"type": "message", "id": "m1", "part": "Orders", "text": "Pause", "mode": "pause"},
                      {"type": "message", "id": "m2", "part": None, "text": "Use EUR", "mode": "amend",
                       "from": "Konrad"},
                      {"type": "message", "id": "m3", "part": "Footer", "text": "?", "mode": "ask"},
                      {"type": "message", "id": "m4", "part": "Nope", "text": "?", "mode": "ask"}]
    ae.handle_messages(run)
    inbox = messages.read_all(str(repo.root / "agents" / "a1" / "inbox.jsonl"))
    assert [(e["id"], e["mode"]) for e in inbox] == [("m1", "pause"), ("m2", "amend")]
    assert inbox[1]["from"] == "Konrad" and not a["paused"]
    assert b["pending_messages"][0]["id"] == "m2"
    replies = {m["to"]: m for m in repo.sent if m["type"] == "reply"}
    assert "finished" in replies["m3"]["text"] and replies["m3"]["part"] == "Footer"
    assert "no workflow called" in replies["m4"]["text"]
    b["adw_id"] = "b1"
    ae.flush_pending(b)
    assert messages.read_all(str(repo.root / "agents" / "b1" / "inbox.jsonl"))[0]["id"] == "m2"


def test_trigger_relays_replies_and_one_question_at_a_time(repo):
    a = {"title": "Orders", "status": "running", "adw_id": "a1", "issue_number": "7"}
    b = {"title": "Invoices", "status": "running", "adw_id": "b1", "issue_number": "8"}
    run = workflow_run(repo, a, b)
    messages.append(str(repo.root / "agents" / "a1" / "outbox.jsonl"), {"type": "reply", "to": "m1", "text": "50%"})
    messages.append(str(repo.root / "agents" / "a1" / "outbox.jsonl"),
                    {"type": "ask", "n": 1, "question": "EUR or USD?", "options": ["EUR", "USD"]})
    messages.append(str(repo.root / "agents" / "b1" / "outbox.jsonl"), {"type": "ask", "n": 1, "question": "Why?"})
    for g in (a, b):
        ae.poll_outbox(run, g)
    ae.poll_asks(run)
    assert {"type": "reply", "to": "m1", "text": "50%", "part": "Orders"} in repo.sent
    asks = [m for m in repo.sent if m["type"] == "input_request"]
    assert asks == [{"type": "input_request", "id": "ask-7-1", "prompt": "Orders: EUR or USD?", "kind": "choice",
                     "options": ["EUR", "USD"]}]
    parts = {p["key"]: p for p in ae.parts(run)}
    assert parts["Orders"]["status"] == "input" and "EUR or USD?" in parts["Orders"]["message"]
    ae.poll_asks(run)
    assert len([m for m in repo.sent if m["type"] == "input_request"]) == 1         # still one open
    ae.IO.answers["ask-7-1"] = "EUR"
    ae.poll_asks(run)
    assert messages.read_all(str(repo.root / "agents" / "a1" / "inbox.jsonl"))[-1]["text"] == "EUR"
    nxt = [m for m in repo.sent if m["type"] == "input_request"][-1]
    assert nxt["id"] == "ask-8-1" and nxt["kind"] == "text"


def test_parts_carry_usage_images_and_the_limit_wait(repo):
    a = {"title": "Orders", "status": "running", "adw_id": "a1", "issue_number": "7",
         "usage_before": {"cost_usd": 1.0, "input_tokens": 10, "output_tokens": 1, "cache_read_tokens": 0,
                          "models": {"claude-opus-5-5": {"cost_usd": 1.0, "input_tokens": 10, "output_tokens": 1}}}}
    run = workflow_run(repo, a)
    t = messages.UsageTracker(str(repo.root / "agents" / "a1" / "usage.json"))
    t.new_process()
    t.on_message(RESULT)
    t.on_message(RATE_EVENT)
    t.set_waiting("2099-01-01T13:05:00")
    messages.append(str(repo.root / "agents" / "a1" / "images.jsonl"), {"label": "Orders", "url": "https://x/y.png"})
    messages.append(str(repo.root / "agents" / "a1" / "images.jsonl"), {"label": "Bad", "url": "file:///etc"})
    part = ae.parts(run)[0]
    assert part["usage"]["cost_usd"] == pytest.approx(1.0022916)
    assert set(part["usage"]["models"]) == {"claude-opus-5-5", "claude-haiku-5-5"}
    assert part["usage"]["limit"]["kind"] == "seven_day"
    assert part["images"] == [{"label": "Orders", "url": "https://x/y.png"}]
    assert part["message"] == "Claude usage limit reached until 13:05"
    run.s["usage"] = {"cost_usd": 0.5}
    assert ae.run_usage(run, [part])["cost_usd"] == pytest.approx(1.5022916)


def test_resume_continues_an_orchestrated_workflow_with_the_same_adw(repo, monkeypatch):
    wt = repo.root / "trees" / "a1"
    wt.mkdir(parents=True)
    (repo.root / "agents" / "a1").mkdir(parents=True)
    (repo.root / "agents" / "a1" / "adw_state.json").write_text(json.dumps(
        {"adw_id": "a1", "worktree_path": str(wt), "orchestrator_session_id": "sess-9"}))
    (repo.root / "agents" / "b1").mkdir(parents=True)
    (repo.root / "agents" / "b1" / "adw_state.json").write_text(json.dumps({"adw_id": "b1"}))     # setup failed
    a = {"title": "Orders", "status": "failed", "adw_id": "a1", "issue_number": "7", "workflow": "orchestrated",
         "pid": None, "outbox_offsets": {"a1": 40}}
    b = {"title": "Invoices", "status": "failed", "adw_id": "b1", "issue_number": "8", "workflow": "orchestrated"}
    c = {"title": "Footer", "status": "running", "adw_id": "c1", "issue_number": "9", "workflow": "orchestrated",
         "pid": 999999}                                     # interrupted: its process is gone
    run = workflow_run(repo, a, b, c)
    cleaned = []
    monkeypatch.setattr(ae, "clean_group", lambda run_, g, on_github: cleaned.append(g["title"]) or [])
    monkeypatch.setattr(ae, "alive", lambda g: (False, None))
    resources.acquire("a1", pid=999999)                    # what the stopped workflow still held
    assert ae.retry_failed(run) == 3
    assert a["status"] == "queued" and a["next_adw_id"] == "a1" and a["continue_adw"] == "a1"
    assert a["outbox_offsets"] == {"a1": 40} and "Orders" not in cleaned
    assert resources.get("a1") is None                     # released; the workflow leases again
    assert cleaned == ["Invoices", "Footer"] and "next_adw_id" not in b and c["status"] == "queued"
    # the slot is taken again for the same adw_id, and its state (worktree, session) is kept for the ADW
    assert ae.claim_slot(run, a) == "a1" and resources.holds_slot(resources.WORKFLOW, "a1")
    saved = {}

    class State:
        def __init__(self, adw_id, data=None):
            self.data = dict(data or {"adw_id": adw_id})

        @classmethod
        def load(cls, adw_id, logger=None):
            return cls(adw_id, json.loads((repo.root / "agents" / adw_id / "adw_state.json").read_text()))

        def update(self, **kw):
            self.data.update(kw)

        def save(self, *_):
            saved.update(self.data)

    class Proc:
        pid = 4321

    monkeypatch.setattr(ae, "ADWState", State)
    monkeypatch.setattr(ae.subprocess, "Popen", lambda cmd, **kw: Proc())
    monkeypatch.setattr(ae.os, "getpgid", lambda pid: pid, raising=False)
    a["workflow"] = "orchestrated"
    ae.start_adw(run, a, a.pop("next_adw_id"))
    assert saved["orchestrator_session_id"] == "sess-9" and saved["worktree_path"] == str(wt)
    assert a["adw_id"] == "a1" and a["message"] == "Continuing"
    # a requeue (no free ports when it started) keeps continuing the same ADW
    ae.requeue(run, a, "no ports")
    assert a["next_adw_id"] == "a1"


def test_simulate_talks_with_ore(tmp_path):
    """--simulate end to end with messages: an ask is answered, pause holds the workflow until resume, an amend to
    the whole run reaches every workflow, the orchestrator's question is asked in Ore and answered, and the parts
    carry screenshots and usage. Every message passes Ore's checker (when Ore is installed)."""
    from adw_tests import ore_harness
    repo = tmp_path / "repo"
    shutil.copytree(ADWS, repo / "adws", ignore=shutil.ignore_patterns("__pycache__", "agents", "trees"))
    env = {"ORE_SIM_SPEED": "10", "PYTHONPATH": os.environ.get("PYTHONPATH", "")}
    code, msgs, err = ore_harness.run([str(repo / "adws" / "adw_triggers" / "trigger_ore.py"), "--simulate"],
                                      env=env, timeout=300, talk=True)
    assert code == 0, err[-2000:]
    sent = [m for m in msgs if m["type"] == "message"]
    replies = [m for m in msgs if m["type"] == "reply"]
    assert [m["mode"] for m in sent] == ["ask", "pause", "resume", "amend"]
    for m in sent:
        assert any(r["to"] == m["id"] for r in replies), m
    assert len([r for r in replies if r["to"] == "m4"]) == 2                 # the amend went to both workflows
    asks = [m for m in msgs if m["type"] == "input_request" and m["id"].startswith("ask-")]
    assert len(asks) == 2 and all(a["kind"] == "choice" for a in asks)
    statuses = [m for m in msgs if m["type"] == "status"]
    assert all(s.get("accepts") == ["message", "follow_up", "withdraw", "replan", "files"] for s in statuses)
    assert [s["phase"] for s in statuses][0] == "planning" and statuses[-1]["phase"] == "building"
    assert all(s.get("queries") == list(ae.QUERIES) for s in statuses)
    assert any(p["status"] == "input" for s in statuses for p in s.get("parts") or [])
    last = statuses[-1]
    assert sorted(i for p in last["parts"] for i in p["items"]) == ["1", "2", "3"]   # every sample item, once
    assert last["usage"]["cost_usd"] > 0 and last["usage"]["models"]
    for part in last["parts"]:
        assert part["status"] == "done" and len(part["images"]) == 2
        assert all(i["url"].startswith("https://placehold.co/") for i in part["images"])
        assert part["usage"]["limit"]["kind"] == "five_hour"
        assert {s["key"]: s for s in part["steps"]}["screens"]["status"] == "done"
    progress = list((repo / "agents" / "progress").glob("issue-sim-*.jsonl"))
    texts = [json.loads(ln)["comment"] for p in progress for ln in p.read_text(encoding="utf-8").splitlines()]
    assert any("**Packages**" in t for t in texts) and any("Answer received: Show them" in t for t in texts)
    snap = json.loads(Path(resources.registry_path()).read_text(encoding="utf-8"))
    assert not snap["leases"] and not snap["slots"].get("workflow")
    try:
        from ore.protocol import check_message
    except ImportError:
        check_message = None
    for m in msgs:
        if check_message and m["type"] != "message":
            assert check_message(m) == [], m


# ---- follow-ups -------------------------------------------------------------------------------

def finished_orchestrated(repo, adw="a1", session="sess-9"):
    wt = repo.root / "trees" / adw
    wt.mkdir(parents=True, exist_ok=True)
    (repo.root / "agents" / adw).mkdir(parents=True, exist_ok=True)
    (repo.root / "agents" / adw / "adw_state.json").write_text(json.dumps(
        {"adw_id": adw, "worktree_path": str(wt), "orchestrator_session_id": session}))
    return {"title": "Orders", "status": "done", "adw_id": adw, "issue_number": "7", "workflow": "orchestrated",
            "pr_url": "https://github.com/o/r/pull/12", "progress": 1.0, "completed": True, "ended_at": 1.0,
            "pid": 4321, "offset": 99, "check": {"state": "done", "result": "green"}, "log": [{"text": "PR"}]}


def test_a_follow_up_continues_a_finished_workflow_with_the_same_adw(repo, monkeypatch):
    a = finished_orchestrated(repo)
    other = {"title": "Footer", "status": "failed", "adw_id": "b1", "issue_number": "8", "workflow": "orchestrated"}
    run = workflow_run(repo, a, other)
    run.s["phase"] = "done"
    ae.IO.messages = [{"type": "message", "id": "m9", "part": "Orders", "mode": "follow_up", "from": "Konrad",
                       "text": "Make the pre-fill atomic"}]
    ae.handle_messages(run)
    assert a["status"] == "queued" and a["next_adw_id"] == a["continue_adw"] == "a1" and a["follow_ups"] == 1
    assert a["follow_up"] == {"n": 1, "id": "m9", "text": "Make the pre-fill atomic", "from": "Konrad"}
    assert a["pr_url"].endswith("/12") and a["log"]                       # the PR and its history stay
    assert not {"completed", "ended_at", "pid", "offset", "check"} & set(a)
    assert run.s["phase"] == "workflows" and other["status"] == "failed"  # only this workflow runs again
    reply = next(m for m in repo.sent if m["type"] == "reply" and m["to"] == "m9")
    assert reply["text"].startswith("Follow-up 1 queued")
    # started: the same ADW, with the request handed over and --follow-up on the command line
    launched = {}

    class Proc:
        pid = 777

    def popen(cmd, **kw):
        launched["cmd"] = cmd
        return Proc()

    monkeypatch.setattr(ae.subprocess, "Popen", popen)
    monkeypatch.setattr(ae.os, "getpgid", lambda pid: pid, raising=False)
    monkeypatch.setattr(ae, "ADWState", types.SimpleNamespace(
        load=lambda adw_id, logger=None: types.SimpleNamespace(update=lambda **kw: None, save=lambda *x: None)))
    ae.start_adw(run, a, a.pop("next_adw_id"))
    assert launched["cmd"][-3:] == ["7", "a1", "--follow-up"] and a["round"] == 1 and "follow_up" not in a
    assert a["message"] == "Follow-up 1: Make the pre-fill atomic"
    handed = json.loads((repo.root / "agents" / "a1" / messages.FOLLOW_UP).read_text())
    assert handed["text"] == "Make the pre-fill atomic" and handed["n"] == 1
    # its PR predates the round: a round that stops with an error fails; the old PR doesn't make it "done"
    monkeypatch.setattr(ae, "alive", lambda g: (False, 1))

    def fail(message, exit_code=1):
        raise SystemExit(message)

    monkeypatch.setattr(ae, "error", fail)
    with pytest.raises(SystemExit):
        ae.workflows(run)
    assert a["status"] == "failed"


def test_follow_ups_that_cant_run_say_why(repo):
    gone = dict(finished_orchestrated(repo, "a2", session=None), title="Invoices")     # no session to resume
    failed = dict(finished_orchestrated(repo, "a3"), title="Footer", status="failed")
    running = {"title": "Orders", "status": "running", "adw_id": "a4", "issue_number": "9", "workflow": "orchestrated"}
    run = workflow_run(repo, gone, failed, running)
    for mid, part in (("m1", "Invoices"), ("m2", "Footer"), ("m3", "Orders"), ("m4", None), ("m5", "Nope")):
        assert ae.follow_up(run, {"id": mid, "part": part, "text": "More"}) is (mid == "m3")
    replies = {m["to"]: m["text"] for m in repo.sent if m["type"] == "reply"}
    assert "can't be followed up" in replies["m1"] and gone["status"] == "done"
    assert "Resume" in replies["m2"] and "Say which workflow" in replies["m4"] and "no workflow" in replies["m5"]
    # a workflow still running gets it as a change
    assert messages.read_all(str(repo.root / "agents" / "a4" / "inbox.jsonl"))[0]["mode"] == "amend"


def test_the_follow_up_argument():
    import base64
    raw = base64.urlsafe_b64encode(json.dumps({"id": "m1", "part": "Orders", "text": "Do 'it' & more"}).encode())
    rest, msg = ae.follow_up_arg(["--resume", "/r", "--follow-up", raw.decode().rstrip("=")])
    assert rest == ["--resume", "/r"] and msg["text"] == "Do 'it' & more"
    assert ae.follow_up_arg(["--resume", "/r"]) == (["--resume", "/r"], None)
    assert ae.follow_up_arg(["--resume", "/r", "--follow-up", "%%%"])[1] == {}


def test_a_follow_up_round_starts_the_steps_again(repo):
    adw = "a5"
    steps.route(adw, "feature", "dynamic", "Orchestrated SDLC")
    for key, st in (("setup", "done"), ("plan", "done"), ("review", "done"), ("pr", "done")):
        steps.record(adw, key, st)
    steps.record(adw, "orders", "done", parent="work")
    steps.new_round(adw, 1, note="Make the pre-fill atomic")
    assert steps.last_status(adw, "review") is None and steps.last_status(adw, "setup") == "done"
    assert steps.last_status(adw, "orders", parent="work") is None
    steps.record(adw, "setup", "running")
    steps.record(adw, "setup", "done")
    steps.record(adw, "review", "running")
    assert steps.close_open(adw, "Stopped") == 1 and steps.last_status(adw, "review") == "failed"
    built, _route = ae.build_steps(ae.read_steps(adw))
    status = {n["key"]: n["status"] for n in built}
    assert status["setup"] == "done" and status["plan"] == "pending" and status["review"] == "failed"
    assert status["pr"] == "pending" and not next(n for n in built if n["key"] == "work")["steps"]
    assert steps.rounds(steps.read(adw)) == 1


def test_orchestrate_a_follow_up_resumes_the_session_with_the_request(repo, monkeypatch):
    adw = "a6"
    wt = repo.root / "trees" / adw
    wt.mkdir(parents=True)
    (repo.root / "agents" / adw / "orchestrator").mkdir(parents=True)
    (repo.root / "agents" / adw / "orchestrator" / "pr_url.txt").write_text("https://github.com/o/r/pull/12\n")
    calls = []

    def fake_run(cmd, cwd, env, out_path, timeout_s, on_session, **kw):
        calls.append({"cmd": cmd, "first": kw["first_message"], "env": env})
        with open(kw["result_file"], "w") as f:
            json.dump({"status": "pr_opened", "summary": "atomic now", "pr_url": "https://github.com/o/r/pull/12"}, f)
        return {"result": None, "final": {"status": "pr_opened"}, "timed_out": False, "returncode": 0, "stderr": ""}

    monkeypatch.setattr(orch, "run_session", fake_run)
    monkeypatch.setattr(orch.resources, "enabled", lambda: False)

    class State(dict):
        def update(self, **kw):
            super().update(kw)

        def save(self, *_):
            pass

    state = State(adw_id=adw, issue_number="7", worktree_path=str(wt), branch_name="b", issue_class="/feature",
                  backend_port=9101, frontend_port=9201, orchestrator_session_id="sess-6")
    log = types.SimpleNamespace(info=lambda *a: None, warning=lambda *a: None)
    follow = {"n": 2, "text": "Make the pre-fill atomic {and} keep $HOME", "from": "Konrad"}
    orch.orchestrate(state, types.SimpleNamespace(title="T", body="B"), log, fresh=False, follow_up=follow)
    first = calls[0]["first"]
    assert calls[0]["cmd"][-2:] == ["--resume", "sess-6"]
    assert "CLAUDE_CODE_RESUME_INTERRUPTED_TURN" not in calls[0]["env"]      # the session finished: nothing cut off
    assert first.startswith("Follow-up 2 from Konrad") and "Make the pre-fill atomic {and} keep $HOME" in first
    assert "https://github.com/o/r/pull/12" in first and "## Follow-up 2" in first and "workflow_report.md" in first
    assert "{report}" not in first and "{n}" not in first
    # the full check is the orchestrator's call: run it, or record the step as skipped and say why
    assert "check` skipped" not in first and "step check skipped" in first and "full check ran and why" in first
    # without a session to resume, a fresh one gets the instructions and the request
    calls.clear()
    state["orchestrator_session_id"] = None
    orch.orchestrate(state, types.SimpleNamespace(title="T", body="B"), log, fresh=False, follow_up=follow)
    assert "--resume" not in calls[0]["cmd"] and "## Follow-up\n\nFollow-up 2" in calls[0]["first"]
    (repo.root / "agents" / adw / messages.FOLLOW_UP).write_text(json.dumps(follow))
    assert orch.read_follow_up(adw)["n"] == 2 and orch.read_follow_up("nope") is None


def test_a_follow_ups_report_is_posted_again(repo, monkeypatch):
    posted, comments = [], []

    def fake(cmd, **kw):
        if cmd[:3] == ["gh", "pr", "view"]:
            return types.SimpleNamespace(stdout="\n".join(comments), returncode=0)
        posted.append(cmd[-1])
        comments.append(cmd[-1])
        return types.SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(adw_report.subprocess, "run", fake)
    url = "https://github.com/o/r/pull/12"
    adw_report.save_report("a7", "## Summary\nFirst.", url)
    adw_report.save_report("a7", "## Summary\nFirst.", url)               # a resumed session reports again
    adw_report.save_report("a7", "## Follow-up 1\nAtomic.\n\n## Summary\nFirst.", url)
    assert len(posted) == 2 and "## Workflow report\n" in posted[0] and "Workflow report (updated)" in posted[1]
