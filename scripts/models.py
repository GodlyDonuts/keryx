from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Program = Literal["internship", "new-grad"]


@dataclass(frozen=True)
class Observation:
    source_id: str
    source_label: str
    source_url: str
    external_id: str
    company: str
    title: str
    location: str
    url: str
    program: Program
    cycle: str | None = None
    posted_at: str | None = None
    sponsorship: str | None = None
    active: bool = True
    trusted_us: bool = False
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Snapshot:
    source_id: str
    observations: tuple[Observation, ...]
    complete: bool = True
