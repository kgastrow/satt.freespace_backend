"""What a run of adw_orchestrated_sdlc_iso.py records, for dry runs (no Claude, no GitHub) and tests.

One list, used by `adw_orchestrated_sdlc_iso.py --dry-run`, the Ore trigger's --dry-run and its --simulate
(with DELAYS for realistic timing, events_for() for each workflow's own PR link and leased ports), so Ore's flow
for this workflow can be tried offline. Each entry is
(step event or None, progress comment or None). It shows the written plan (posted as a comment), three work
packages, two of them in parallel, checks on the changed code that fail once, screenshots of the changed screens,
a review round with blockers followed by a new round that passes, and the batch's full check. --simulate also asks the user one question
after the plan (ASK), shows the screenshots (IMAGES) and usage numbers (usage_at()).
"""

WORKFLOW = "Orchestrated SDLC"
PR_URL = "https://github.com/example/repo/pull/3"
PLAN_COMMENT = """Plan (specs/orchestrated/issue-<n>-<adw_id>.md)

**Approach.** Add an order status to the model, expose it in the orders API and show it on the orders page.

**Packages**
1. Order model + migration (`models/order.py`, migration; adw-implementer)
2. Orders API, after 1 (`api/v1/orders.py`; adw-implementer)
3. Orders page, after 1, in parallel with 2 (`OrdersPage.tsx`, locales; adw-implementer)

**Test plan.** Targeted pytest per package, vitest for the page, the checks on the changed code; the full suites
once at the end (the batch's full check); screenshots of /orders.

**Risks.** Existing orders need a default status (the migration sets it)."""
# --simulate: the question the simulated orchestrator asks after the plan, and the screenshots it reports
ASK = {"question": "Should cancelled orders be shown on the orders page?", "options": ["Show them", "Hide them"]}
IMAGES = [{"label": "Orders page, desktop", "url": "https://placehold.co/1440x900/png?text=Orders+page+desktop"},
          {"label": "Orders page, mobile", "url": "https://placehold.co/390x844/png?text=Orders+page+mobile"}]

EVENTS = [
    ({"key": "route", "status": "running", "label": "Route"}, None),
    ({"key": "route", "status": "done", "label": "Route", "note": "feature, dynamic", "type": "feature",
      "complexity": "dynamic", "workflow": WORKFLOW}, "Routing decision: /feature, Orchestrated SDLC"),
    ({"key": "setup", "status": "running", "label": "Setup"}, "Starting Orchestrated SDLC workflow"),
    ({"key": "setup", "status": "done", "label": "Setup",
      "note": "venv cloned from main checkout; node_modules cloned from main checkout; app on :9103/:9203"}, None),
    ({"key": "plan", "status": "running", "label": "Plan"}, "Orchestrator is planning the work"),
    ({"key": "work", "status": "planned", "label": "Work",
      "phases": [{"id": "model", "name": "Order model + migration"},
                 {"id": "api", "name": "Orders API", "after": ["model"]},
                 {"id": "ui", "name": "Orders page", "after": ["model"]}]}, None),
    ({"key": "plan", "status": "done", "label": "Plan", "note": "3 packages"}, PLAN_COMMENT),
    ({"key": "model", "parent": "work", "label": "Order model + migration", "status": "running"}, None),
    ({"key": "model", "parent": "work", "label": "Order model + migration", "status": "done",
      "note": "models/order.py, migration, 6 tests"}, None),
    ({"key": "api", "parent": "work", "label": "Orders API", "status": "running"}, None),
    ({"key": "ui", "parent": "work", "label": "Orders page", "status": "running"}, None),
    ({"key": "ui", "parent": "work", "label": "Orders page", "status": "done", "note": "OrdersPage.tsx, 4 tests"}, None),
    ({"key": "api", "parent": "work", "label": "Orders API", "status": "done", "note": "api/v1/orders.py, 11 tests"},
     None),
    ({"key": "integrate", "status": "running", "label": "Checks", "note": "Run 1: checks on the changed code"},
     None),
    ({"key": "integrate", "status": "failed", "label": "Checks",
      "note": "Run 1: build ok; lint ok; backend FAILED (1 failed, 36 passed (4 test files)); frontend ok (21 passed)"},
     None),
    ({"key": "integrate", "status": "running", "label": "Checks", "note": "Run 2: checks on the changed code"},
     None),
    ({"key": "integrate", "status": "done", "label": "Checks",
      "note": "Run 2: build ok; lint ok; backend ok (37 passed (4 test files)); frontend ok (21 passed)"}, None),
    ({"key": "screens", "status": "running", "label": "Screens"}, None),
    ({"key": "screens", "status": "done", "label": "Screens", "note": "2 screenshots, no visible problems"},
     "Screenshots of the changed screens: Orders page (desktop, mobile)"),
    ({"key": "review", "status": "running", "label": "Review", "note": "Round 1"}, None),
    ({"key": "review", "status": "failed", "label": "Review",
      "note": "Round 1: 2 blockers: list endpoint misses organization_id filter"},
     "Review round 1: 2 blockers (tenant filter on list endpoint, missing i18n key)"),
    ({"key": "integrate", "status": "running", "label": "Checks", "note": "Run 3: checks on the changed code"},
     None),
    ({"key": "integrate", "status": "done", "label": "Checks", "note": "Run 3: build ok; lint ok; backend ok; frontend ok"},
     None),
    ({"key": "review", "status": "running", "label": "Review", "note": "Round 2"}, None),
    ({"key": "review", "status": "done", "label": "Review", "note": "Round 2: passed, 1 warning"},
     "Review round 2: passed"),
    ({"key": "docs", "status": "running", "label": "Docs"}, None),
    ({"key": "docs", "status": "done", "label": "Docs", "note": "app_docs/orders.md"}, None),
    ({"key": "check", "status": "running", "label": "Full check", "note": "Check 1: waiting for the batch's full check"},
     None),
    ({"key": "check", "status": "running", "label": "Full check",
      "note": "Running the full suites: build, backend, frontend, lint with 7 workers"}, None),
    ({"key": "check", "status": "done", "label": "Full check", "note": "Green"}, None),
    ({"key": "pr", "status": "running", "label": "Pull request"}, None),
    ({"key": "pr", "status": "done", "label": "Pull request", "note": f"PR #3: {PR_URL}"},
     f"Pull request created: {PR_URL}"),
    (None, f"Orchestrated SDLC workflow completed: {PR_URL}"),
]

