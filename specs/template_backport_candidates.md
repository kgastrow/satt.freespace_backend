# Template backport candidates

Work done in OneFan that fixes code the template also ships.

Two repos are referenced throughout, both by absolute path:

- **Template** — `/home/kgastrow/ayzer.webapp.template/`
- **Reference implementation (this repo)** — `/home/kgastrow/OneFan/`

Every **Status** below was verified by reading the template's **working tree**
on 2026-09-06 (HEAD `8df35ed4`, 2026-07-08, plus 86 uncommitted files — several
backports already live there uncommitted). Every **Detect** command is
copy-pasteable and reads the template directly; if it matches, the gap is still
open.

Read order for an agent with limited budget: `A1`, `A4`, `N3`, `N4`, `N5` first
— each is a handful of lines and fixes outright broken behaviour. Then `S2`,
`S3`, `A5`, `A6`.

Items already applied to the template are listed at the end so nobody re-does
them.

---

# Tier 0 — security

## S2 · "Per-IP" does not mean per-IP behind a CDN
**Status** — PRESENT.

**Template**
- `/home/kgastrow/ayzer.webapp.template/app/backend/src/services/audit.py:306`
- `/home/kgastrow/ayzer.webapp.template/app/backend/src/core/rate_limit.py:19`

**Reference** — `/home/kgastrow/OneFan/app/backend/src/core/client_ip.py:93`
(`get_client_ip`), commit `d084730`.

**Symptom** — audit rows record an address the visitor chose, and every visitor
behind one CDN edge node shares a single rate-limit bucket, so the limit either
never fires or fires for innocents.

**Mechanism** — the audit path reads `X-Forwarded-For` and takes index `[0]`:
```python
forwarded = request.headers.get("X-Forwarded-For")
if forwarded:
    return forwarded.split(",")[0].strip()
```
Cloudflare and most CDNs **append** to a visitor-supplied XFF rather than
replacing it, so `[0]` is attacker-chosen. Meanwhile the limiter uses slowapi's
`get_remote_address` → `request.client.host`, which after uvicorn's
`ProxyHeadersMiddleware` is the *edge* address, shared by everyone behind that
node.

**Fix** — one module both call sites use, driven by a configured trusted header
name. The rule it encodes: only ever trust a header the edge **overwrites**
(`CF-Connecting-IP`, `True-Client-IP`); append-only headers are refused in code,
not merely discouraged. Sound only with an origin lock at the web server, so
ship the two together. OneFan made startup refuse to boot without the setting.

**Detect**
```
grep -n "X-Forwarded-For" /home/kgastrow/ayzer.webapp.template/app/backend/src/services/audit.py
grep -n "get_remote_address" /home/kgastrow/ayzer.webapp.template/app/backend/src/core/rate_limit.py
```

**Cost** — small in code; needs a deployment decision. Any load test of rate
limiting run before this measured one bucket, not many.

## S3 · A clock step 401s every signed-in user
**Status** — PRESENT. Nine `jwt.decode` sites, none passing decode options.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/api/deps.py:173`,
`api/auth.py`, `api/account_linking.py:61`, `api/sso.py`,
`core/security.py:184` (and two more in that file),
`services/notifications/unsubscribe.py`, `services/request_log_writer.py`.

**Reference** — `/home/kgastrow/OneFan/app/backend/src/core/security.py:50`
(`JWT_DECODE_OPTIONS`) and `:81` (`jwt_decode_options()`), commit `1a3297a`.

**Symptom** — after an NTP correction, a VM migration or a hypervisor pause,
live users get 401s on tokens minted seconds earlier.

**Mechanism** — PyJWT ≥ 2.10 validates `iat` with **zero** tolerance and raises
`ImmatureSignatureError` for a token issued "in the future", which the deps
layer maps to an invalid-token 401.

**Fix** — a shared `JWT_DECODE_OPTIONS = {"verify_iat": False}` passed at every
decode site. Deliberately **not** `leeway=`: PyJWT's leeway is not per-claim, so
`leeway=30` would also accept every expired token for 30 more seconds. RFC 7519
§4.1.6 makes `iat` informational; `nbf` is the claim that means "not valid
before" and stays strict. Measured effect on token lifetime: zero seconds.

**Detect**
```
grep -rn "jwt.decode" /home/kgastrow/ayzer.webapp.template/app/backend/src | grep -v verify_iat
```

**Cost** — small and mechanical.

## S4 · SSO account linking needs no proof of account control
**Status** — PRESENT.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/api/account_linking.py:38`

