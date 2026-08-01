from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

JobStatus = Literal["open", "closed"]
EventType = Literal["opened", "reopened", "closed"]


@dataclass(frozen=True)
class Observation:
    """One source's current statement about a public role."""

    source: str
    external_id: str
    company: str
    title: str
    url: str
    locations: tuple[str, ...] = ()
    category: str | None = None
    cycles: tuple[str, ...] = ()
    posted_at: str | None = None
    remote: bool | None = None
    sponsorship: str | None = None
    active: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceSnapshot:
    """A provider response and whether absence is meaningful."""

    source: str
    observations: tuple[Observation, ...]
    complete: bool = True


@dataclass(frozen=True)
class SyncEvent:
    event_id: str
    event_type: EventType
    job_id: str
    occurred_at: str
    job: dict[str, Any]


@dataclass(frozen=True)
class SyncResult:
    baseline: bool
    jobs: tuple[dict[str, Any], ...]
    events: tuple[SyncEvent, ...]
    event_history: tuple[SyncEvent, ...]
    source_counts: dict[str, int]
    errors: dict[str, str]
