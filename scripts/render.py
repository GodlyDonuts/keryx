from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .intelligence import INTELLIGENCE_EXTRACTOR_VERSION, MAX_SKILLS
from .normalize import canonical_url, is_recruiting_platform_url, sanitize_job_url
from .provenance import parse_utc_timestamp
from .qualifications import ACADEMIC_EXTRACTOR_VERSION

_DATABASES = (
    ("internship", "summer-2027", Path("internships/summer-2027.md"), "Summer 2027 US Internships"),
    ("internship", "fall-2026", Path("internships/fall-2026.md"), "Fall 2026 US Internships"),
    ("internship", "spring-2027", Path("internships/spring-2027.md"), "Spring 2027 US Internships"),
    ("internship", "winter-2027", Path("internships/winter-2027.md"), "Winter 2027 US Internships"),
    (
        "internship",
        "unscheduled",
        Path("internships/unscheduled.md"),
        "US Internships — Cycle Not Stated",
    ),
    ("new-grad", "2027", Path("new-grad/2027.md"), "2027 US New-Graduate Roles"),
    ("new-grad", "2026", Path("new-grad/2026.md"), "2026 US New-Graduate Roles"),
    (
        "new-grad",
        "unscheduled",
        Path("new-grad/unscheduled.md"),
        "US New-Graduate Roles — Cycle Not Stated",
    ),
)
_LINK_STATUSES = frozenset({"ats-verified", "cross-source", "platform-structured", "unverified"})
_ACADEMIC_STATUSES = frozenset(
    {
        "explicit-date",
        "explicit-window",
        "explicit-lower-bound",
        "explicit-upper-bound",
        "student-status",
        "not-found",
        "unavailable",
    }
)
_REQUIREMENT_LEVELS = frozenset({"required", "preferred", "stated"})
_INTELLIGENCE_TEXT_STATUSES = frozenset({"checked", "metadata-only", "unavailable"})
_CATEGORIES = frozenset(
    {"software", "data-ml", "quant", "security", "hardware", "product-design", "other-tech"}
)
_WORKPLACE_VALUES = frozenset({"remote", "hybrid", "onsite", "unspecified"})
_VISA_VALUES = frozenset(
    {"citizenship-required", "no-sponsorship", "sponsorship-available", "unknown"}
)
_CATEGORY_LABELS = {
    "software": "Software",
    "data-ml": "Data / ML",
    "quant": "Quant",
    "security": "Security",
    "hardware": "Hardware",
    "product-design": "Product / Design",
    "other-tech": "Other tech",
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _cell(value: object) -> str:
    text = " ".join(str(value or "—").replace("|", "/").split())
    return (
        text.replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("://", "&#58;//")
    )


def _source_links(job: dict[str, Any]) -> str:
    links = []
    current_ids = {str(value) for value in job.get("current_source_ids", [])}
    historical_ids = {str(value) for value in job.get("historical_source_ids", [])}
    for source in job.get("sources", [])[:4]:
        label = _cell(source.get("label"))
        source_id = str(source.get("id") or "")
        if source_id in current_ids:
            label = f"{label} · current"
        elif source_id in historical_ids:
            label = f"{label} · historical"
        url = canonical_url(str(source.get("url") or ""))
        links.append(f"[{label}]({url})" if url else label)
    return ", ".join(links) or "—"


def _apply_link(job: dict[str, Any]) -> str:
    raw_url = job.get("url")
    url = raw_url if isinstance(raw_url, str) else ""
    host = str(job.get("url_host") or (urlsplit(url).hostname if url else "") or "external site")
    if not url:
        return f"destination withheld<br><sub>single source · {_cell(host)}</sub>"
    status = {
        "ats-verified": "ATS checked",
        "cross-source": "cross-checked",
        "platform-structured": "recognized recruiting platform",
    }.get(str(job.get("link_status")), "source reported")
    return f"[apply · {_cell(host)}]({url})<br><sub>{status}</sub>"


def _academic_eligibility(job: dict[str, Any]) -> str:
    eligibility = job.get("academic_eligibility")
    if not isinstance(eligibility, dict) or eligibility.get("status") == "unavailable":
        return "not available<br><sub>posting text not indexed</sub>"
    status = str(eligibility.get("status") or "")
    source = _cell(eligibility.get("source_label") or "source text")
    provenance = "direct ATS text" if eligibility.get("confidence") == "direct-ats" else source
    checked_at = _cell(str(eligibility.get("checked_at") or "")[:16].replace("T", " "))
    if status == "not-found":
        return f"not stated<br><sub>{provenance} · checked {checked_at}</sub>"
    details = []
    if status.startswith("explicit-"):
        details.append(f"graduation: {_cell(eligibility.get('requirement_level'))}")
    if eligibility.get("currently_enrolled"):
        details.append(f"enrollment: {_cell(eligibility.get('currently_enrolled_level'))}")
    if eligibility.get("return_to_school"):
        details.append(f"return to school: {_cell(eligibility.get('return_to_school_level'))}")
    details.append(provenance)
    details.append(f"checked {checked_at}")
    return f"{_cell(eligibility.get('summary'))}<br><sub>{' · '.join(details)}</sub>"


def _job_intelligence(job: dict[str, Any]) -> str:
    intelligence = job.get("intelligence")
    if not isinstance(intelligence, dict):
        return "—"
    category = _CATEGORY_LABELS.get(str(intelligence.get("category") or ""), "Other tech")
    skills = intelligence.get("skills")
    skill_text = ", ".join(str(skill) for skill in skills[:6]) if isinstance(skills, list) else ""
    lines = [f"**{_cell(category)}**" + (f" · {_cell(skill_text)}" if skill_text else "")]
    details: list[str] = []
    compensation = intelligence.get("compensation")
    if isinstance(compensation, dict) and compensation.get("summary"):
        details.append(_cell(compensation["summary"]))
    workplace = intelligence.get("workplace")
    if isinstance(workplace, dict) and workplace.get("value") not in {None, "unspecified"}:
        details.append(_cell(workplace["value"]))
    visa = intelligence.get("visa")
    if isinstance(visa, dict):
        visa_label = {
            "citizenship-required": "citizenship / clearance restriction",
            "no-sponsorship": "no sponsorship",
            "sponsorship-available": "sponsorship stated",
        }.get(str(visa.get("status") or ""))
        if visa_label:
            details.append(_cell(visa_label))
    if details:
        lines.append(" · ".join(details))
    h1b = intelligence.get("h1b_history")
    if isinstance(h1b, dict) and isinstance(h1b.get("approvals"), int):
        lines.append(f"H-1B history: {_cell(h1b['approvals'])} approvals*")
    return "<br>".join(lines)


def _markdown(title: str, jobs: list[dict[str, Any]], *, count_label: str = "open roles") -> str:
    lines = [
        f"# {title}",
        "",
        "> Generated automatically by Keryx. US roles only. "
        "Academic requirements are deterministic hints, not eligibility decisions. "
        "Use the employer link to confirm current details.",
        "> Skills, pay, work arrangement, and visa language are extracted only from public "
        "posting data. H-1B history is employer-level context, never a promise for this role.",
        "> **Required**, **preferred**, and merely **stated** conditions remain distinct; "
        "preferred qualifications are never treated as eligibility gates.",
        "> **Not stated** means no requirement was detected in available posting text; "
        "**not available** means Keryx did not receive the full posting text.",
        "",
        f"**{len(jobs)} {count_label}**",
        "",
    ]
    if not jobs:
        lines.extend(["_No open roles currently indexed._", ""])
        return "\n".join(lines)
    lines.extend(
        [
            "| Company | Role | Location | Role intelligence | Academic eligibility | "
            "Posted | Seen in | Apply |",
            "|---|---|---|---|---|---|---|---|",
        ]
    )
    for job in jobs:
        lines.append(
            "| "
            + " | ".join(
                (
                    _cell(job.get("company")),
                    _cell(job.get("title")),
                    _cell(job.get("location")),
                    _job_intelligence(job),
                    _academic_eligibility(job),
                    _cell(job.get("posted_at")),
                    _source_links(job),
                    _apply_link(job),
                )
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _sort_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(job: dict[str, Any]) -> tuple[int, str, str]:
        posted = str(job.get("posted_at") or "").replace("-", "")
        posted_number = int(posted) if posted.isdigit() else 0
        return (
            -posted_number,
            str(job.get("company", "")).casefold(),
            str(job.get("title", "")).casefold(),
        )

    return sorted(
        jobs,
        key=key,
    )


def _count_table(counts: dict[tuple[str, str], int]) -> str:
    rows = ["| Recruiting cycle | Open roles |", "|---|---:|"]
    for program, cycle, path, title in _DATABASES:
        rows.append(f"| [{title}]({path.as_posix()}) | {counts.get((program, cycle), 0)} |")
    return "\n".join(rows)


def _academic_coverage_table(jobs: list[dict[str, Any]]) -> str:
    status_counts = {"detected": 0, "not-found": 0, "unavailable": 0}
    level_counts = {level: 0 for level in sorted(_REQUIREMENT_LEVELS)}
    for job in jobs:
        eligibility = job.get("academic_eligibility")
        if not isinstance(eligibility, dict) or eligibility.get("status") == "unavailable":
            status_counts["unavailable"] += 1
            continue
        if eligibility.get("status") == "not-found":
            status_counts["not-found"] += 1
            continue
        status_counts["detected"] += 1
        for key in (
            "requirement_level",
            "currently_enrolled_level",
            "return_to_school_level",
        ):
            level = eligibility.get(key)
            if level in level_counts:
                level_counts[str(level)] += 1

    return "\n".join(
        (
            "| Current posting-text coverage | Open roles |",
            "|---|---:|",
            f"| Academic condition detected | {status_counts['detected']} |",
            f"| Text checked; no condition detected | {status_counts['not-found']} |",
            f"| Complete posting text unavailable | {status_counts['unavailable']} |",
            "",
            "| Detected-condition modality | Criteria |",
            "|---|---:|",
            f"| Required | {level_counts['required']} |",
            f"| Preferred | {level_counts['preferred']} |",
            f"| Stated without clear modality | {level_counts['stated']} |",
        )
    )


def _intelligence_coverage_table(jobs: list[dict[str, Any]]) -> str:
    text_checked = 0
    skill_tagged = 0
    compensated = 0
    workplace_stated = 0
    visa_counts = {value: 0 for value in _VISA_VALUES}
    for job in jobs:
        intelligence = job.get("intelligence")
        if not isinstance(intelligence, dict):
            continue
        text_checked += int(intelligence.get("text_status") == "checked")
        skill_values = intelligence.get("skills")
        skill_tagged += int(isinstance(skill_values, list) and bool(skill_values))
        compensated += int(isinstance(intelligence.get("compensation"), dict))
        workplace = intelligence.get("workplace")
        workplace_stated += int(
            isinstance(workplace, dict) and workplace.get("value") != "unspecified"
        )
        visa = intelligence.get("visa")
        visa_status = str(visa.get("status")) if isinstance(visa, dict) else "unknown"
        if visa_status in visa_counts:
            visa_counts[visa_status] += 1
    return "\n".join(
        (
            "| Deterministic intelligence coverage | Open roles |",
            "|---|---:|",
            f"| Complete posting text checked | {text_checked} |",
            f"| One or more skill tags | {skill_tagged} |",
            f"| Explicit compensation found | {compensated} |",
            f"| Work arrangement stated | {workplace_stated} |",
            f"| Citizenship / clearance restriction | {visa_counts['citizenship-required']} |",
            f"| Sponsorship unavailable | {visa_counts['no-sponsorship']} |",
            f"| Sponsorship available | {visa_counts['sponsorship-available']} |",
            f"| Visa language inconclusive | {visa_counts['unknown']} |",
        )
    )


def _replace_generated_block(text: str, start: str, end: str, body: str) -> str:
    before, remainder = text.split(start, 1)
    _, after = remainder.split(end, 1)
    return f"{before}{start}\n{body}\n{end}{after}"


def _validate_bounded_intelligence_text(identifier: str, value: object, field: str) -> None:
    if value is not None and (not isinstance(value, str) or len(value) > 240):
        raise ValueError(f"{identifier} has invalid intelligence {field}")


def _validate_intelligence(
    identifier: str,
    value: object,
    source_ids: set[str],
) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{identifier} has invalid intelligence")
    if value.get("extractor_version") != INTELLIGENCE_EXTRACTOR_VERSION:
        raise ValueError(f"{identifier} has stale intelligence")
    text_status = value.get("text_status")
    if text_status not in _INTELLIGENCE_TEXT_STATUSES:
        raise ValueError(f"{identifier} has invalid intelligence text status")
    checked_at = value.get("checked_at")
    if text_status == "checked":
        if not isinstance(checked_at, str) or (
            re.fullmatch(r"20\d{2}-\d{2}-\d{2}", checked_at) is None
            and parse_utc_timestamp(checked_at) is None
        ):
            raise ValueError(f"{identifier} lacks an intelligence check date")
    elif checked_at is not None:
        raise ValueError(f"{identifier} has an invalid intelligence check date")
    if value.get("category") not in _CATEGORIES:
        raise ValueError(f"{identifier} has an invalid role category")
    skills = value.get("skills", [])
    if (
        not isinstance(skills, list)
        or len(skills) > MAX_SKILLS
        or any(not isinstance(skill, str) or not skill or len(skill) > 40 for skill in skills)
        or len(set(skills)) != len(skills)
    ):
        raise ValueError(f"{identifier} has invalid skill tags")
    for field in ("category_source_id", "skills_source_id"):
        source_id = value.get(field)
        if source_id is not None and source_id not in source_ids:
            raise ValueError(f"{identifier} has invalid intelligence provenance")

    compensation = value.get("compensation")
    if compensation is not None:
        if not isinstance(compensation, dict):
            raise ValueError(f"{identifier} has invalid compensation")
        minimum = compensation.get("minimum")
        maximum = compensation.get("maximum")
        if (
            compensation.get("currency") != "USD"
            or compensation.get("period") not in {"hour", "year"}
            or not isinstance(minimum, int | float)
            or maximum is not None
            and not isinstance(maximum, int | float)
            or isinstance(maximum, int | float)
            and maximum < minimum
            or compensation.get("source_id") not in source_ids
        ):
            raise ValueError(f"{identifier} has invalid compensation")
        for field in ("summary", "evidence", "source_label", "confidence"):
            _validate_bounded_intelligence_text(identifier, compensation.get(field), field)

    workplace = value.get("workplace")
    if workplace is not None and (
        not isinstance(workplace, dict) or workplace.get("value") not in _WORKPLACE_VALUES
    ):
        raise ValueError(f"{identifier} has invalid workplace intelligence")
    visa = value.get("visa")
    if visa is not None and (not isinstance(visa, dict) or visa.get("status") not in _VISA_VALUES):
        raise ValueError(f"{identifier} has invalid visa intelligence")
    for field_name, record in (("workplace", workplace), ("visa", visa)):
        if record is None:
            continue
        assert isinstance(record, dict)
        for field in ("summary", "evidence", "source_label", "confidence"):
            _validate_bounded_intelligence_text(identifier, record.get(field), field)
        source_id = record.get("source_id")
        if source_id is not None and source_id not in source_ids:
            raise ValueError(f"{identifier} has invalid {field_name} provenance")

    h1b = value.get("h1b_history")
    if h1b is not None:
        if (
            not isinstance(h1b, dict)
            or not isinstance(h1b.get("approvals"), int)
            or h1b["approvals"] < 0
            or h1b.get("source_id") not in source_ids
        ):
            raise ValueError(f"{identifier} has invalid H-1B history")
        for field in ("period", "source_label", "summary"):
            _validate_bounded_intelligence_text(identifier, h1b.get(field), field)


def _validate_publishable_jobs(jobs: list[dict[str, Any]]) -> None:
    for job in jobs:
        identifier = str(job.get("id", "unknown"))
        status = str(job.get("link_status", ""))
        if status not in _LINK_STATUSES:
            raise ValueError(f"{identifier} has an invalid link status")
        source_ids = {
            str(source.get("id", ""))
            for source in job.get("sources", [])
            if isinstance(source, dict)
        }
        current_source_ids = {
            str(source_id) for source_id in job.get("current_source_ids", source_ids)
        }
        historical_source_ids = {
            str(source_id) for source_id in job.get("historical_source_ids", [])
        }
        if not current_source_ids.issubset(source_ids) or not historical_source_ids.issubset(
            source_ids
        ):
            raise ValueError(f"{identifier} has invalid source-state views")
        if current_source_ids & historical_source_ids:
            raise ValueError(f"{identifier} has overlapping current and historical sources")
        for source in job.get("sources", []):
            if not isinstance(source, dict):
                continue
            state = source.get("state")
            if state is not None and state not in {"active", "historical"}:
                raise ValueError(f"{identifier} has an invalid source state")
            for field in ("first_seen_at", "state_changed_at", "last_observed_at"):
                timestamp = source.get(field)
                if timestamp is not None and parse_utc_timestamp(timestamp) is None:
                    raise ValueError(f"{identifier} has an invalid source timestamp")
        for field in ("first_seen_at", "last_changed_at", "closed_at_timestamp"):
            timestamp = job.get(field)
            if timestamp is not None and parse_utc_timestamp(timestamp) is None:
                raise ValueError(f"{identifier} has an invalid {field}")
        field_sources = job.get("field_sources")
        if field_sources is not None and (
            not isinstance(field_sources, dict)
            or any(source_id not in source_ids for source_id in field_sources.values())
        ):
            raise ValueError(f"{identifier} has invalid field provenance")
        field_conflicts = job.get("field_conflicts")
        if field_conflicts is not None and not isinstance(field_conflicts, dict):
            raise ValueError(f"{identifier} has invalid field conflicts")
        intelligence = job.get("intelligence")
        if intelligence is not None:
            _validate_intelligence(identifier, intelligence, source_ids)
        eligibility = job.get("academic_eligibility")
        if eligibility is not None:
            if not isinstance(eligibility, dict):
                raise ValueError(f"{identifier} has invalid academic eligibility")
            academic_status = str(eligibility.get("status") or "")
            if eligibility.get("extractor_version") != ACADEMIC_EXTRACTOR_VERSION:
                raise ValueError(f"{identifier} has a stale academic eligibility extractor")
            if academic_status not in _ACADEMIC_STATUSES:
                raise ValueError(f"{identifier} has invalid academic eligibility status")
            checked_at = eligibility.get("checked_at")
            if academic_status == "unavailable":
                if checked_at is not None:
                    raise ValueError(f"{identifier} has an invalid unavailable check date")
            elif not isinstance(checked_at, str) or (
                re.fullmatch(r"20\d{2}-\d{2}-\d{2}", checked_at) is None
                and parse_utc_timestamp(checked_at) is None
            ):
                raise ValueError(f"{identifier} lacks a valid academic check date")
            summary = str(eligibility.get("summary") or "")
            evidence_fields = {
                key: str(eligibility.get(key) or "")
                for key in (
                    "evidence",
                    "graduation_evidence",
                    "currently_enrolled_evidence",
                    "return_to_school_evidence",
                )
            }
            if (
                not summary
                or len(summary) > 160
                or any(len(value) > 280 for value in evidence_fields.values())
            ):
                raise ValueError(f"{identifier} has oversized academic eligibility text")
            if (
                academic_status.startswith("explicit-")
                and eligibility.get("requirement_level") not in _REQUIREMENT_LEVELS
            ):
                raise ValueError(f"{identifier} has invalid graduation requirement level")
            if (
                academic_status.startswith("explicit-")
                and not evidence_fields["graduation_evidence"]
            ):
                raise ValueError(f"{identifier} lacks graduation evidence")
            if (
                eligibility.get("currently_enrolled")
                and eligibility.get("currently_enrolled_level") not in _REQUIREMENT_LEVELS
            ):
                raise ValueError(f"{identifier} has invalid enrollment requirement level")
            if (
                eligibility.get("currently_enrolled")
                and not evidence_fields["currently_enrolled_evidence"]
            ):
                raise ValueError(f"{identifier} lacks enrollment evidence")
            if (
                eligibility.get("return_to_school")
                and eligibility.get("return_to_school_level") not in _REQUIREMENT_LEVELS
            ):
                raise ValueError(f"{identifier} has invalid return-to-school requirement level")
            if (
                eligibility.get("return_to_school")
                and not evidence_fields["return_to_school_evidence"]
            ):
                raise ValueError(f"{identifier} lacks return-to-school evidence")
            academic_source = eligibility.get("source_id")
            if academic_status == "unavailable":
                if academic_source is not None:
                    raise ValueError(f"{identifier} has invalid unavailable eligibility provenance")
            elif not isinstance(academic_source, str) or academic_source not in source_ids:
                raise ValueError(f"{identifier} lacks academic eligibility provenance")
            for key in ("graduation_start", "graduation_end"):
                value = eligibility.get(key)
                if value is not None and not re.fullmatch(r"20\d{2}(?:-\d{2})?", str(value)):
                    raise ValueError(f"{identifier} has invalid {key}")
        if status == "ats-verified" and not any(
            source_id.startswith("ats:") for source_id in current_source_ids
        ):
            raise ValueError(f"{identifier} lacks direct ATS provenance")
        if status == "cross-source" and (
            len(current_source_ids) < 2
            or any(source_id.startswith("ats:") for source_id in current_source_ids)
        ):
            raise ValueError(f"{identifier} lacks cross-source provenance")
        raw_url = job.get("url")
        host = str(job.get("url_host") or "")
        fingerprint = str(job.get("url_fingerprint") or "")
        if raw_url is None:
            host_decision = sanitize_job_url(f"https://{host}/")
            if (
                status != "unverified"
                or len(current_source_ids) > 1
                or any(source_id.startswith("ats:") for source_id in current_source_ids)
                or not host_decision.url
                or host_decision.host != host
                or len(fingerprint) != 24
            ):
                raise ValueError(f"{identifier} has an invalid withheld-link record")
            continue
        if not isinstance(raw_url, str):
            raise ValueError(f"{identifier} has a non-string application URL")
        decision = sanitize_job_url(raw_url)
        if not decision.url or decision.url != raw_url or decision.host != host:
            raise ValueError(f"{identifier} application URL is not canonical and safe")
        if hashlib.sha256(raw_url.encode("utf-8")).hexdigest()[:24] != fingerprint:
            raise ValueError(f"{identifier} application URL fingerprint does not match")
        if status == "unverified":
            raise ValueError(f"{identifier} exposes an unverified application URL")
        if status == "platform-structured" and not is_recruiting_platform_url(raw_url):
            raise ValueError(f"{identifier} has an invalid recruiting-platform URL")
        if status == "platform-structured" and len(current_source_ids) > 1:
            raise ValueError(f"{identifier} has invalid recruiting-platform provenance")


def render_repository(
    root: Path,
    payload: dict[str, Any],
    boards: object,
    quarantine: object | None = None,
    source_health: object | None = None,
) -> None:
    _validate_publishable_jobs(payload["jobs"])
    open_jobs = [job for job in payload["jobs"] if job.get("status") == "open"]
    counts: dict[tuple[str, str], int] = {}
    for program, cycle, relative_path, title in _DATABASES:
        jobs = _sort_jobs(
            [job for job in open_jobs if job["program"] == program and job["cycle"] == cycle]
        )
        counts[(program, cycle)] = len(jobs)
        _write(root / relative_path, _markdown(title, jobs))

    closed = _sort_jobs([job for job in payload["jobs"] if job.get("status") == "closed"])
    _write(
        root / "archive/closed.md",
        _markdown("Closed US Opportunities", closed, count_label="closed roles"),
    )
    _write(root / "data/jobs.json", json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _write(
        root / "data/boards.json",
        json.dumps({"schema_version": 1, "boards": boards}, indent=2, sort_keys=True) + "\n",
    )
    _write(
        root / "data/quarantine.json",
        json.dumps(
            quarantine or {"schema_version": 1, "quarantined": []},
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    if source_health is not None:
        _write(
            root / "data/source-health.json",
            json.dumps(source_health, indent=2, sort_keys=True) + "\n",
        )

    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    readme = _replace_generated_block(
        readme,
        "<!-- COUNTS:START -->",
        "<!-- COUNTS:END -->",
        _count_table(counts),
    )
    readme = _replace_generated_block(
        readme,
        "<!-- ACADEMIC-COVERAGE:START -->",
        "<!-- ACADEMIC-COVERAGE:END -->",
        _academic_coverage_table(open_jobs),
    )
    readme = _replace_generated_block(
        readme,
        "<!-- INTELLIGENCE-COVERAGE:START -->",
        "<!-- INTELLIGENCE-COVERAGE:END -->",
        _intelligence_coverage_table(open_jobs),
    )
    _write(readme_path, readme)