**Reference** — `/home/kgastrow/OneFan/app/backend/src/services/auth_session.py`
(`issue_session_for_user`) and the cookie-bound SSO state in
`/home/kgastrow/OneFan/app/backend/src/api/sso.py`, commit `bcd23fd`.

**Symptom** — `POST /auth/sso/link` accepts a link token and returns a full
session. There is a `purpose == "sso_link"` check but no `get_current_user`
dependency, so possession of the token is the only proof required.

**Fix in OneFan** — SSO `state` made cookie-bound and fail-closed, and session
issuance consolidated into one function so no path can mint a session that skips
the 2FA and suspension gates.

**Detect**
```
grep -n "get_current_user" /home/kgastrow/ayzer.webapp.template/app/backend/src/api/account_linking.py
```

**Cost** — review-derived rather than proven by an exploit here. Confirm against
the template's own SSO flow before changing it.

---

# Tier 1 — availability

## A1 · One reconnecting client kills realtime for the whole process
**Status** — PRESENT.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/services/websocket/redis_pubsub.py:412`

**Reference** — `/home/kgastrow/OneFan/app/backend/src/services/websocket/redis_pubsub.py:476`,
commit `ea35c66`.

**Symptom** — chat, notifications, live updates and maintenance banners stop for
**every** connected user, with nothing surfaced to any client, until the backend
is restarted. In the log:
```
ERROR: Pub/sub listener error: dictionary changed size during iteration
INFO:  Pub/sub listener stopped (running=True)
```
`running=True` — nothing asked it to stop.

**Mechanism** — the listener iterates the live dict:
```python
callbacks = self._subscriptions.get(channel, {})
for cb_id, callback in callbacks.items():
    await callback(parsed_message)
```
`await callback(...)` yields; `subscribe`/`unsubscribe` mutate
`self._subscriptions[channel]` under a lock the listener does not hold. So any
socket connecting or disconnecting mid-broadcast changes the dict during
iteration. The `RuntimeError` is raised by the **iterator**, not the callback,
so it sails past the per-callback `except`, reaches the outer handler, unwinds
the `while` and ends the listener task.

**Fix** — iterate a snapshot:
```python
callbacks = list(self._subscriptions.get(channel, {}).items())
```
A callback removed mid-broadcast then receives that one message, which is a
harmless stale delivery.

**Detect**
```
grep -n "_subscriptions.get(channel" /home/kgastrow/ayzer.webapp.template/app/backend/src/services/websocket/redis_pubsub.py
```

**Cost** — one line. Highest value-per-character item in this document.

**Related, still open in OneFan too** — the outer `except Exception` stops the
listener permanently for any *other* unanticipated error, and `subscribe()`
never restarts it. Worth fixing properly in the template: log-and-continue for
unexpected errors, plus a supervisor that restarts the listener when `_running`
is true but the task is gone.

## A2 · One slow client stalls fan-out for everyone on that worker
**Status** — PRESENT.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/api/websocket.py:56`

**Reference** — `/home/kgastrow/OneFan/app/backend/src/services/websocket/sender.py`
(whole file, 186 lines) and its use at
`/home/kgastrow/OneFan/app/backend/src/api/websocket.py:179`, commits `458f2d6`,
`2148530`, `aa82cdc`.

**Symptom** — realtime delivery degrades or stops for all users on a worker
whenever one client stops reading (a backgrounded mobile browser, a phone on a
dying connection, a paused debugger).

**Mechanism** — the pub/sub callback awaits the socket directly:
```python
async def callback(message: dict[str, Any]) -> None:
    try:
        await websocket.send_json(message)
```
There is one pub/sub listener task per worker and it awaits every subscriber's
callback in turn, so a client whose receive window is full blocks delivery to
every other connection on that worker.

**Fix** — port `sender.py`: a bounded per-connection queue with a non-blocking
`offer()`, a drain task per connection, and an actual socket **close** on
overflow rather than a silent drop. The pub/sub callback becomes
`sender.offer(message)` and never touches the socket.

**Detect**
```
grep -n "await websocket.send_json(message)" /home/kgastrow/ayzer.webapp.template/app/backend/src/api/websocket.py
```

**Cost** — medium. New module plus a lifecycle change in the socket handler
(bind teardown names before the `try`, or shutdown raises `NameError` over the
real error).

