from __future__ import annotations

import hashlib
from collections import defaultdict
from copy import deepcopy
from typing import Any

from .intelligence import (
    INTELLIGENCE_EXTRACTOR_VERSION,
    build_job_intelligence,
    visa_compatibility_value,
)
from .models import Observation
from .normalize import (
    canonical_url,
    infer_cycle,
    is_recruiting_platform_url,
    is_technical,
    is_us_role,
    job_id,
    sanitize_job_url,
)
from .provenance import (
    normalize_observed_at,
    partial_observation_is_fresh,
    source_is_fresh,
    source_outcome,
)
from .qualifications import ACADEMIC_EXTRACTOR_VERSION, classify_academic_eligibility

_SOURCE_PRIORITY = {
    "ats": 0,
    "intern-engine": 1,
    "simplify": 2,
    "speedy": 3,
    "sndsh": 4,
}
_REQUIREMENT_LEVELS = {"required", "preferred", "stated"}
_INTELLIGENCE_TEXT_STATUSES = {"checked", "metadata-only", "unavailable"}


def _has_current_eligibility_schema(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("extractor_version") != ACADEMIC_EXTRACTOR_VERSION:
        return False
    status = str(value.get("status") or "")
    if status != "unavailable" and not isinstance(value.get("checked_at"), str):
        return False
    if status.startswith("explicit-") and value.get("requirement_level") not in _REQUIREMENT_LEVELS:
        return False
    if (
        value.get("currently_enrolled")
        and value.get("currently_enrolled_level") not in _REQUIREMENT_LEVELS
    ):
        return False
    if (
        value.get("return_to_school")
        and value.get("return_to_school_level") not in _REQUIREMENT_LEVELS
    ):
        return False
    return status in {"not-found", "unavailable", "student-status"} or status.startswith(
        "explicit-"
    )


def _has_current_intelligence_schema(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("extractor_version") != INTELLIGENCE_EXTRACTOR_VERSION:
        return False
    if value.get("text_status") not in _INTELLIGENCE_TEXT_STATUSES:
        return False
    return (
        isinstance(value.get("category"), str)
        and isinstance(value.get("skills"), list)
        and (value.get("workplace") is None or isinstance(value.get("workplace"), dict))
        and (value.get("visa") is None or isinstance(value.get("visa"), dict))
    )


def _unavailable_intelligence() -> dict[str, Any]:
    return {
        "extractor_version": INTELLIGENCE_EXTRACTOR_VERSION,
        "text_status": "unavailable",
        "category": "other-tech",
        "skills": [],
    }


def _intelligence_source_ids(value: dict[str, Any]) -> set[str]:
    source_ids = {
        str(value[field])
        for field in ("category_source_id", "skills_source_id")
        if value.get(field)
    }
    for field in ("compensation", "workplace", "visa", "h1b_history"):
        record = value.get(field)
        if isinstance(record, dict) and record.get("source_id"):
            source_ids.add(str(record["source_id"]))
    return source_ids


def _preserve_verified_intelligence(
    current: object,
    previous: object,
    *,
    current_source_ids: set[str],
) -> object:
    if not _has_current_intelligence_schema(current):
        return previous if _has_current_intelligence_schema(previous) else current
    if not _has_current_intelligence_schema(previous):
        return current
    assert isinstance(current, dict)
    assert isinstance(previous, dict)
    if current.get("text_status") == "checked" or previous.get("text_status") != "checked":
        return current
    previous_source_ids = _intelligence_source_ids(previous)
    if not previous_source_ids or not previous_source_ids.issubset(current_source_ids):
        return current
    # Direct boards are polled in rotating slots. A metadata-only run must not erase a prior
    # source-text classification while all of its evidence sources remain current. Historical
    # evidence is never carried into the active intelligence view.
    preserved = deepcopy(previous)
    if current.get("h1b_history") is not None:
        preserved["h1b_history"] = deepcopy(current["h1b_history"])
    return preserved


def eligible(observation: Observation) -> bool:
    return (
        observation.active
        and bool(canonical_url(observation.url))
        and is_us_role(
            observation.location,
            trusted_us=observation.trusted_us,
            context=f"{observation.title} {observation.url}",
        )
        and is_technical(observation.title, observation.description)
    )


def _priority(observation: Observation) -> int:
    prefix = observation.source_id.split(":", 1)[0].split("-", 1)[0]
    return _SOURCE_PRIORITY.get(prefix, 10)


def _source(
    observation: Observation,
    observed_at: str,
    source_health: object,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "id": observation.source_id,
        "label": observation.source_label,
        "url": observation.source_url,
        "state": "active",
        "first_seen_at": observed_at,
        "state_changed_at": observed_at,
    }
    if source_outcome(observation.source_id, source_health) == "partial":
        value["last_observed_at"] = observed_at
    return value


def _link_status(source_ids: set[str], url: str) -> str:
    if any(source_id.startswith("ats:") for source_id in source_ids):
        return "ats-verified"
    if len(source_ids) >= 2:
        return "cross-source"
    if is_recruiting_platform_url(url):
        return "platform-structured"
    return "unverified"


def _effective_source_ids(
    sources: list[dict[str, Any]],
    current_source_ids: set[str],
    source_health: object,
    *,
    observed_at: str,
) -> set[str]:
    effective = set(current_source_ids)
    for source in sources:
        source_id = str(source.get("id") or "")
        if source.get("state") == "active" and (
            source_is_fresh(source_id, source_health, as_of=observed_at)
            or partial_observation_is_fresh(source, as_of=observed_at)
        ):
            effective.add(source_id)
    return effective


def _source_views(job: dict[str, Any], effective_source_ids: set[str]) -> None:
    all_source_ids = {
        str(source.get("id"))
        for source in job.get("sources", [])
        if isinstance(source, dict) and source.get("id")
    }
    historical = all_source_ids - effective_source_ids
    job["current_source_ids"] = sorted(effective_source_ids)
    job["historical_source_ids"] = sorted(historical)
    job["previously_ats_observed"] = any(source_id.startswith("ats:") for source_id in historical)


def _protect_link(
    job: dict[str, Any],
    sources: list[dict[str, Any]],
    raw_url: str,
    *,
    current_source_ids: set[str],
    source_health: object,
    observed_at: str,
) -> None:
    decision = sanitize_job_url(raw_url)
    effective_source_ids = _effective_source_ids(
        sources,
        current_source_ids,
        source_health,
        observed_at=observed_at,
    )
    status = _link_status(effective_source_ids, decision.url)
    job["url_host"] = decision.host
    job["url_fingerprint"] = hashlib.sha256(decision.url.encode("utf-8")).hexdigest()[:24]
    job["link_status"] = status
    job["url"] = decision.url if status != "unverified" else None
    _source_views(job, effective_source_ids)


def _merge_sources(
    previous: object,
    current: list[dict[str, Any]],
    *,
    complete_sources: set[str],
    observed_at: str,
) -> list[dict[str, Any]]:
    known: dict[str, dict[str, Any]] = {}
    if isinstance(previous, list):
        for value in previous:
            if not isinstance(value, dict) or not value.get("id"):
                continue
            source = deepcopy(value)
            source.setdefault("state", "historical")
            source.setdefault("first_seen_at", observed_at)
            source.setdefault("state_changed_at", observed_at)
            known[str(source["id"])] = source
    current_ids = {str(source["id"]) for source in current}
    for source in current:
        source_id = str(source["id"])
        prior = known.get(source_id)
        if prior is not None:
            source["first_seen_at"] = prior.get("first_seen_at") or observed_at
            if prior.get("state") == "active":
                source["state_changed_at"] = prior.get("state_changed_at") or observed_at
        known[source_id] = source
    for source_id, source in known.items():
        if source_id in current_ids or source_id not in complete_sources:
            continue
        if source.get("state") != "historical":
            source["state"] = "historical"
            source["state_changed_at"] = observed_at
    return [known[key] for key in sorted(known)]


def _field_evidence(observations: list[Observation]) -> tuple[dict[str, str], dict[str, Any]]:
    preferred = observations[0]
    selected: dict[str, tuple[object, Observation]] = {
        "company": (preferred.company, preferred),
        "title": (preferred.title, preferred),
        "location": (preferred.location or "United States", preferred),
        "application_url": (canonical_url(preferred.url), preferred),
    }
    posted = next((item for item in observations if item.posted_at), None)
    if posted is not None:
        selected["posted_at"] = (posted.posted_at, posted)
    field_sources = {field: item.source_id for field, (_, item) in selected.items()}
    conflicts: dict[str, Any] = {}
    for field, (selected_value, _) in selected.items():
        attribute = "url" if field == "application_url" else field
        alternatives = []
        seen = {str(selected_value)}
        for item in observations:
            raw = getattr(item, attribute)
            value = canonical_url(raw) if field == "application_url" else raw
            if value is None or str(value) in seen:
                continue
            seen.add(str(value))
            alternatives.append({"value": value, "source_id": item.source_id})
        if alternatives:
            conflicts[field] = alternatives[:8]
    return field_sources, conflicts


def _current_jobs(
    observations: list[Observation],
    *,
    observed_at: str,
    source_health: object,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        if eligible(observation):
            grouped[job_id(observation)].append(observation)

    jobs: dict[str, dict[str, Any]] = {}
    for identifier, group in grouped.items():
        ordered = sorted(group, key=_priority)
        preferred = ordered[0]
        locations = [item.location for item in ordered if item.location]
        posted_source = next((item for item in ordered if item.posted_at), None)
        sponsorships = [
            item.sponsorship
            for item in ordered
            if item.sponsorship and item.sponsorship.casefold() not in {"unknown", "other"}
        ]
        cycle = infer_cycle(
            title=preferred.title,
            description=" ".join(item.description for item in ordered),
            program=preferred.program,
            hint=next((item.cycle for item in ordered if item.cycle), None),
        )
        sources = {
            _source(item, observed_at, source_health)["id"]: _source(
                item, observed_at, source_health
            )
            for item in ordered
        }
        source_list = [sources[key] for key in sorted(sources)]
        current_source_ids = set(sources)
        field_sources, field_conflicts = _field_evidence(ordered)
        academic_eligibility = classify_academic_eligibility(ordered)
        if academic_eligibility.get("status") != "unavailable":
            academic_eligibility["checked_at"] = observed_at
        intelligence = build_job_intelligence(ordered, checked_at=observed_at)
        compatible_sponsorship = visa_compatibility_value(intelligence)
        jobs[identifier] = {
            "id": identifier,
            "company": preferred.company,
            "title": preferred.title,
            "location": locations[0] if locations else "United States",
            "program": preferred.program,
            "cycle": cycle,
            "posted_at": posted_source.posted_at if posted_source is not None else None,
            "sponsorship": compatible_sponsorship or (sponsorships[0] if sponsorships else None),
            "academic_eligibility": academic_eligibility,
            "intelligence": intelligence,
            "status": "open",
            "lifecycle_state": "new",
            "first_seen": observed_at[:10],
            "first_seen_at": observed_at,
            "last_changed": observed_at[:10],
            "last_changed_at": observed_at,
            "closed_at": None,
            "missed_runs": 0,
            "sources": source_list,
            "field_sources": field_sources,
            "field_conflicts": field_conflicts,
            "_candidate_url": preferred.url,
        }
        _protect_link(
            jobs[identifier],
            source_list,
            preferred.url,
            current_source_ids=current_source_ids,
            source_health=source_health,
            observed_at=observed_at,
        )
    return jobs


def _material(job: dict[str, Any]) -> tuple[Any, ...]:
    return (
        job.get("company"),
        job.get("title"),
        job.get("location"),
        job.get("url"),
        job.get("link_status"),
        job.get("program"),
        job.get("cycle"),
        job.get("posted_at"),
        job.get("sponsorship"),
        job.get("academic_eligibility"),
        job.get("sources"),
        job.get("current_source_ids"),
        job.get("historical_source_ids"),
        job.get("field_sources"),
        job.get("field_conflicts"),
        job.get("lifecycle_state"),
        job.get("intelligence"),
        job.get("status"),
    )


def merge_state(
    previous_payload: dict[str, Any],
    observations: list[Observation],
    *,
    complete_sources: set[str],
    observed_at: str | None = None,
    today: str | None = None,
    source_health: object = None,
    close_after_misses: int = 2,
) -> dict[str, Any]:
    checked_at = normalize_observed_at(observed_at=observed_at, today=today)
    day = checked_at[:10]
    previous_jobs = {
        str(job["id"]): deepcopy(job)
        for job in previous_payload.get("jobs", [])
        if isinstance(job, dict) and job.get("id")
    }
    current = _current_jobs(
        observations,
        observed_at=checked_at,
        source_health=source_health,
    )
    merged: dict[str, dict[str, Any]] = {}

    for identifier, job in current.items():
        previous = previous_jobs.get(identifier)
        if previous is None:
            merged[identifier] = job
            continue
        current_source_ids = {
            str(source.get("id"))
            for source in job["sources"]
            if isinstance(source, dict) and source.get("id")
        }
        job["sources"] = _merge_sources(
            previous.get("sources"),
            job["sources"],
            complete_sources=complete_sources,
            observed_at=checked_at,
        )
        _source_views(
            job,
            _effective_source_ids(
                job["sources"],
                set(),
                source_health,
                observed_at=checked_at,
            ),
        )
        raw_url = str(job.get("_candidate_url") or job.get("url") or previous.get("url") or "")
        _protect_link(
            job,
            job["sources"],
            raw_url,
            current_source_ids=current_source_ids,
            source_health=source_health,
            observed_at=checked_at,
        )
        current_eligibility = job.get("academic_eligibility")
        if (
            isinstance(current_eligibility, dict)
            and current_eligibility.get("status") == "unavailable"
            and _has_current_eligibility_schema(previous.get("academic_eligibility"))
            and previous.get("academic_eligibility", {}).get("source_id")
            in job["current_source_ids"]
        ):
            # Direct boards are intentionally polled in rotating slots. Do not erase previously
            # verified requirements merely because this run saw only metadata-only sources.
            job["academic_eligibility"] = deepcopy(previous["academic_eligibility"])
        job["intelligence"] = _preserve_verified_intelligence(
            job.get("intelligence"),
            previous.get("intelligence"),
            current_source_ids=set(job["current_source_ids"]),
        )
        compatible_sponsorship = visa_compatibility_value(job["intelligence"])
        if compatible_sponsorship:
            job["sponsorship"] = compatible_sponsorship
        job["first_seen"] = previous.get("first_seen") or day
        job["first_seen_at"] = previous.get("first_seen_at") or (
            f"{previous['first_seen']}T00:00:00Z" if previous.get("first_seen") else checked_at
        )
        job["missed_runs"] = 0
        job.pop("closure_source_ids", None)
        job["closed_at"] = None
        job["lifecycle_state"] = "reopened" if previous.get("status") == "closed" else "open"
        changed = _material(job) != _material(previous)
        job["last_changed"] = day if changed else previous.get("last_changed") or day
        job["last_changed_at"] = (
            checked_at
            if changed
            else previous.get("last_changed_at")
            or (
                f"{previous['last_changed']}T00:00:00Z"
                if previous.get("last_changed")
                else checked_at
            )
        )
        merged[identifier] = job

    for identifier, previous in previous_jobs.items():
        if identifier in merged:
            continue
        previous_active_sources = {
            str(source.get("id"))
            for source in previous.get("sources", [])
            if isinstance(source, dict)
            and source.get("id")
            and source.get("state", "active") == "active"
        }
        job = deepcopy(previous)
        # Link-safety failures are not ordinary source misses: unsafe links must disappear
        # immediately rather than remain clickable through the two-run closure grace period.
        previous_url = job.get("url")
        previous_source_list: list[dict[str, Any]] = [
            source for source in job.get("sources", []) if isinstance(source, dict)
        ]
        job["sources"] = _merge_sources(
            previous_source_list,
            [],
            complete_sources=complete_sources,
            observed_at=checked_at,
        )
        if isinstance(previous_url, str) and previous_url:
            sanitized_previous = sanitize_job_url(previous_url)
            if not sanitized_previous.url:
                continue
            _protect_link(
                job,
                job["sources"],
                sanitized_previous.url,
                current_source_ids=set(),
                source_health=source_health,
                observed_at=checked_at,
            )
        elif job.get("link_status") != "unverified":
            continue
        closure_sources = {
            str(source_id) for source_id in previous.get("closure_source_ids", [])
        } or previous_active_sources
        if closure_sources and closure_sources.issubset(complete_sources):
            job["missed_runs"] = int(job.get("missed_runs", 0)) + 1
            job["closure_source_ids"] = sorted(closure_sources)
            if job["missed_runs"] >= close_after_misses and job.get("status") == "open":
                job["status"] = "closed"
                job["lifecycle_state"] = "closed"
                job["closed_at"] = day
                job["closed_at_timestamp"] = checked_at
                job["last_changed"] = day
                job["last_changed_at"] = checked_at
                job.pop("closure_source_ids", None)
            elif job.get("status") == "open":
                job["lifecycle_state"] = "closing-unconfirmed"
                job["last_changed"] = day
                job["last_changed_at"] = checked_at
        elif job.get("status") == "open" and not job.get("current_source_ids"):
            job["lifecycle_state"] = "stale"
        merged[identifier] = job

    for job in merged.values():
        job.pop("_candidate_url", None)
        job.setdefault(
            "first_seen_at",
            f"{job['first_seen']}T00:00:00Z" if job.get("first_seen") else checked_at,
        )
        job.setdefault(
            "last_changed_at",
            f"{job['last_changed']}T00:00:00Z" if job.get("last_changed") else checked_at,
        )
        job.setdefault("lifecycle_state", "closed" if job.get("status") == "closed" else "open")
        job.setdefault("current_source_ids", [])
        job.setdefault(
            "historical_source_ids",
            sorted(
                str(source.get("id"))
                for source in job.get("sources", [])
                if isinstance(source, dict) and source.get("id")
            ),
        )
        job.setdefault(
            "previously_ats_observed",
            any(
                str(source_id).startswith("ats:")
                for source_id in job.get("historical_source_ids", [])
            ),
        )
        if not _has_current_eligibility_schema(job.get("academic_eligibility")):
            job["academic_eligibility"] = {
                "extractor_version": ACADEMIC_EXTRACTOR_VERSION,
                "status": "unavailable",
                "summary": "Posting text unavailable",
                "confidence": "metadata-only",
            }
        if not _has_current_intelligence_schema(job.get("intelligence")):
            job["intelligence"] = _unavailable_intelligence()

    return {
        "schema_version": 3,
        "country": "United States",
        "jobs": [merged[key] for key in sorted(merged)],
    }
