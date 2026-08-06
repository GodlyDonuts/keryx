from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import Snapshot

SOURCE_HEALTH_SCHEMA_VERSION = 1
_DIRECT_FRESHNESS = timedelta(hours=2)
_UPSTREAM_FRESHNESS = timedelta(minutes=45)


def parse_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def utc_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_observed_at(*, observed_at: str | None, today: str | None) -> str:
    if observed_at is None:
        if today is None:
            raise ValueError("observed_at is required")
        observed_at = f"{today}T00:00:00Z"
    parsed = parse_utc_timestamp(observed_at)
    if parsed is None:
        raise ValueError("observed_at must be an ISO-8601 UTC timestamp")
    return utc_timestamp(parsed)


def update_source_health(
    previous: object,
    snapshots: tuple[Snapshot, ...],
    errors: dict[str, str],
    *,
    checked_at: str,
) -> dict[str, Any]:
    if parse_utc_timestamp(checked_at) is None:
        raise ValueError("source-health check time must be an ISO-8601 timestamp")
    previous_sources = previous.get("sources", {}) if isinstance(previous, dict) else {}
    sources = deepcopy(previous_sources) if isinstance(previous_sources, dict) else {}
    for snapshot in snapshots:
        prior = sources.get(snapshot.source_id)
        record = deepcopy(prior) if isinstance(prior, dict) else {"source_id": snapshot.source_id}
        record.update(
            {
                "source_id": snapshot.source_id,
                "outcome": "complete" if snapshot.complete else "partial",
                "last_attempt_at": checked_at,
                "last_success_at": checked_at,
                "records_seen": len(snapshot.observations),
            }
        )
        if snapshot.complete:
            record["last_complete_at"] = checked_at
        sources[snapshot.source_id] = record
    for source_id in errors:
        prior = sources.get(source_id)
        record = deepcopy(prior) if isinstance(prior, dict) else {"source_id": source_id}
        record.update(
            {
                "source_id": source_id,
                "outcome": "failed",
                "last_attempt_at": checked_at,
            }
        )
        sources[source_id] = record
    return {
        "schema_version": SOURCE_HEALTH_SCHEMA_VERSION,
        "generated_at": checked_at,
        "sources": {key: sources[key] for key in sorted(sources)},
    }


def source_is_fresh(source_id: str, source_health: object, *, as_of: str) -> bool:
    now = parse_utc_timestamp(as_of)
    if now is None or not isinstance(source_health, dict):
        return False
    records = source_health.get("sources")
    if not isinstance(records, dict):
        return False
    record = records.get(source_id)
    if not isinstance(record, dict) or record.get("outcome") != "complete":
        return False
    last_success = parse_utc_timestamp(record.get("last_success_at"))
    if last_success is None or last_success > now:
        return False
    threshold = _DIRECT_FRESHNESS if source_id.startswith("ats:") else _UPSTREAM_FRESHNESS
    return now - last_success <= threshold


def source_outcome(source_id: str, source_health: object) -> str | None:
    if not isinstance(source_health, dict) or not isinstance(source_health.get("sources"), dict):
        return None
    record = source_health["sources"].get(source_id)
    return str(record.get("outcome")) if isinstance(record, dict) else None


def partial_observation_is_fresh(source: object, *, as_of: str) -> bool:
    if not isinstance(source, dict):
        return False
    source_id = str(source.get("id") or "")
    observed = parse_utc_timestamp(source.get("last_observed_at"))
    now = parse_utc_timestamp(as_of)
    if observed is None or now is None or observed > now:
        return False
    threshold = _DIRECT_FRESHNESS if source_id.startswith("ats:") else _UPSTREAM_FRESHNESS
    return now - observed <= threshold


def latest_verification_at(
    source_ids: set[str],
    source_health: object,
    *,
    as_of: str,
) -> str | None:
    if not isinstance(source_health, dict):
        return None
    records = source_health.get("sources")
    if not isinstance(records, dict):
        return None
    values = []
    for source_id in source_ids:
        if not source_is_fresh(source_id, source_health, as_of=as_of):
            continue
        record = records.get(source_id)
        if isinstance(record, dict) and isinstance(record.get("last_success_at"), str):
            values.append(record["last_success_at"])
    return max(values, default=None)
