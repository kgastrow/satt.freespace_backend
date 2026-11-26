# Making ARQ job metrics actually record — template port guide

Source: OneFan commit `207ac88` ("jobs: queue health, job metrics, worker
settings"), against `arq==0.26.1`. Everything below is a *behavioural* fix: the
pre-fix code ran without errors and rendered a background-jobs panel that was
permanently empty, permanently healthy, or permanently zero. It is the
"reports success while doing nothing" class of bug — nothing logs, nothing
fails, the numbers are just wrong.

Port targets in the template:

| File | Change |
|---|---|
| `src/constants/queues.py` | **new** — single source of truth for queue name + derived Redis keys |
| `src/workers/job_metrics.py` | F1, F2 |
| `src/workers/settings.py` | F3 (base class), queue name from constants |
| `src/workers/worker.py` | F3 (concrete class re-declaration) |
| `src/services/tasks.py` | queue name from constants |
| `src/services/queue_health.py` | F4–F8 (largely a rewrite) |
| `src/serialisers/background_jobs.py` | F9 |
| `src/constants/job_types.py` | F11 |
| `src/pages/admin/BackgroundJobsPage.tsx` | F10 |
| `tests/unit_tests/test_job_metrics_recording.py` | **new** — pins F1, F2 |
| `tests/unit_tests/test_queue_health_keys.py` | **new** — pins F4–F8 |

---

## Design note: why Redis and the DB, not Prometheus

The ARQ worker is a **separate process** from the API. Its
`prometheus_client` registry is not the API's, so a counter incremented inside
a job is invisible to the API's `/metrics` scrape and dies with the process.
Prometheus instrumentation in the worker is therefore only useful if the worker
is scraped separately; the admin panel must read from **Redis** (rolling stats)
and the **database** (`background_job_execution`, the persistent audit trail).

That single fact is what makes F1 a bug rather than a preference.

---

## F1 — `METRICS_ENABLED` deleted the audit trail

Both `instrument_task` and `instrument_cron_task` opened with:

```python
if not settings.METRICS_ENABLED:
    return await func(ctx, *args, **kwargs)
```

The early return sits *above* the Redis stats write and the database execution
record, so a Prometheus scrape toggle silently switched off the persistent job
history the admin panel reads. `METRICS_ENABLED` must gate **only** the
Prometheus observations.

Fix: drop the early return, capture the flag, and guard only the raw gauge
(the `record_*` helpers already check the flag themselves):

```python
# Prometheus-only switch. The per-call record_* helpers check this
# flag themselves; the raw gauge below has to be guarded explicitly.
metrics_enabled = settings.METRICS_ENABLED

if metrics_enabled:
    JOBS_IN_PROGRESS.labels(job_type=job_type, instance_id=INSTANCE_ID).inc()
```

…and in `finally`:

```python
finally:
    if metrics_enabled:
        JOBS_IN_PROGRESS.labels(job_type=job_type, instance_id=INSTANCE_ID).dec()
```

## F2 — `instrument_cron_task` never wrote to the database

`instrument_task` called `_record_to_db(...)` on both the success and failure
paths. `instrument_cron_task` called it on neither. The ARQ-native crons are
the only jobs on a fixed schedule, so on a quiet deployment they are the only
guaranteed source of execution data — and they persisted nothing.

Fix: add the same two calls to the cron decorator.

```python
# success branch
await _record_to_db(ctx, job_name, "success", duration * 1000)

# failure branch
await _record_to_db(
    ctx, job_name, "failure", duration * 1000,
    error_type=error_type, error_message=str(e)[:500],
)
```

`_record_to_db` reads `ctx["session_factory"]`, so the worker `startup` hook
must set it (`ctx["session_factory"] = AsyncSessionLocal`). It swallows every
exception by design — instrumentation must never fail a job.

## F3 — arq silently drops inherited `WorkerSettings` attributes

`arq.worker.get_kwargs` builds the Worker kwargs from
`settings_cls.__dict__` — the class's **own** attribute dict. Attributes that
exist only on a base class are not in `__dict__`, are dropped without warning,
and arq's own defaults apply instead.

In the template, `BaseWorkerSettings` in `settings.py` declared `max_jobs`,
`job_timeout`, `keep_result`, `max_tries`, `poll_delay` and
`queue_read_limit`; the concrete `WorkerSettings` in `worker.py` subclassed it
and re-declared only `redis_settings`, `queue_name` and the lifecycle hooks.
Every tuning knob was therefore inert while looking configured.

The metrics consequence: `health_check_interval` stayed at arq's default of
**3600s**, so the heartbeat key's TTL was an hour — and any liveness check
tighter than that read a live worker as offline.

Fix: re-declare every setting on the concrete class, sourced from the base so
the two cannot drift:

```python
class WorkerSettings(BaseWorkerSettings):
    redis_settings = get_redis_settings()
    queue_name = ARQ_QUEUE_NAME
    on_startup = startup
    on_shutdown = shutdown

    # Worker tuning — re-declared so arq actually applies them.
    max_jobs = BaseWorkerSettings.max_jobs
    job_timeout = BaseWorkerSettings.job_timeout
    keep_result = BaseWorkerSettings.keep_result
    max_tries = BaseWorkerSettings.max_tries
    poll_delay = BaseWorkerSettings.poll_delay
    queue_read_limit = BaseWorkerSettings.queue_read_limit
    health_check_interval = BaseWorkerSettings.health_check_interval
```

Both classes carry a docstring stating the `__dict__` rule, because the next
person to add a knob will otherwise add it in one place only.

## F4 — queue depth read a key that never existed

The worker runs on an app-specific queue name (set deliberately so other ARQ
workers on the same Redis cannot steal jobs). `queue_health` read arq's
**default** `arq:queue`, so depth was `0` forever.

Fix: `src/constants/queues.py` as the single source of truth, imported by the
worker settings, the enqueue-side pool (`services/tasks.py`) and the health
monitor. The module imports nothing from the application, so it is safe from
circular imports:

```python
ARQ_QUEUE_NAME = "arq:<app>_backend"

# queue_name + arq.constants.health_check_key_suffix
ARQ_HEALTH_CHECK_KEY = f"{ARQ_QUEUE_NAME}:health-check"

# arq's own default is 3600s — far too coarse for a liveness signal.
ARQ_HEALTH_CHECK_INTERVAL_SECONDS = 30

ARQ_IN_PROGRESS_KEY_PREFIX = "arq:in-progress:"
ARQ_JOB_KEY_PREFIX = "arq:job:"

ARQ_JOB_TIMEOUT_SECONDS = 300
# arq psetex's the in-progress key with TTL = max_timeout + 10.
ARQ_IN_PROGRESS_TIMEOUT_SECONDS = ARQ_JOB_TIMEOUT_SECONDS + 10
```

## F5 — worker heartbeat: wrong key, wrong parse, unreachable summary

Three compounding errors:

1. It scanned `arq:health:*`. arq writes exactly **one** key per queue,
   `<queue_name>:health-check`.
2. It fed the value to `datetime.fromisoformat`. The value is a
   human-readable info string (`"Sep-03 21:10:00 j_complete=… j_failed=…"`),
   so the parse always threw and every worker was reported offline.
3. `check_health` raised the alarm on `offline_workers > 0`. An absent
   heartbeat produces an **empty** worker list, so that guard could never
   fire: the panel read healthy with the worker stopped.

Fix: key **existence** is the freshness signal (arq `psetex`s it with
TTL `(health_check_interval + 1) * 1000` ms). Do not parse the value. With N
workers overwriting one key, the only honest report is 0 or 1.

```python
heartbeat = await self._redis.get(ARQ_HEALTH_CHECK_KEY)
if heartbeat is None:
    return []
ttl_ms = await self._redis.pttl(ARQ_HEALTH_CHECK_KEY)
return [{
    "worker_id": ARQ_HEALTH_CHECK_KEY,
    "is_online": True,
    "info": heartbeat,
    "seconds_to_heartbeat_expiry": int(ttl_ms / 1000) if ttl_ms and ttl_ms > 0 else None,
}]
```

And drive the summary off `online_workers == 0`, not `offline_workers > 0`.

Note this only works because F3 brought `health_check_interval` down to 30s.

## F6 — stuck jobs scanned a key shape arq does not write

The old implementation scanned `arq:job-result:*` and read hash fields `s`
(status) and `st` (start time). arq has no such key with that shape, so
`hgetall` returned nothing and the stuck-job count was permanently `0`.

The real mechanism: arq marks a running job with `arq:in-progress:<job_id>`,
`psetex`'d with TTL `max_job_timeout + 10` seconds. **The key holds only
`b"1"`** — no function name, no start time. So:

- elapsed run time = `ARQ_IN_PROGRESS_TIMEOUT_SECONDS - (pttl / 1000)`
- function name comes from the separate job payload (F7)

The trap: **an in-progress key alone does not mean the job is still running.**
When a *cron* job finishes, arq does not delete its in-progress key — it
re-expires it to `keep_cronjob_progress` (60s) to block duplicate runs
(`arq.worker.Worker.finish_job`). That shortened TTL is indistinguishable from
"started 250s ago", so every completed cron would be reported stuck for a
minute; with ~15 crons the panel would be permanently red.

Discriminator: arq **does** delete `arq:job:<id>` on both the success and
failure paths, while a genuinely running job keeps it for its whole run. So:

```python
if not await self._redis.exists(f"{ARQ_JOB_KEY_PREFIX}{job_id}"):
    continue  # finished cron, not a stuck job
```

`EXISTS` returns an int, so the shared decoding client is safe here.

## F7 — the shared Redis client corrupts arq's pickled job payloads

The job definition at `arq:job:<id>` is **pickled bytes**. The shared
monitoring client is created with `decode_responses=True`, which mangles it on
read. Resolving a stuck job's function name therefore needs its own
`decode_responses=False` client, built lazily and cached, with a
`_binary_unavailable` latch so a failed connection is not retried per scan:

```python
raw = await binary.get(f"{ARQ_JOB_KEY_PREFIX}{job_id}")
return deserialize_job(raw).function if raw else None
```

Degrade to an explicit `"unknown"` function name rather than dropping the job
from the list — a stuck job with no name is still a stuck job.

## F8 — the stuck-job threshold was above the observability ceiling

A running job is only *observable* for as long as its in-progress key lives,
i.e. `job_timeout + 10` = 310s ≈ 5 minutes. Past that arq has already timed the
job out and the key is gone. The template default of **30 minutes** could
therefore never match anything.

Fix: default to 4 minutes, and warn loudly rather than returning a misleading
zero when the configured threshold exceeds the ceiling:

```python
if threshold_seconds >= ARQ_IN_PROGRESS_TIMEOUT_SECONDS:
    logger.warning(
        f"Stuck-job threshold of {threshold} minutes exceeds the "
        f"{ARQ_IN_PROGRESS_TIMEOUT_SECONDS}s lifetime of arq's in-progress "
        f"key; the stuck-job count will always be 0."
    )
```

If you need a longer stuck threshold, raise `job_timeout` first.

## F9 — the stats endpoint 500s as soon as jobs start recording

`JobTypeStats.last_execution` was typed `Optional[str]`, but it is populated
straight from `func.max(BackgroundJobExecution.started_at)` — a `datetime`.
Pydantic v2 does not coerce `datetime → str`, so the response raised a
`ValidationError` for **every job that had ever run**. Fixing F1/F2 without
this turns an empty panel into a 500.

```python
last_execution: Optional[datetime] = Field(
    None, description="Timestamp of last execution (ISO 8601 in JSON)"
)
```

Pydantic serialises the datetime to an ISO 8601 string in the JSON response, so
the client contract (nullable ISO string) is unchanged.

## F10 — the frontend rendered a failed request as "no data"

`BackgroundJobsPage` only branched on `data`, so a 500 or a 403 rendered as an
empty table and read as "idle", hiding exactly the failures this work exposes.
Add `isError`/`error` branches with a destructive `Alert` for both the queue
health and stats queries.

One trap: `detail` is not always a string. `create_http_exception` sends
`detail: { detail, detail_code }` — which is what a 403 from the super-admin
guard returns, the likeliest failure on this page. Returning that object hands
React an object as a child and crashes the very branch meant to surface the
error. Unwrap it:

```ts
const apiErrorDetail = (error: unknown): string | undefined => {
  const detail = (error as { data?: { detail?: string | { detail?: string } } } | undefined)
    ?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail.detail === 'string') return detail.detail
  return undefined
}
```

## F11 — the job-type registry is the panel's allowlist

The stats endpoint iterates `get_non_cron_job_types()` and looks up DB stats
per known code. A task that runs but is absent from `src/constants/job_types.py`
records to the database and is then **never displayed**. Every new
`@instrument_task` needs a `JobTypeDefinition` (and a category) in the same
change.

---

## Verification

Order matters — F9 only surfaces once F1/F2 are in.

1. Unit tests (no Redis/DB needed; both use stubs):
   - `test_job_metrics_recording.py` — asserts both decorators still write to
     Redis and the DB with `METRICS_ENABLED=False`, and that
     `instrument_cron_task` writes on both the success and failure paths.
   - `test_queue_health_keys.py` — asserts the exact key names and the
     PTTL→elapsed derivation, and that a finished cron (in-progress key
     present, job key absent) is not reported stuck.
2. Live check with the worker running:
   ```
   redis-cli -n <arq_db> exists "arq:<app>_backend:health-check"   # → 1
   redis-cli -n <arq_db> ttl    "arq:<app>_backend:health-check"   # → ≤ 31
   redis-cli -n <arq_db> zcard  "arq:<app>_backend"                # → queue depth
   ```
3. Stop the worker, wait ~35s, reload the panel: it must report the worker
   offline, not healthy.
4. Enqueue one job, then `select count(*) from background_job_execution;` —
   the row must appear with `METRICS_ENABLED` both true and false.
5. Reload the stats panel with at least one recorded execution — that is the
   F9 regression path.