# Seconds before each event in a simulated run (trigger_ore.py --simulate): about 2.5 minutes per workflow, the
# packages and the suites taking longest, as in a real run (only much shorter).
DELAYS = [0, 3, 2, 10, 2, 8, 1, 1, 18, 1, 1, 16, 7, 2, 6, 3, 6, 1, 8, 2, 11, 3, 6, 2, 9, 1, 5, 2, 4, 12, 1, 4, 1]
assert len(DELAYS) == len(EVENTS)
ASK_AT = next(i for i, (e, _) in enumerate(EVENTS) if e and e["key"] == "plan" and e["status"] == "done") + 1
SCREENS_DONE = next(i for i, (e, _) in enumerate(EVENTS) if e and e["key"] == "screens" and e["status"] == "done")


def usage_at(done: int, index: int = 0) -> dict:
    """Plausible usage after `done` events of workflow `index` (protocol shape): an Opus orchestrator, Sonnet
    implementers, a Haiku investigator; the five-hour limit filling up."""
    from datetime import datetime, timedelta
    f = done / len(EVENTS)
    scale = 1 + 0.2 * index
    models = {"claude-opus-5-5": (2.10, 380_000, 41_000), "claude-sonnet-5-5": (0.95, 520_000, 63_000),
              "claude-haiku-5-5": (0.04, 90_000, 6_000)}
    out = {"models": {}, "cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
    for name, (cost, tin, tout) in models.items():
        m = {"cost_usd": round(cost * f * scale, 4), "input_tokens": int(tin * f * scale),
             "output_tokens": int(tout * f * scale)}
        out["models"][name] = m
        out["cost_usd"] = round(out["cost_usd"] + m["cost_usd"], 4)
        out["input_tokens"] += m["input_tokens"]
        out["output_tokens"] += m["output_tokens"]
    out["cache_read_tokens"] = int(out["input_tokens"] * 6)
    resets = (datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=3))
    out["limit"] = {"status": "allowed", "kind": "five_hour", "resets_at": resets.isoformat(timespec="seconds"),
                    "used_percent": round(12 + 30 * f * scale, 1)}
    return out


def events_for(n: int, ports=None) -> list:
    """EVENTS for the n-th simulated workflow: its own PR number, and the ports it really leased."""
    url = PR_URL.rsplit("/", 1)[0] + f"/{n}"
    out = []
    for event, text in EVENTS:
        if event:
            event = dict(event)
            note = event.get("note") or ""
            if ports and ":9103/:9203" in note:
                note = note.replace(":9103/:9203", f":{ports[0]}/:{ports[1]}")
            event["note"] = note.replace(PR_URL, url).replace("PR #3", f"PR #{n}")
            if not event["note"]:
                event.pop("note")
        if text:
            text = text.replace(PR_URL, url)
        out.append((event, text))
    return out


def due(elapsed: float, index: int = 0, speed: float = 1.0) -> int:
    """How many events of workflow `index` are due after `elapsed` seconds (each workflow a little slower than
    the one before, so they don't finish in lockstep)."""
    scale = (1 + 0.15 * index) / max(speed, 0.01)
    t, n = 0.0, 0
    for d in DELAYS:
        t += d * scale
        if t > elapsed:
            break
        n += 1
    return n