## A3 · Every client reconnects in lockstep after a restart
**Status** — PRESENT. No jitter anywhere in the hook.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/frontend/src/hooks/useWebSocket.ts:53`

**Reference** — `/home/kgastrow/OneFan/app/frontend/src/hooks/useWebSocket.ts:130`,
commits `37b3121`, `90e05e6`, `c6845fd`.

**Symptom** — a backend restart or a brief network blip produces a synchronised
reconnect burst from every open tab, exactly when the backend is least able to
absorb it.

**Mechanism**
```ts
const delay = RECONNECT_BASE_DELAY_MS * Math.pow(RECONNECT_MULTIPLIER, attempt)
return Math.min(delay, RECONNECT_MAX_DELAY_MS)
```
Deterministic for every client. The same file also resets the attempt counter on
auth events, tracks connect time per hook rather than per socket, and has no
unmount guard on the pending timer.

**Fix** — full jitter (`Math.round(Math.random() * capped)`) off a 5s base with a
widened cap; stop resetting backoff on re-authentication; per-socket connect
timestamps; guard the pending timer on unmount; hoist access-revoked handling so
a revoked client stops retrying instead of hammering.

**Detect**
```
grep -c "Math.random" /home/kgastrow/ayzer.webapp.template/app/frontend/src/hooks/useWebSocket.ts
```
(`0` = no jitter)

**Cost** — small, contained in one hook.

**Related trap** — the socket batches frames, so a Redux slice that matches only
`addMessage` and not `addMessages` silently receives nothing while looking
correctly wired. Worth a comment in the template's slice example.

## A4 · One Redis blip disables caching until the next restart
**Status** — PRESENT.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/services/cache.py:96`
and `:115`

**Reference** — `/home/kgastrow/OneFan/app/backend/src/services/cache.py:136`
(`_mark_unavailable`) and `:146`, fixed in commits `7a4a71a` / `4263637`.

**Symptom** — a two-second Redis hiccup permanently ends caching for that
worker. Nothing is logged after the first error. The request-logging middleware
loads config on every request *before* checking `enabled`, so the standing cost
is several extra DB queries per request, forever.

**Mechanism** — `self._enabled = False` inside the connection-error handlers,
with nothing anywhere setting it back. `_enabled` is the *configuration* flag
(`settings.CACHE_ENABLED`) being reused as a *runtime health* flag.
Configuration does not recover on its own, and nothing re-probes.

**Fix** — separate the two. Keep `_enabled` for configuration; add a cooldown
timestamp for health (`_unavailable_until`), set by any `RedisError`/`OSError`/
timeout and cleared by a successful ping. Log once per outage, not once per
request. Callers fall open to the database while the cooldown runs. Decode
errors are bad payloads, not a sick backend — do not start a cooldown for them.

**Detect**
```
grep -n "_enabled = False" /home/kgastrow/ayzer.webapp.template/app/backend/src/services/cache.py
```

**Cost** — small; about 40 lines in one class.

## A5 · A Redis blip is a total API outage via the rate limiter
**Status** — PRESENT. The template still constructs a plain `Limiter` with no
storage options.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/core/rate_limit.py`
(whole file, 24 lines)

**Reference** — `/home/kgastrow/OneFan/app/backend/src/core/rate_limit.py:84`
(`FailOpenLimiter`), `:201` (`storage_options`), `:211`
(`exempt_from_ip_limit`), commits `d084730`, `7a4a71a`.

**Symptom** — HTTP 500 on **every** request (not just limited ones) while Redis
is unreachable; and a Redis that accepts connections but stops answering hangs
workers indefinitely.

**Mechanism** — two independent defects.
1. slowapi 0.1.9 drives `limits` with a **synchronous** Redis client and
   registers no handler for `redis.ConnectionError`; the failure path ends in an
   `AttributeError` → 500.
2. `storage_uri` alone means `redis.from_url` with `socket_timeout` and
   `socket_connect_timeout` both `None`.

**Fix** — a `Limiter` subclass that catches storage errors and falls back to
in-memory limiting (with a guard in case the fallback itself raises), logs once
per outage rather than per request, and passes explicit socket timeouts through
`storage_options`. Re-raise `RateLimitExceeded` untouched — that is the limiter
working. Note `limits` offers `async+redis://`, but slowapi 0.1.9 cannot use it.

Port `exempt_from_ip_limit` alongside: slowapi's own `@limiter.exempt` returns a
wrapper that breaks FastAPI's signature inspection, so exemptions must be
registered by name into `limiter._exempt_routes` instead.

**Detect**
```
grep -n "storage_options\|ConnectionError" /home/kgastrow/ayzer.webapp.template/app/backend/src/core/rate_limit.py
```
(no output = unfixed)

