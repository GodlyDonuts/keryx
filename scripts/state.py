from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from copy import deepcopy
from typing import Any

from .discovery import company_key
from .models import Observation
from .normalize import (
    infer_cycle,
    is_recruiting_platform_url,
    is_technical,
    is_us_role,
    job_id,
    reported_job_url,
)
from .qualifications import ACADEMIC_EXTRACTOR_VERSION, classify_academic_eligibility

_SOURCE_PRIORITY = {
    "ats": 0,
    "intern-engine": 1,
    "simplify": 2,
    "speedy": 3,
    "sndsh": 4,
    "jobright": 5,
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
        and bool(reported_job_url(observation.url).url)
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


def _content_key_values(company: object, title: object, location: object) -> tuple[str, str, str]:
    def normalize(value: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())

    return (
        normalize(str(company or "")),
        normalize(str(title or "")),
        normalize(str(location or "")),
    )


def _match_key_values(company: object, title: object, location: object) -> tuple[str, str, str]:
    def normalize(value: str) -> str:
        return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())

    normalized_location = re.sub(
        r"\b(?:united states(?: of america)?|u\.?s\.?a\.?)\b",
        " ",
        str(location or ""),
        flags=re.IGNORECASE,
    )
    return (
        company_key(company),
        normalize(str(title or "")),
        normalize(normalized_location),
    )


def _content_key(observation: Observation) -> tuple[str, str, str]:
    return _content_key_values(observation.company, observation.title, observation.location)


def _match_key(observation: Observation) -> tuple[str, str, str]:
    return _match_key_values(observation.company, observation.title, observation.location)


def _title_match_key(observation: Observation) -> tuple[str, str, str]:
    company, title, _ = _match_key(observation)
    return company, title, observation.program


_COMPANY_DESCRIPTORS = frozenset(
    {
        "aerospace",
        "com",
        "financial",
        "global",
        "group",
        "holdings",
        "industries",
        "labs",
        "laboratories",
        "platforms",
        "services",
        "solutions",
        "systems",
        "technologies",
        "technology",
        "web",
    }
)


def _company_alias_match(left: str, right: str) -> bool:
    if left == right:
        return True
    if left.replace(" ", "") == right.replace(" ", ""):
        return True
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return False
    shared = left_tokens & right_tokens
    if not any(len(token) >= 4 for token in shared):
        return False
    if left_tokens <= right_tokens:
        return (right_tokens - left_tokens) <= _COMPANY_DESCRIPTORS
    if right_tokens <= left_tokens:
        return (left_tokens - right_tokens) <= _COMPANY_DESCRIPTORS
    return False


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
    decision = reported_job_url(raw_url)
    status = _link_status(sources, decision.url)
    job["url_host"] = decision.host
    job["url_fingerprint"] = hashlib.sha256(decision.url.encode("utf-8")).hexdigest()[:24]
    job["link_status"] = status
    job["url"] = decision.url or None


def _previous_direct_observation(job: dict[str, Any]) -> Observation | None:
    raw_url = job.get("url")
    decision = reported_job_url(raw_url if isinstance(raw_url, str) else "")
    program = job.get("program")
    if (
        job.get("status") != "open"
        or not decision.url
        or decision.host == "jobright.ai"
        or program not in {"internship", "new-grad"}
    ):
        return None
    source = next(
        (
            item
            for item in job.get("sources", [])
            if isinstance(item, dict) and not str(item.get("id") or "").startswith("jobright-")
        ),
        None,
    )
    if source is None:
        return None
    cycle = job.get("cycle")
    return Observation(
        source_id=str(source.get("id") or "previous-direct"),
        source_label=str(source.get("label") or "Previously resolved employer link"),
        source_url=str(source.get("url") or decision.url),
        external_id=str(job.get("id") or decision.url),
        company=str(job.get("company") or ""),
        title=str(job.get("title") or ""),
        location=str(job.get("location") or "United States"),
        url=decision.url,
        program=program,
        cycle=str(cycle) if cycle else None,
        posted_at=str(job.get("posted_at")) if job.get("posted_at") else None,
        sponsorship=str(job.get("sponsorship")) if job.get("sponsorship") else None,
        trusted_us=True,
        metadata={"carried_direct_link": True},
    )


def _index_direct_observations(
    observations: list[Observation],
) -> tuple[
    dict[tuple[str, str, str], Observation],
    dict[tuple[str, str, str], dict[str, Observation]],
    dict[tuple[str, str], dict[str, Observation]],
]:
    by_content: dict[tuple[str, str, str], Observation] = {}
    by_title: dict[tuple[str, str, str], dict[str, Observation]] = defaultdict(dict)
    by_role: dict[tuple[str, str], dict[str, Observation]] = defaultdict(dict)
    for observation in sorted(observations, key=_priority):
        by_content.setdefault(_match_key(observation), observation)
        by_title[_title_match_key(observation)].setdefault(job_id(observation), observation)
        _, title, program = _title_match_key(observation)
        by_role[(title, program)].setdefault(job_id(observation), observation)
    return by_content, by_title, by_role


