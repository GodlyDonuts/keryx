from __future__ import annotations

import hashlib
from collections import defaultdict
from copy import deepcopy
from typing import Any

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
from .qualifications import ACADEMIC_EXTRACTOR_VERSION, classify_academic_eligibility

_SOURCE_PRIORITY = {
    "ats": 0,
    "intern-engine": 1,
    "simplify": 2,
    "speedy": 3,
    "sndsh": 4,
}
_REQUIREMENT_LEVELS = {"required", "preferred", "stated"}


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


def _source(observation: Observation) -> dict[str, str]:
    return {
        "id": observation.source_id,
        "label": observation.source_label,
        "url": observation.source_url,
    }


def _link_status(sources: list[dict[str, str]], url: str) -> str:
    if not url:
        return "unverified"
    source_ids = {str(source.get("id", "")) for source in sources}
    if any(source_id.startswith("ats:") for source_id in source_ids):
        return "ats-verified"
    if len(source_ids) >= 2:
        return "cross-source"
    if is_recruiting_platform_url(url):
        return "platform-structured"
    return "source-reported"


def _protect_link(job: dict[str, Any], sources: list[dict[str, str]], raw_url: str) -> None:
    decision = sanitize_job_url(raw_url)
    status = _link_status(sources, decision.url)
    job["url_host"] = decision.host
    job["url_fingerprint"] = hashlib.sha256(decision.url.encode("utf-8")).hexdigest()[:24]
    job["link_status"] = status
    job["url"] = decision.url if status != "unverified" else None


def _current_jobs(observations: list[Observation], today: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        if eligible(observation):
            grouped[job_id(observation)].append(observation)

    jobs: dict[str, dict[str, Any]] = {}
    for identifier, group in grouped.items():
        ordered = sorted(group, key=_priority)
        preferred = ordered[0]
        locations = [item.location for item in ordered if item.location]
        posted_dates = sorted(item.posted_at for item in ordered if item.posted_at)
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
        sources = {_source(item)["id"]: _source(item) for item in ordered}
        source_list = [sources[key] for key in sorted(sources)]
        academic_eligibility = classify_academic_eligibility(ordered)
        if academic_eligibility.get("status") != "unavailable":
            academic_eligibility["checked_at"] = today
        jobs[identifier] = {
            "id": identifier,
            "company": preferred.company,
            "title": preferred.title,
            "location": locations[0] if locations else "United States",
            "program": preferred.program,
            "cycle": cycle,
            "posted_at": posted_dates[0] if posted_dates else None,
            "sponsorship": sponsorships[0] if sponsorships else None,
            "academic_eligibility": academic_eligibility,
            "status": "open",
            "first_seen": today,
            "last_changed": today,
            "closed_at": None,
            "missed_runs": 0,
            "sources": source_list,
            "_candidate_url": preferred.url,
        }
        _protect_link(jobs[identifier], source_list, preferred.url)
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
        job.get("status"),
    )


def merge_state(
    previous_payload: dict[str, Any],
    observations: list[Observation],
    *,
    complete_sources: set[str],
    today: str,
    close_after_misses: int = 2,
) -> dict[str, Any]:
    previous_jobs = {
        str(job["id"]): deepcopy(job)
        for job in previous_payload.get("jobs", [])
        if isinstance(job, dict) and job.get("id")
    }
    current = _current_jobs(observations, today)
    merged: dict[str, dict[str, Any]] = {}

    for identifier, job in current.items():
        previous = previous_jobs.get(identifier)
        if previous is None:
            merged[identifier] = job
            continue
        known_sources = {
            source["id"]: source
            for source in previous.get("sources", [])
            if isinstance(source, dict) and source.get("id")
        }
        for source in job["sources"]:
            known_sources[source["id"]] = source
        job["sources"] = [known_sources[key] for key in sorted(known_sources)]
        raw_url = str(job.get("_candidate_url") or job.get("url") or previous.get("url") or "")
        _protect_link(job, job["sources"], raw_url)
        current_eligibility = job.get("academic_eligibility")
        if (
            isinstance(current_eligibility, dict)
            and current_eligibility.get("status") == "unavailable"
            and _has_current_eligibility_schema(previous.get("academic_eligibility"))
        ):
            # Direct boards are intentionally polled in rotating slots. Do not erase previously
            # verified requirements merely because this run saw only metadata-only sources.
            job["academic_eligibility"] = deepcopy(previous["academic_eligibility"])
        job["first_seen"] = previous.get("first_seen") or today
        job["last_changed"] = (
            today
            if _material(job) != _material(previous)
            else previous.get("last_changed") or today
        )
        merged[identifier] = job

    for identifier, previous in previous_jobs.items():
        if identifier in merged:
            continue
        previous_sources = {
            str(source.get("id"))
            for source in previous.get("sources", [])
            if isinstance(source, dict) and source.get("id")
        }
        job = deepcopy(previous)
        # Link-safety failures are not ordinary source misses: unsafe links must disappear
        # immediately rather than remain clickable through the two-run closure grace period.
        previous_url = job.get("url")
        previous_source_list = [
            source for source in job.get("sources", []) if isinstance(source, dict)
        ]
        if isinstance(previous_url, str) and previous_url:
            sanitized_previous = sanitize_job_url(previous_url)
            if not sanitized_previous.url:
                continue
            _protect_link(job, previous_source_list, sanitized_previous.url)
        elif job.get("link_status") != "unverified":
            continue
        if previous_sources and previous_sources.issubset(complete_sources):
            job["missed_runs"] = int(job.get("missed_runs", 0)) + 1
            if job["missed_runs"] >= close_after_misses and job.get("status") == "open":
                job["status"] = "closed"
                job["closed_at"] = today
                job["last_changed"] = today
        merged[identifier] = job

    for job in merged.values():
        job.pop("_candidate_url", None)
        if not _has_current_eligibility_schema(job.get("academic_eligibility")):
            job["academic_eligibility"] = {
                "extractor_version": ACADEMIC_EXTRACTOR_VERSION,
                "status": "unavailable",
                "summary": "Posting text unavailable",
                "confidence": "metadata-only",
            }

    return {
        "schema_version": 2,
        "country": "United States",
        "jobs": [merged[key] for key in sorted(merged)],
    }