**Cost** — medium; one file, well-bounded. Do it before any load test.

## A6 · Concurrent 401s produce N refresh calls
**Status** — PRESENT. No mutex or shared promise.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/frontend/src/store/api.ts:67-75`

**Symptom** — a page with several queries in flight hits token expiry, fires one
`POST /auth/refresh` per failed query, and (once refresh-token rotation exists)
all but one fail — logging the user out mid-session.

**Fix** — a module-level in-flight promise: the first 401 starts the refresh,
every concurrent 401 awaits the same promise, then all retry. Worth fixing in
the same pass: a transient `/user/me` failure wipes the session
(`app/frontend/src/features/auth/authSlice.ts`), and
`RootRedirect`/`RegistrationGuard` fail the wrong way on error.

**Detect**
```
grep -n "auth/refresh" /home/kgastrow/ayzer.webapp.template/app/frontend/src/store/api.ts
```
then check for a shared promise around it.

**Cost** — small. Still open in OneFan too.

## A7 · `/health` is a constant, and a router that fails to import is swallowed
**Status** — PRESENT.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/main.py:476`
```python
@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "healthy"}
```
plus the `except ImportError:` blocks around optional wiring and router include.

**Symptom** — a load balancer keeps routing to a process whose database or Redis
is gone. Separately, an `ImportError` in a router leaves the app **up** with
those endpoints silently missing — production 404s for a whole feature area.

**Fix** — make the probe reflect at least DB and Redis reachability (or point
the load balancer at `/health/detailed`, which the template already has), and
let a router import failure crash startup. A deploy that fails loudly is
recoverable; one that silently drops endpoints is not.

**Cost** — small, but it changes deployment behaviour: decide it deliberately.

---

# Tier 2 — features that report success while doing nothing

This is the dominant bug class in this codebase. Every item below was green in
tests and looked correct in the UI.

## N2 · The metrics dashboard measures nothing
**Status** — PRESENT. `record_activity` still has zero call sites; no
`metric_rollup` model exists.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/services/user_activity.py:43`

**Reference** — `/home/kgastrow/OneFan/app/backend/src/api/deps.py` (producer in
`get_current_user`), `/home/kgastrow/OneFan/app/backend/src/services/metrics/buckets.py`,
`/home/kgastrow/OneFan/app/backend/src/services/metrics/rollup.py`,
`/home/kgastrow/OneFan/app/backend/src/models/metric_rollup.py`,
`/home/kgastrow/OneFan/app/backend/src/workers/metrics_tasks.py`, commit `4263637`.

**Symptom** — "Active users" renders `0` as though it were a measurement. Every
other figure resets to zero on deploy and has no history, so nothing can be
graphed.

**Fix** — put the producer in `get_current_user`, the one point every
authenticated request passes, deduped per user per minute. Then split storage by
horizon, because a Prometheus counter in one process is not a time series:
1 min → Redis hashes with a 2h TTL; 5 min → a `metric_rollup` table, 7 days;
1 hour → same table, 1 year. Worker crons fold, downsample and prune.

Two traps worth carrying over as comments: HyperLogLog horizons are **unions,
not sums** (adding hourly figures over-counts), and buckets must flush on a
background ticker — a request-triggered flush cannot write the last batch before
traffic stops (caught live: a 50-request burst wrote 1).

**Detect**
```
grep -rn "record_activity" /home/kgastrow/ayzer.webapp.template/app/backend/src | grep -v user_activity.py
```
(no output = dead metric)

**Cost** — large for the charts; small for the producer call site alone, which
by itself turns a lie into a number.

## N3 · Unsubscribe links have never worked
**Status** — PRESENT. Both URLs still built against `/api/`.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/services/notifications/unsubscribe.py:194`
and `:225`
```python
return f"{self.base_url}/api/notifications/unsubscribe?token={token}"
```
The API is mounted at `/api/v1` (`main.py:527`), so both paths 404.

**Reference** — `/home/kgastrow/OneFan/app/backend/src/services/notifications/unsubscribe.py:215`
(footer link, now a frontend page) and `:248` (one-click, `/api/v1/...`), commit
`a94ec9d`.

**Symptom** — every unsubscribe link in every email ever sent is a 404. Gmail
and Yahoo record a failed one-click unsubscribe against sending reputation.

**Mechanism** — `get_list_unsubscribe_headers` additionally computes the
one-click URL and then does not use it.

