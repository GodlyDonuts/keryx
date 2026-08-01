from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from .models import Observation
from .normalize import canonical_url, infer_cycle, is_technical, is_us_role, job_id

_SOURCE_PRIORITY = {
    "ats": 0,
    "intern-engine": 1,
    "simplify": 2,
    "speedy": 3,
    "sndsh": 4,
}


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
        jobs[identifier] = {
            "id": identifier,
            "company": preferred.company,
            "title": preferred.title,
            "location": locations[0] if locations else "United States",
            "url": canonical_url(preferred.url),
            "program": preferred.program,
            "cycle": cycle,
            "posted_at": posted_dates[0] if posted_dates else None,
            "sponsorship": sponsorships[0] if sponsorships else None,
            "status": "open",
            "first_seen": today,
            "last_changed": today,
            "closed_at": None,
            "missed_runs": 0,
            "sources": [sources[key] for key in sorted(sources)],
        }
    return jobs


def _material(job: dict[str, Any]) -> tuple[Any, ...]:
    return (
        job.get("company"),
        job.get("title"),
        job.get("location"),
        job.get("url"),
        job.get("program"),
        job.get("cycle"),
        job.get("posted_at"),
        job.get("sponsorship"),
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
        if previous_sources and previous_sources.issubset(complete_sources):
            job["missed_runs"] = int(job.get("missed_runs", 0)) + 1
            if job["missed_runs"] >= close_after_misses and job.get("status") == "open":
                job["status"] = "closed"
                job["closed_at"] = today
                job["last_changed"] = today
        merged[identifier] = job

    return {
        "schema_version": 1,
        "country": "United States",
        "jobs": [merged[key] for key in sorted(merged)],
    }
