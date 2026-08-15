from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

from .normalize import canonical_url, reported_job_url
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
_LINK_STATUSES = frozenset(
    {"ats-verified", "cross-source", "platform-structured", "source-reported", "unverified"}
)
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
_CYCLE_LABELS = {
    "summer-2027": "Summer 2027",
    "fall-2026": "Fall 2026",
    "spring-2027": "Spring 2027",
    "winter-2027": "Winter 2027",
    "2027": "2027",
    "2026": "2026",
    "unscheduled": "Not listed",
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
    for source in job.get("sources", [])[:4]:
        label = _cell(source.get("label"))
        url = canonical_url(str(source.get("url") or ""))
        links.append(f"[{label}]({url})" if url else label)
    return ", ".join(links) or "—"


def _markdown_destination(url: str) -> str:
    return quote(url, safe=":/?#@!$&'*+,;=%~._-")


def _apply_link(job: dict[str, Any]) -> str:
    raw_url = job.get("url")
    url = raw_url if isinstance(raw_url, str) else ""
    host = str(job.get("url_host") or (urlsplit(url).hostname if url else "") or "external site")
    if not url:
        return f"link unavailable<br><sub>{_cell(host)}</sub>"
    if host == "jobright.ai":
        return (
            f"[view job · Jobright]({_markdown_destination(url)})<br><sub>discovery listing</sub>"
        )
    status = {
        "ats-verified": "ATS checked",
        "cross-source": "cross-checked",
        "platform-structured": "recognized recruiting platform",
    }.get(str(job.get("link_status")), "source reported")
    return f"[apply · {_cell(host)}]({_markdown_destination(url)})<br><sub>{status}</sub>"


def _front_page_apply_link(job: dict[str, Any]) -> str:
    raw_url = job.get("url")
    url = raw_url if isinstance(raw_url, str) else ""
    if not url:
        return "link unavailable"
    host = str(job.get("url_host") or urlsplit(url).hostname or "employer site")
    if host == "jobright.ai":
        return f"**[View job →]({_markdown_destination(url)})**<br><sub>Jobright</sub>"
    return f"**[Apply →]({_markdown_destination(url)})**<br><sub>{_cell(host)}</sub>"


def _academic_eligibility(job: dict[str, Any]) -> str:
    eligibility = job.get("academic_eligibility")
    if not isinstance(eligibility, dict) or eligibility.get("status") == "unavailable":
        return "not available<br><sub>posting text not indexed</sub>"
    status = str(eligibility.get("status") or "")
    source = _cell(eligibility.get("source_label") or "source text")
    provenance = "direct ATS text" if eligibility.get("confidence") == "direct-ats" else source
    checked_at = _cell(eligibility.get("checked_at"))
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


def _markdown(title: str, jobs: list[dict[str, Any]], *, count_label: str = "open roles") -> str:
    lines = [
        f"# {title}",
        "",
        "> Generated automatically by Keryx. US roles only. "
        "Academic requirements are deterministic hints, not eligibility decisions. "
        "Use the employer link to confirm current details.",
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
            "| Company | Role | Location | Academic eligibility | Posted | Seen in | Apply |",
            "|---|---|---|---|---|---|---|",
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
    internships = sum(count for (program, _), count in counts.items() if program == "internship")
    new_grad = sum(count for (program, _), count in counts.items() if program == "new-grad")
    return "\n".join(
        (
            f"**{internships:,} internships · {new_grad:,} new-grad roles · "
            f"{internships + new_grad:,} total openings**",
            "",
            "### 🎓 Internships",
            "",
            "| Recruiting term | Open roles | Browse |",
            "|---|---:|---|",
            f"| ☀️ Summer 2027 | {counts.get(('internship', 'summer-2027'), 0):,} | "
            "**[View openings →](internships/summer-2027.md)** |",
            f"| 🍂 Fall 2026 | {counts.get(('internship', 'fall-2026'), 0):,} | "
            "**[View openings →](internships/fall-2026.md)** |",
            f"| 🌱 Spring 2027 | {counts.get(('internship', 'spring-2027'), 0):,} | "
            "**[View openings →](internships/spring-2027.md)** |",
            f"| ❄️ Winter 2027 | {counts.get(('internship', 'winter-2027'), 0):,} | "
            "**[View openings →](internships/winter-2027.md)** |",
            f"| 📅 Season not listed | {counts.get(('internship', 'unscheduled'), 0):,} | "
            "**[View openings →](internships/unscheduled.md)** |",
            "",
            "### 🚀 New-graduate roles",
            "",
            "| Start year | Open roles | Browse |",
            "|---|---:|---|",
            f"| 2027 | {counts.get(('new-grad', '2027'), 0):,} | "
            "**[View openings →](new-grad/2027.md)** |",
            f"| 2026 | {counts.get(('new-grad', '2026'), 0):,} | "
            "**[View openings →](new-grad/2026.md)** |",
            f"| Year not listed | {counts.get(('new-grad', 'unscheduled'), 0):,} | "
            "**[View openings →](new-grad/unscheduled.md)** |",
        )
    )


def _front_page_eligibility(job: dict[str, Any]) -> str:
    eligibility = job.get("academic_eligibility")
    if not isinstance(eligibility, dict) or eligibility.get("status") == "unavailable":
        return "not available"
    if eligibility.get("status") == "not-found":
        return "not stated"

    levels = []
    for key in ("requirement_level", "currently_enrolled_level", "return_to_school_level"):
        level = eligibility.get(key)
        if level in _REQUIREMENT_LEVELS and level not in levels:
            levels.append(str(level))
    detail = f"<br><sub>{' / '.join(levels)}</sub>" if levels else ""
    return f"{_cell(eligibility.get('summary'))}{detail}"


def _latest_table(jobs: list[dict[str, Any]], program: str, *, limit: int = 12) -> str:
    latest = _sort_jobs([job for job in jobs if job.get("program") == program])[:limit]
    if not latest:
        return "_No open roles currently indexed._"

    rows = [
        "| Company | Role | Location | Term | Eligibility | Posted | Apply |",
        "|---|---|---|---|---|---:|---|",
    ]
    for job in latest:
        rows.append(
            "| "
            + " | ".join(
                (
                    _cell(job.get("company")),
                    _cell(job.get("title")),
                    _cell(job.get("location")),
                    _cell(_CYCLE_LABELS.get(str(job.get("cycle")), job.get("cycle"))),
                    _front_page_eligibility(job),
                    _cell(job.get("posted_at")),
                    _front_page_apply_link(job),
                )
            )
            + " |"
        )
    return "\n".join(rows)


def _replace_generated_block(text: str, start: str, end: str, body: str) -> str:
    before, remainder = text.split(start, 1)
    _, after = remainder.split(end, 1)
    return f"{before}{start}\n{body}\n{end}{after}"


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
            elif not isinstance(checked_at, str) or not re.fullmatch(
                r"20\d{2}-\d{2}-\d{2}", checked_at
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
        raw_url = job.get("url")
        host = str(job.get("url_host") or "")
        fingerprint = str(job.get("url_fingerprint") or "")
        if raw_url is None:
            continue
        if not isinstance(raw_url, str):
            raise ValueError(f"{identifier} has a non-string application URL")
        decision = reported_job_url(raw_url)
        if not decision.url or decision.url != raw_url or decision.host != host:
            raise ValueError(f"{identifier} application URL is not a valid absolute web URL")
        if hashlib.sha256(raw_url.encode("utf-8")).hexdigest()[:24] != fingerprint:
            raise ValueError(f"{identifier} application URL fingerprint does not match")


def render_repository(
    root: Path,
    payload: dict[str, Any],
    boards: object,
    quarantine: object | None = None,
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
        "<!-- LATEST-INTERNSHIPS:START -->",
        "<!-- LATEST-INTERNSHIPS:END -->",
        _latest_table(open_jobs, "internship"),
    )
    readme = _replace_generated_block(
        readme,
        "<!-- LATEST-NEW-GRAD:START -->",
        "<!-- LATEST-NEW-GRAD:END -->",
        _latest_table(open_jobs, "new-grad"),
    )
    _write(readme_path, readme)