**Fix** — build both URLs from the same versioned prefix as everything else, and
implement `POST /notifications/unsubscribe/one-click` for RFC 8058: token in the
query string, body ignored, and **always 200** — a 4xx is recorded by the
mailbox provider as a broken unsubscribe. Gate it to `user_configurable=True`
categories from the same decision as the footer link, so the two cannot
disagree.

**Detect**
```
grep -rn '"/api/' /home/kgastrow/ayzer.webapp.template/app/backend/src | grep -v "/api/v1"
```

**Cost** — small. The cheapest deliverability win available.

## N4 · Every notification row has stored NULL metadata
**Status** — PRESENT.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/crud/notification.py:79`
```python
metadata=data.get("metadata"),
```
against a model whose column is `extra_data`.

**Reference** — `/home/kgastrow/OneFan/app/backend/src/crud/notification.py:90`,
commit `643b828`.

**Symptom** — `extra_data` is empty on every notification ever created. Anything
reading it (deep links, dedupe keys, template variables) silently sees nothing.

**Mechanism** — this should raise. It does not, because
`hasattr(Notification, "metadata")` is **true**: `metadata` is the declarative
`MetaData` object on the Base. SQLAlchemy sets a shadowing instance attribute
and the insert proceeds with the column unset.

**Fix** — pass `extra_data=`, then grep the codebase for any other `metadata=`
kwarg aimed at a declarative model; the failure mode is silent by construction
and will recur.

**Detect**
```
grep -rn "metadata=" /home/kgastrow/ayzer.webapp.template/app/backend/src/crud/
```

**Cost** — one line, plus a grep sweep.

## N5 · Bulk sends ignore the segment the admin chose
**Status** — PRESENT. `extra_data` appears zero times in the file.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/crud/bulk_notification.py`
(`create_bulk_notification`)

**Reference** — `/home/kgastrow/OneFan/app/backend/src/crud/bulk_notification.py`,
commit `643b828`.

**Symptom** — an admin narrows a bulk notification to a segment; it goes to the
entire tenant, and the UI reports success.

**Mechanism** — the create never persists `extra_data`, which is exactly where
`bulk_processor` reads its **recipient filters** from. Related in the same file:
a bulk created from a `template_code` stored the code in `extra_data`, never
resolved it, and sent an empty body while reporting success.

**Fix** — persist it, and add a test that a filtered bulk resolves to fewer
recipients than an unfiltered one.

**Detect**
```
grep -c "extra_data" /home/kgastrow/ayzer.webapp.template/app/backend/src/crud/bulk_notification.py
```
(`0` = unfixed)

**Cost** — small. High embarrassment value if it ships.

## N6 · One `organization_id` doing three different jobs
**Status** — PRESENT.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/services/notifications/dispatcher.py:312`

**Reference** — `/home/kgastrow/OneFan/app/backend/src/services/notifications/dispatcher.py:102`
(`preference_organization_id` parameter) and `:142`, commit `f58334a`.

**Symptom** — in any deployment where a user's `User` row lives in a different
org from their notification history, **every** notification on **every** channel
is dropped silently.

**Mechanism**
```python
select(User).where(
    User.id == user_uuid,
    User.organization_id == org_uuid,
    ...
)
...
if not user:
    logger.error(f"User not found: {user_id} in org {organization_id}")
    return None
```
The single `organization_id` parameter is simultaneously (a) the scope of the
user lookup, (b) the scope of the preference check, and (c) the scope of the
notification record. Those are three different questions. As soon as any product
decision separates them — a platform-level sentinel org, a user belonging to
several orgs, an end user registering under one tenant and receiving
platform-level notices — the lookup fails and the send returns `None` as though
the user had opted out.

**Fix** — thread a separate `preference_organization_id`, and relax the user
lookup where the scoping org is deliberately not the user's home org.

**Test trap that hides it** — if the fixtures register every user in the platform
org, the two ids coincide and no test can see this. Any test of cross-org
notification delivery must use a non-platform org or it proves nothing.

**Cost** — medium; a signature change through the dispatcher and its callers.
Skip only if the template will never have more than one org per user — but read
it first, because the symptom is total silence, not an error.

## N7 · An unknown category is allowed on every channel, with no toggle
**Status** — PRESENT.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/services/notifications/preference_checker.py:84`,
`:108`, and `:291`/`:305`/`:319`

**Symptom** — a typo'd or unseeded `category_code` passes every preference check
and delivers on every channel, while showing the user no way to turn it off.

