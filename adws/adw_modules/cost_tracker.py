"""Cost telemetry for agent invocations.

The Claude CLI writes a stream-json JSONL log to
``agents/<adw_id>/<agent_name>/raw_output.jsonl`` on every call. The final
``type=result`` message contains ``total_cost_usd``, ``duration_ms``,
``num_turns``, and a ``usage`` block with input/output token counts.

This module parses those JSONL files lazily — one parse per finished agent
call — and aggregates the numbers in-process so a workflow can:

* enforce a per-module budget cap (skip the rest of a module's retries if
  it has already burned $X), and
* print a human-readable cost summary at end-of-run.

It does NOT modify how the CLI is invoked; it just observes the artifacts.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, List, Optional


@dataclass
class AgentInvocationCost:
    """Parsed cost for a single ``execute_template`` call."""

    agent_name: str
    jsonl_path: str
    cost_usd: float = 0.0
    duration_ms: int = 0
    num_turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    parsed: bool = False
    error: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @classmethod
    def from_jsonl(cls, agent_name: str, jsonl_path: str) -> "AgentInvocationCost":
        if not os.path.exists(jsonl_path):
            return cls(
                agent_name=agent_name, jsonl_path=jsonl_path,
                error=f"jsonl missing: {jsonl_path}",
            )

        result_msg: Optional[Dict] = None
        try:
            with open(jsonl_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if msg.get("type") == "result":
                        result_msg = msg  # keep the last one
        except (IOError, OSError) as e:
            return cls(
                agent_name=agent_name, jsonl_path=jsonl_path,
                error=f"read failed: {e}",
            )

        if result_msg is None:
            return cls(
                agent_name=agent_name, jsonl_path=jsonl_path,
                error="no result message in JSONL",
            )

        usage = result_msg.get("usage", {}) or {}
        return cls(
            agent_name=agent_name,
            jsonl_path=jsonl_path,
            cost_usd=float(result_msg.get("total_cost_usd", 0.0)),
            duration_ms=int(result_msg.get("duration_ms", 0)),
            num_turns=int(result_msg.get("num_turns", 0)),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cache_creation_tokens=int(usage.get("cache_creation_input_tokens", 0)),
            cache_read_tokens=int(usage.get("cache_read_input_tokens", 0)),
            parsed=True,
        )


@dataclass
class BucketTotals:
    """Roll-up totals for a named bucket (module, phase, etc.)."""

    name: str
    cost_usd: float = 0.0
    duration_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    calls: int = 0
    # Count of invocations that DID happen but whose JSONL output couldn't
    # be parsed for cost data. Such invocations contribute 0 to cost — a
    # non-zero number here means the summary undercounts actual spend.
    unparsed_calls: int = 0

    def add(self, inv: AgentInvocationCost) -> None:
        self.cost_usd += inv.cost_usd
        self.duration_ms += inv.duration_ms
        self.input_tokens += inv.input_tokens
        self.output_tokens += inv.output_tokens
        self.cache_creation_tokens += inv.cache_creation_tokens
        self.cache_read_tokens += inv.cache_read_tokens
        self.calls += 1
        if not inv.parsed:
            self.unparsed_calls += 1

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "cost_usd": round(self.cost_usd, 4),
            "duration_ms": self.duration_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "calls": self.calls,
            "unparsed_calls": self.unparsed_calls,
        }


class CostTracker:
    """Thread-safe accumulator for agent costs.

    Designed to be instantiated once per orchestrator run and shared across
    phases. ``record_from_template_request`` is the main entry point: pass
    the same ``adw_id`` + ``agent_name`` you fed to ``execute_template`` and
    the tracker will locate the JSONL itself.
    """

    def __init__(self, project_root: Optional[str] = None) -> None:
        # RLock (not Lock) — write_summary/print_summary acquire the lock and
        # also call grand_total() which re-enters. Non-reentrant lock would deadlock.
        self._lock = RLock()
        self._buckets: Dict[str, BucketTotals] = {}
        self._invocations: List[AgentInvocationCost] = []
        if project_root is None:
            # adw_modules/cost_tracker.py is in <repo>/adws/adw_modules/
            project_root = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
        self._project_root = project_root

    def _jsonl_for(self, adw_id: str, agent_name: str) -> str:
        return os.path.join(
            self._project_root, "agents", adw_id, agent_name, "raw_output.jsonl",
        )

    def record_from_template_request(
        self,
        adw_id: str,
        agent_name: str,
        bucket: str = "default",
        logger: Optional[logging.Logger] = None,
    ) -> AgentInvocationCost:
        """Parse the agent's JSONL output and add it to the named bucket.

        ``bucket`` is the roll-up key — typically ``module_id`` for greenfield
        work, or a phase name (``"e2e_generation"``, ``"e2e_resolve"``) for
        cross-cutting work.
        """
        jsonl = self._jsonl_for(adw_id, agent_name)
        inv = AgentInvocationCost.from_jsonl(agent_name, jsonl)

        with self._lock:
            self._invocations.append(inv)
            if bucket not in self._buckets:
                self._buckets[bucket] = BucketTotals(name=bucket)
            self._buckets[bucket].add(inv)

        if logger:
            if inv.parsed:
                logger.info(
                    f"[cost] agent={agent_name} bucket={bucket} "
                    f"cost=${inv.cost_usd:.4f} tokens={inv.total_tokens} "
                    f"duration={inv.duration_ms}ms"
                )
            else:
                # WARN, not DEBUG: an unparsed invocation means our cost
                # summary will undercount actual spend. Operators need to see this.
                logger.warning(
                    f"[cost] agent={agent_name} bucket={bucket} unparsed "
                    f"(cost undercount): {inv.error}"
                )

        return inv

    def bucket_total(self, bucket: str) -> Optional[BucketTotals]:
        with self._lock:
            return self._buckets.get(bucket)

    def grand_total(self) -> BucketTotals:
        total = BucketTotals(name="GRAND_TOTAL")
        with self._lock:
            for b in self._buckets.values():
                total.cost_usd += b.cost_usd
                total.duration_ms += b.duration_ms
                total.input_tokens += b.input_tokens
                total.output_tokens += b.output_tokens
                total.cache_creation_tokens += b.cache_creation_tokens
                total.cache_read_tokens += b.cache_read_tokens
                total.calls += b.calls
                total.unparsed_calls += b.unparsed_calls
        return total

    def bucket_exceeds(self, bucket: str, *, max_usd: Optional[float] = None,
                       max_tokens: Optional[int] = None) -> bool:
        """Check if a bucket has exceeded a configured cap.

        Either cap can be None to disable. Returns True the moment EITHER cap
        is breached.
        """
        b = self.bucket_total(bucket)
        if b is None:
            return False
        if max_usd is not None and b.cost_usd >= max_usd:
            return True
        if max_tokens is not None and (b.input_tokens + b.output_tokens) >= max_tokens:
            return True
        return False

    def write_summary(self, output_path: str, adw_id: str) -> None:
        """Persist a JSON summary of all buckets and invocations."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with self._lock:
            data = {
                "adw_id": adw_id,
                "grand_total": self.grand_total().to_dict(),
                "buckets": [b.to_dict() for b in self._buckets.values()],
                "invocations": [
                    {
                        "agent_name": inv.agent_name,
                        "cost_usd": round(inv.cost_usd, 4),
                        "duration_ms": inv.duration_ms,
                        "num_turns": inv.num_turns,
                        "input_tokens": inv.input_tokens,
                        "output_tokens": inv.output_tokens,
                        "cache_creation_tokens": inv.cache_creation_tokens,
                        "cache_read_tokens": inv.cache_read_tokens,
                        "parsed": inv.parsed,
                        "error": inv.error,
                    }
                    for inv in self._invocations
                ],
            }
        with open(output_path, "w") as f:
            json.dump(data, f, indent=2)

    def print_summary(self, header: str = "Cost Summary") -> None:
        """Human-readable summary for end-of-run output."""
        with self._lock:
            buckets = sorted(self._buckets.values(), key=lambda b: -b.cost_usd)
            total = self.grand_total()

        print(f"\n--- {header} ---")
        if not buckets:
            print("  No agent invocations recorded.")
            return

        # Header line
        print(f"  {'Bucket':<40} {'Calls':>6} {'Unprs':>6} {'Cost USD':>10} {'Tokens':>10}")
        for b in buckets:
            tokens = b.input_tokens + b.output_tokens
            print(
                f"  {b.name[:40]:<40} {b.calls:>6} {b.unparsed_calls:>6} "
                f"{b.cost_usd:>10.4f} {tokens:>10}"
            )
        print(
            f"  {'TOTAL':<40} {total.calls:>6} {total.unparsed_calls:>6} "
            f"{total.cost_usd:>10.4f} {total.input_tokens + total.output_tokens:>10}"
        )
        if total.unparsed_calls:
            print(
                f"  ⚠️  {total.unparsed_calls} invocation(s) had unparseable JSONL — "
                f"cost figures undercount actual spend"
            )
