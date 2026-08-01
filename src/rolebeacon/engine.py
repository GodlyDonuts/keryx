from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import asdict
from typing import Any

from .canonical import canonical_url, job_identity
from .models import SourceSnapshot, SyncEvent, SyncResult

_MAX_RECENT_EVENTS = 1_000


def _event(event_type: str, job: dict[str, Any], now: str) -> SyncEvent:
    event_id = hashlib.sha256(f"{event_type}:{job['id']}:{now}".encode()).hexdigest()[:24]
    return SyncEvent(
        event_id=f"evt_{event_id}",
        event_type=event_type,  # type: ignore[arg-type]
        job_id=str(job["id"]),
        occurred_at=now,
        job=deepcopy(job),
    )


def _new_job(observation: Any, identity: str, now: str) -> dict[str, Any]:
    return {
        "id": identity,
        "company": observation.company,
        "title": observation.title,
        "url": canonical_url(observation.url) or observation.url,
        "locations": list(observation.locations),
        "category": observation.category,
        "cycles": list(observation.cycles),
        "posted_at": observation.posted_at,
        "remote": observation.remote,
        "sponsorship": observation.sponsorship,
        "status": "open" if observation.active else "closed",
        "first_seen_at": now,
        "last_seen_at": now,
        "closed_at": None if observation.active else now,
        "sources": {},
    }


def synchronize(
    state: dict[str, Any],
    snapshots: tuple[SourceSnapshot, ...],
    *,
    now: str,
    close_after_misses: int,
    errors: dict[str, str] | None = None,
) -> tuple[dict[str, Any], SyncResult]:
    """Merge complete source snapshots into state without alerting on the first baseline."""
    updated = deepcopy(state)
    jobs: dict[str, dict[str, Any]] = updated["jobs"]
    baseline = updated.get("initialized_at") is None
    events: list[SyncEvent] = []
    source_counts: dict[str, int] = {}

    for snapshot in snapshots:
        seen: set[str] = set()
        source_counts[snapshot.source] = len(snapshot.observations)
        for observation in snapshot.observations:
            identity = job_identity(
                url=observation.url,
                source=observation.source,
                external_id=observation.external_id,
            )
            seen.add(identity)
            existed = identity in jobs
            if not existed and not observation.active:
                # Historical closed records are not useful until RoleBeacon has observed them open.
                continue
            job = jobs.setdefault(identity, _new_job(observation, identity, now))
            previous_status = job["status"]
            source = job["sources"].setdefault(
                snapshot.source,
                {
                    "external_id": observation.external_id,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "miss_count": 0,
                    "active": observation.active,
                    "url": observation.url,
                    "metadata": observation.metadata,
                },
            )
            source.update(
                {
                    "external_id": observation.external_id,
                    "last_seen_at": now,
                    "miss_count": 0,
                    "active": observation.active,
                    "url": observation.url,
                    "metadata": observation.metadata,
                }
            )
            job.update(
                {
                    "company": observation.company,
                    "title": observation.title,
                    "url": canonical_url(observation.url) or observation.url,
                    "locations": list(observation.locations),
                    "category": observation.category,
                    "cycles": list(observation.cycles),
                    "posted_at": observation.posted_at or job.get("posted_at"),
                    "remote": observation.remote,
                    "sponsorship": observation.sponsorship,
                    "last_seen_at": now,
                }
            )
            job["status"] = (
                "open" if any(item["active"] for item in job["sources"].values()) else "closed"
            )
            job["closed_at"] = None if job["status"] == "open" else job.get("closed_at") or now
            if not baseline:
                if job["status"] == "open":
                    if not existed:
                        events.append(_event("opened", job, now))
                    elif previous_status == "closed":
                        events.append(_event("reopened", job, now))
                elif existed and previous_status == "open":
                    events.append(_event("closed", job, now))

        if snapshot.complete:
            for job in jobs.values():
                source = job["sources"].get(snapshot.source)
                if source is None or job["id"] in seen or not source["active"]:
                    continue
                source["miss_count"] += 1
                if source["miss_count"] >= close_after_misses:
                    previous_status = job["status"]
                    source["active"] = False
                    job["status"] = (
                        "open"
                        if any(item["active"] for item in job["sources"].values())
                        else "closed"
                    )
                    if previous_status == "open" and job["status"] == "closed":
                        job["closed_at"] = now
                        if not baseline:
                            events.append(_event("closed", job, now))

    updated["initialized_at"] = updated.get("initialized_at") or now
    updated["last_sync_at"] = now
    event_values = [*updated.get("recent_events", []), *event_dicts(tuple(events))]
    updated["recent_events"] = event_values[-_MAX_RECENT_EVENTS:]
    event_history = tuple(SyncEvent(**value) for value in updated["recent_events"])
    ordered_jobs = tuple(sorted(jobs.values(), key=lambda job: (job["company"], job["title"])))
    return updated, SyncResult(
        baseline=baseline,
        jobs=ordered_jobs,
        events=tuple(events),
        event_history=event_history,
        source_counts=source_counts,
        errors=errors or {},
    )


def event_dicts(events: tuple[SyncEvent, ...]) -> list[dict[str, Any]]:
    return [asdict(event) for event in events]