**Mechanism** — `_get_category` returns `None` for an unknown code; both guards
are written as `if category and ...` / `if cat_pref and ...`, so a missing
category falls through to "allowed". Three `_is_channel_enabled_for_*` helpers
end with `return True  # Unknown channels default to enabled` — the same shape.

**Fix** — decide the default explicitly and fail the *build*, not the request:
keep the permissive runtime default (a dropped notification is worse than an
extra one) but add a test that every `category_code=` literal in `src/` exists in
the seeded category set. OneFan hit this three times in one week —
gamification, ticketing and account notifications each shipped uncategorised.

**Detect**
```
grep -rn "category_code=" /home/kgastrow/ayzer.webapp.template/app/backend/src | wc -l
```
then compare against the seeded categories.

**Cost** — small (the guard test), and it retires a recurring class.

## N8 · Rendered notifications ship raw `{{placeholders}}` to users
**Status** — PRESENT. Renderer defaults to `strict: bool = False` and no test
asserts a rendered body is free of `{{`.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/services/notifications/template_renderer.py:38`

**Reference** — `/home/kgastrow/OneFan/app/backend/src/services/notifications/links.py`,
`/home/kgastrow/OneFan/app/backend/src/services/notifications/formatting.py`,
and the two guard tests
`/home/kgastrow/OneFan/app/backend/tests/service_tests/test_notification_content.py`
and `test_notification_link_sources.py`, commit `643b828`.

**Symptom** — a real user receives `Tickets confirmed for {{club_home}} vs
{{club_away}}`.

**Mechanism** — non-strict rendering is correct for the renderer and fatal for
callers: an under-supplied `template_vars` ships the placeholder rather than
failing.

**Fix** — keep the renderer permissive; add two mutation-verified guard tests.
One renders every trigger with its real variable set and asserts no `{{`
survives. One asserts every user-facing link the backend builds resolves to a
route that exists in the frontend router — OneFan had seven backend paths that
had drifted from the real router tree, each a hard 404 on tap.

Also port the *shape* of `links.py`: every frontend path as a named builder with
an `absolute()` variant for email, rather than f-strings scattered across trigger
handlers.

**Cost** — small to medium. The guard tests are what stop the class returning;
without them the fix rots in a month.

## N9 · Email partly bypasses the configured provider
**Status** — PARTIAL. The template already resolves
`get_effective_email_config` and calls `send_with_config` in
`workers/tasks.py:114` and the dispatcher, but raw `send_email` is still
reachable from five places and nothing refuses an unresolved config.

**Template** — remaining raw callers:
`/home/kgastrow/ayzer.webapp.template/app/backend/src/services/notifications/email_provider.py:96`,
`services/notifications/dispatcher.py:759`, `api/email_settings.py:280`,
`workers/tasks.py:122`, and three internal helpers in `services/email.py`
(`:258`, `:290`, `:327`).

**Reference** — `/home/kgastrow/OneFan/app/backend/src/services/email.py`,
`/home/kgastrow/OneFan/app/backend/src/services/notifications/email_provider.py`,
commit `9a5fc61`.

**Symptom** — the org has SendGrid configured in the admin UI; mail goes out over
`config.json` SMTP anyway, with a "sent" status.

**Fix** — finish the invariant rather than the call sites: make both provider
wrappers refuse to send without a resolved `EmailConfig`, and have
`get_email_provider` return `None` (fail loud) when provider is sendgrid with no
API key. Mark `send_email()` legacy/internal in its docstring and write the rule
into CLAUDE.md.

**Detect**
```
grep -rn "\.send_email(" /home/kgastrow/ayzer.webapp.template/app/backend/src
```

**Cost** — small per call site; the value is the invariant.

---

# Tier 3 — guards that stop a class from returning

## G1 · Build-time detail-code registry guard
**Status** — PRESENT (no such test exists in the template).

**Reference** — `/home/kgastrow/OneFan/app/backend/tests/unit_tests/test_detail_code_registry.py`

**Gap** — `get_response_code` is deliberately fail-soft: an unregistered key is
logged and returned as-is rather than raising, so a missing registration never
escalates a deliberate 4xx into a 500. The consequence is that **nothing at
runtime notices** an unregistered code — it ships to the client as a raw
untranslated key and the frontend renders `auth.some_code` to the user.

**What the guard must cover** (each bullet is a blind spot found the hard way):
- the keyword form `detail_code="..."`,
- codes passed **positionally** into helpers (`_parse_id(value, "scan.x")`),
- the ~137 direct `get_response_code("...")` call sites, whose codes go into a
  response *model field* rather than through `create_success_response`.

Seeding that last set in OneFan immediately surfaced a code returned on a **200**
that had never been registered.

**Detect**
```
ls /home/kgastrow/ayzer.webapp.template/app/backend/tests/unit_tests/ | grep -i "response_code\|detail_code"
```

**Cost** — small; one test file, and every downstream app inherits the guard.

## G2 · Schema drift is invisible to the test suite
**Status** — PRESENT. `/home/kgastrow/ayzer.webapp.template/app/backend/tests/conftest.py:143`
builds the schema with `sqlite+aiosqlite:///:memory:`.

**Gap** — tests build the schema from the models, never from the migration
chain, so any Postgres-only drift passes every test and fails only in
production. Two classes:

- `Enum(native_enum=False)` becomes `VARCHAR(max(len(values)))` with **no** CHECK
  constraint (SQLAlchemy 1.4+ defaults `create_constraint=False`). Adding a
  longer member silently needs a column widening. `alembic check` does catch it.
- Native `Enum` persists the member **NAME**, not its value, and both
  `alembic check` and autogenerate are **blind to enum labels**. A missing label
  needs hand-written `ALTER TYPE ... ADD VALUE IF NOT EXISTS 'NAME'`. OneFan
  shipped `'expired'` where the name was `'EXPIRED'`; the cron using it errored
  on every run and swallowed it as `{"status": "error"}`.

**Fix** — a documented sweep, ideally a CI step: `alembic upgrade head`, then
`alembic check`, then compare `pg_enum` labels against every model's native
`Enum.enums`. The second half is the part nothing else does.

**Cost** — small script; needs a Postgres in CI.

## G3 · Handlers that register by import side effect
**Status** — check before porting; the shape exists in the template's worker.

**Reference** — `/home/kgastrow/OneFan/app/backend/src/workers/worker.py`, and the
finding in `/home/kgastrow/OneFan/ai_docs/launch-review-2026-09.md`.

**Gap** — event consumers, fulfilment handlers and cron handlers register when
their module is imported. `import src.workers.worker` imports only some of them;
others appear only when an unrelated cron lazily imports their module, and some
never register in the worker at all. Tests never catch it, because pytest
imports `main`, which imports everything.

**Fix** — an explicit registration list in the worker, plus a test that asserts
the registered set from the **worker's** import graph rather than the API's.

**Cost** — small, and it prevents a class of "works locally, dead in the worker".

---

# Tier 4 — infrastructure and workflow

## I1 · Connection pool settings that were never in effect
**Status** — PRESENT. Still `poolclass: NullPool` with `pool_pre_ping` and
`pool_recycle` set in a branch that ignores them.

**Template** — `/home/kgastrow/ayzer.webapp.template/app/backend/src/database.py:45`,
`:106-107`

**Reference** — `/home/kgastrow/OneFan/app/backend/src/database.py:28-70`
(`APP_POOL_SIZE`, `APP_MAX_OVERFLOW`, `APP_POOL_TIMEOUT`, `APP_POOL_RECYCLE` and
the budget comment), commits `9e71b7e` then `1e1cd0e`.

**What changed** — NullPool → a bounded `AsyncAdaptedQueuePool` with unique
prepared-statement names; sizing hardcoded with the full budget written out;
`pool_timeout` cut to **5s** (there is no request-timeout middleware, so a long
wait burns the timeout and *then* fails while pinning an async slot — worse than
NullPool's instant failure); `pool_recycle` hardcoded because SQLAlchemy treats
any value `> -1` as live, so a deployed `pool_recycle=0` silently degrades the
pool to NullPool with extra steps and no error anywhere.

**Worth carrying over verbatim** — the PgBouncer failure mode: at
`max_client_conn` it **hangs** rather than refusing, because it stops accepting
and the kernel backlog holds the socket. A starting worker blocks silently
instead of erroring.

**Cost** — medium and deployment-specific. Read the reasoning; re-derive the
numbers for the template's own worker counts rather than copying them.

## I3 · RBAC guards and audit-log filters
**Status** — PARTIAL. The template has `validate_role_hierarchy`
(`app/backend/src/api/user_role.py:69`); OneFan added platform-level role and
target guards on top.

**Reference** — `/home/kgastrow/OneFan/app/backend/src/api/role.py`,
`/home/kgastrow/OneFan/app/backend/src/api/user_role.py`,
`/home/kgastrow/OneFan/app/backend/src/api/audit_log.py` and their CRUD, commit
`f115507` (11 of 13 changed files are template files, so it ports almost
verbatim).

## I4 · Auth surface, remaining
**Status** — PARTIAL. The template already fixed the 2FA bypass and
impersonation revocation (`4f1d4f92`).

Still worth comparing, all in template files: OTPs hashed at rest
(`app/backend/src/crud/user_otp.py`); mandatory 2FA enforced server-side with
restricted sessions rather than by the client; deletion-request cancel and
unverified re-register (`api/user.py`, `crud/organization.py`, commit `8754c14`);
cross-tenant leaks closed in help center, request logs and the bulk processor
(commit `203f1ed`).

Port selectively — some of the OneFan auth wave is entangled with its
club/union role model.

## I5 · Split the production seeder in two
**Status** — PRESENT. The template ships only
`/home/kgastrow/ayzer.webapp.template/app/backend/scripts/seed_first_tenant.py`
and `seed_smoke_test.py`.

**Reference** — `/home/kgastrow/OneFan/app/backend/scripts/seed_maintenance.py`
and the Seeding section of `/home/kgastrow/OneFan/CLAUDE.md`, commit `fe8d40c`.

**Gap** — `seed_first_tenant.py` is a bootstrap seeder that creates orgs,
settings and named accounts at fixed emails alongside its reference data. Run it
on a **live** deployment to pick up a new permission or notification template and
it re-asserts those identities: an admin who changed their email in the UI gets
the seed's original address recreated alongside them.

**Fix** — a second, additive get-or-create seeder for code-owned data only
(roles, permissions and grants, rate limits, user types, notification templates,
cron definitions, system config keys), touching no users, orgs or settings, with
`--list`, `--only`, `--skip` and `--dry-run` (writes, reports counts, rolls
back). Then a CLAUDE.md rule: new reference data must be added to the maintenance
seeder, because a key only the bootstrap seeder knows about will never reach an
already-deployed environment.

**Cost** — medium once; it removes a whole category of "we cannot seed production
safely".

---

# Already applied to the template

Verified present in the template working tree on 2026-09-06. Do not re-port.

- **ARQ job metrics (`N1`)** — complete, including
  `app/backend/src/constants/queues.py`, the rewritten `queue_health.py`, the
  `WorkerSettings` re-declarations, the `last_execution` datetime fix, the
  frontend error branches, and both guard tests
  (`test_job_metrics_recording.py`, `test_queue_health_keys.py`). The port guide
  is already sitting there as `specs/arq_job_metrics_template_fix.md`. All of it
  is uncommitted in that tree.
- **Token type confusion (`S1`)** — both doors closed:
  `app/backend/src/api/deps.py:174` and `app/backend/src/api/websocket.py:139`
  reject any token whose `type` is not `access`/`impersonation`.
- **Build identity and update lifecycle (`I2`)** —
  `app/frontend/src/store/api.ts:29` sends `X-App-Commit`, with
  `app/frontend/src/store/api.appCommit.test.ts` guarding it.
- **E2E harness isolation (`I6`)** — `app/frontend/playwright.config.ts` already
  offsets ports by codebase index for parallel checkouts.
- **Email provider resolution** — partially, see `N9`.

---

# Known-open in OneFan too

Template defects OneFan has confirmed and **not** fixed. A template fix flows
downstream to every app:

- Pub/sub listener still exits permanently on any non-`ConnectionError` (`A1`).
- Refresh tokens have no rotation or revocation (`app/backend/src/api/auth.py`).
- Concurrent 401s stampede the refresh endpoint; a transient `/user/me` error
  wipes the client session (`A6`).
- Request-logging middleware reads the body before the size check, writes files
  synchronously on the loop, and overwrites `response.background`.
- bcrypt runs on the event loop.
- The outbox dispatcher and cron scheduler take no locks (`SKIP LOCKED`), so two
  workers can double-process.
- A task that *returns* `{"status": "error"}` instead of raising is recorded as a
  success by both ARQ instrumentation decorators.
- No error tracking (no Sentry/OTel) in the requirements at all.

---

# Deliberately excluded

OneFan-specific, or built on top of template code rather than fixing it: web
push (`/home/kgastrow/OneFan/app/backend/src/services/notifications/web_push_*`,
new here — though the multi-tenant root cause in `N6` was found through it),
Ozow payments, streaming and replay, ticketing and gate scanning,
clubs/fixtures/standings, gamification, the profanity filter, and the Cloudflare
Tunnel cutover plus Apache/systemd packaging (useful as a reference, but shaped
around one box's topology).
