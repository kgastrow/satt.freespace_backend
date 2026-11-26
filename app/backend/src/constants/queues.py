"""
ARQ queue naming constants.

Single source of truth for the queue name and every Redis key derived from it.
Imported by the worker settings, the enqueue-side pool and the queue health
monitor so the three can never drift.

This module must not import from the rest of the application - it is imported
by low-level modules and any application import would risk a cycle.
"""

# App-specific queue name, so other ARQ workers sharing the same Redis
# instance cannot steal our jobs.
ARQ_QUEUE_NAME = "arq:ayzer_backend"

# arq writes exactly one health-check key per queue:
# queue_name + arq.constants.health_check_key_suffix
ARQ_HEALTH_CHECK_KEY = f"{ARQ_QUEUE_NAME}:health-check"

# arq's own default is 3600s - far too coarse for a liveness signal.
# arq psetex's the health-check key with TTL (interval + 1) seconds, so the
# key's existence is the freshness signal.
ARQ_HEALTH_CHECK_INTERVAL_SECONDS = 30

# arq marks a running job with `arq:in-progress:<job_id>` and stores the job
# definition (pickled) at `arq:job:<job_id>`.
ARQ_IN_PROGRESS_KEY_PREFIX = "arq:in-progress:"
ARQ_JOB_KEY_PREFIX = "arq:job:"

ARQ_JOB_TIMEOUT_SECONDS = 300

# arq psetex's the in-progress key with TTL = max_timeout + 10. A running job
# is therefore only observable for this long; past it arq has already timed the
# job out and the key is gone.
ARQ_IN_PROGRESS_TIMEOUT_SECONDS = ARQ_JOB_TIMEOUT_SECONDS + 10
