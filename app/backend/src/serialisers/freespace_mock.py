"""Wire models for the mock / demonstration endpoints (BF-84). OWNER: M10."""

from __future__ import annotations

from datetime import datetime
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from src.serialisers.freespace_ingest import IngestOccupancyRequest


# One request may move the clock by at most 30 days (guards float overflow and
# typos; a demo needs minutes to hours).
MAX_CLOCK_ADVANCE_SECONDS = 30 * 24 * 3600


class MockOccupancyRequest(IngestOccupancyRequest):
    """Same body as ``POST /v1/ingest/occupancy``; ``measuredAt`` is optional
    and defaults to the mock clock's now."""

    measured_at: datetime | None = None  # type: ignore[assignment]


class _MockOut(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MockClockRequest(BaseModel):
    """``POST /mock/clock`` body: advance by ``seconds`` OR set ``reset``."""

    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="forbid"
    )

    seconds: float | None = Field(default=None, ge=0, le=MAX_CLOCK_ADVANCE_SECONDS)
    reset: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> MockClockRequest:
        if self.seconds is not None and not math.isfinite(self.seconds):
            raise ValueError("seconds must be finite")
        if self.reset == (self.seconds is not None):
            raise ValueError("send either 'seconds' (advance) or 'reset': true")
        return self


class MockTickSummary(_MockOut):
    """Outcome of the inline engine tick run after a clock change."""

    ran: bool
    sites_evaluated: int = 0
    sites_failed: int = 0
    fanouts_enqueued: int = 0


class MockClockResponse(_MockOut):
    """New mock time after ``POST /mock/clock``."""

    mock_time: str
    offset_seconds: float
    tick: MockTickSummary


class MockStatusResponse(_MockOut):
    """``GET /mock/status``."""

    mock_mode: bool = True
    mock_time: str
    offset_seconds: float