def _find_direct_match(
    observation: Observation,
    by_content: dict[tuple[str, str, str], Observation],
    by_title: dict[tuple[str, str, str], dict[str, Observation]],
    by_role: dict[tuple[str, str], dict[str, Observation]],
) -> Observation | None:
    direct = by_content.get(_match_key(observation))
    if direct is not None:
        return direct
    title_matches = list(by_title.get(_title_match_key(observation), {}).values())
    if len(title_matches) == 1:
        return title_matches[0]
    company, title, program = _title_match_key(observation)
    alias_matches = {
        job_id(candidate): candidate
        for candidate in by_role.get((title, program), {}).values()
        if _company_alias_match(company, company_key(candidate.company))
    }
    return next(iter(alias_matches.values())) if len(alias_matches) == 1 else None


def _current_jobs(
    observations: list[Observation],
    today: str,
    previous_jobs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    eligible_observations = [observation for observation in observations if eligible(observation)]
    current_direct = [
        observation
        for observation in eligible_observations
        if not observation.source_id.startswith("jobright-")
    ]
    direct_indexes = _index_direct_observations(current_direct)
    previous_direct = [
        observation
        for job in previous_jobs
        if (observation := _previous_direct_observation(job)) is not None
    ]
    previous_indexes = _index_direct_observations(previous_direct)

    grouped: dict[str, list[Observation]] = defaultdict(list)
    carried_identifiers: set[str] = set()
    for observation in eligible_observations:
        identifier = job_id(observation)
        if observation.source_id.startswith("jobright-"):
            direct = _find_direct_match(observation, *direct_indexes)
            if direct is None:
                direct = _find_direct_match(observation, *previous_indexes)
            if direct is not None:
                identifier = job_id(direct)
                if direct in previous_direct and identifier not in carried_identifiers:
                    grouped[identifier].append(direct)
                    carried_identifiers.add(identifier)
            else:
                identity = "\x1f".join(_content_key(observation))
                identifier = f"job_{hashlib.sha256(identity.encode()).hexdigest()[:24]}"
        grouped[identifier].append(observation)

    jobs: dict[str, dict[str, Any]] = {}
    for identifier, group in grouped.items():
        ordered = sorted(
            group,
            key=lambda item: (item.source_id.startswith("jobright-"), _priority(item)),
        )
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


def _resolved_jobright_aliases(
    job: dict[str, Any],
    previous_jobs: dict[str, dict[str, Any]],
    *,
    current_identifier: str,
) -> list[tuple[str, dict[str, Any]]]:
    sources = [source for source in job.get("sources", []) if isinstance(source, dict)]
    if job.get("url_host") == "jobright.ai" or not any(
        str(source.get("id") or "").startswith("jobright-") for source in sources
    ):
        return []
    company, title, location = _match_key_values(
        job.get("company"), job.get("title"), job.get("location")
    )
    candidates: list[tuple[str, dict[str, Any]]] = []
    for identifier, previous in previous_jobs.items():
        if identifier == current_identifier or previous.get("url_host") != "jobright.ai":
            continue
        previous_company, previous_title, _ = _match_key_values(
            previous.get("company"), previous.get("title"), previous.get("location")
        )
        if (
            previous.get("program") == job.get("program")
            and previous_title == title
            and _company_alias_match(company, previous_company)
        ):
            candidates.append((identifier, previous))
    by_content: dict[tuple[str, str, str], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for candidate in candidates:
        previous = candidate[1]
        by_content[
            _match_key_values(
                previous.get("company"), previous.get("title"), previous.get("location")
            )
        ].append(candidate)
    exact = [
        values
        for key, values in by_content.items()
        if _company_alias_match(company, key[0]) and key[1:] == (title, location)
    ]
    if exact:
        return [candidate for values in exact for candidate in values]
    return next(iter(by_content.values())) if len(by_content) == 1 else []


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
    current = _current_jobs(observations, today, list(previous_jobs.values()))
    merged: dict[str, dict[str, Any]] = {}
    migrated_previous_ids: set[str] = set()

    for identifier, job in current.items():
        previous = previous_jobs.get(identifier)
        aliases = _resolved_jobright_aliases(
            job,
            previous_jobs,
            current_identifier=identifier,
        )
        migrated_previous_ids.update(alias_identifier for alias_identifier, _ in aliases)
        if previous is None and aliases:
            previous = min(
                (alias for _, alias in aliases),
                key=lambda alias: str(alias.get("first_seen") or today),
            )
        if previous is None:
            merged[identifier] = job
            continue
        known_sources = {
            source["id"]: source
            for previous_job in [previous, *(alias for _, alias in aliases)]
            for source in previous_job.get("sources", [])
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
        job["first_seen"] = min(
            str(previous_job.get("first_seen") or today)
            for previous_job in [previous, *(alias for _, alias in aliases)]
        )
        job["last_changed"] = (
            today
            if _material(job) != _material(previous)
            else previous.get("last_changed") or today
        )
        merged[identifier] = job

    for identifier, previous in previous_jobs.items():
        if identifier in merged or identifier in migrated_previous_ids:
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
            reported_previous = reported_job_url(previous_url)
            if not reported_previous.url:
                continue
            _protect_link(job, previous_source_list, reported_previous.url)
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
