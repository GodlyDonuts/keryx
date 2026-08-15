from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from functools import partial
from urllib.parse import urlsplit

from .models import Observation, Program, Snapshot
from .net import get_json, get_text
from .normalize import clean_text, epoch_date, iso_date

SIMPLIFY_INTERNSHIPS = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/"
    "dev/.github/scripts/listings.json"
)
SIMPLIFY_NEW_GRAD = (
    "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/"
    "dev/.github/scripts/listings.json"
)
SPEEDY_INTERNSHIPS = (
    "https://raw.githubusercontent.com/speedyapply/2027-SWE-College-Jobs/main/README.md"
)
SPEEDY_NEW_GRAD = (
    "https://raw.githubusercontent.com/speedyapply/2027-SWE-College-Jobs/main/NEW_GRAD_USA.md"
)
SNDSH_INTERNSHIPS = (
    "https://raw.githubusercontent.com/sndsh404/summer-2027-internships/main/README.md"
)
INTERN_ENGINE = (
    "https://raw.githubusercontent.com/zshah101/"
    "Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships/"
    "main/docs/api/jobs.json"
)
_JOBRIGHT_FEEDS: tuple[tuple[str, str, str, Program, str | None], ...] = (
    (
        "jobright-swe-internships",
        "2026-Software-Engineer-Internship",
        "Software Engineering",
        "internship",
        None,
    ),
    (
        "jobright-data-internships",
        "2026-Data-Analysis-Internship",
        "Data Analysis",
        "internship",
        None,
    ),
    (
        "jobright-business-analyst-internships",
        "2026-Business-Analyst-Internship",
        "Business Analysis",
        "internship",
        None,
    ),
    (
        "jobright-product-internships",
        "2026-Product-Management-Internship",
        "Product Management",
        "internship",
        None,
    ),
    (
        "jobright-engineering-internships",
        "2026-Engineer-Internship",
        "Engineering",
        "internship",
        None,
    ),
    (
        "jobright-swe-new-grad",
        "2026-Software-Engineer-New-Grad",
        "Software Engineering",
        "new-grad",
        "2026",
    ),
    (
        "jobright-data-new-grad",
        "2026-Data-Analysis-New-Grad",
        "Data Analysis",
        "new-grad",
        "2026",
    ),
    (
        "jobright-business-analyst-new-grad",
        "2026-Business-Analyst-New-Grad",
        "Business Analysis",
        "new-grad",
        "2026",
    ),
    (
        "jobright-product-new-grad",
        "2026-Product-Management-New-Grad",
        "Product Management",
        "new-grad",
        "2026",
    ),
)

_REPOSITORIES = {
    "simplify-internships": "https://github.com/SimplifyJobs/Summer2027-Internships",
    "simplify-new-grad": "https://github.com/SimplifyJobs/New-Grad-Positions",
    "speedy-internships": "https://github.com/speedyapply/2027-SWE-College-Jobs",
    "speedy-new-grad": "https://github.com/speedyapply/2027-SWE-College-Jobs",
    "sndsh-internships": "https://github.com/sndsh404/summer-2027-internships",
    "intern-engine": (
        "https://github.com/zshah101/Automated-List-Of-Summer-2027-and-Fall-2026-Tech-Internships"
    ),
    **{
        source_id: f"https://github.com/jobright-ai/{repository}"
        for source_id, repository, _, _, _ in _JOBRIGHT_FEEDS
    },
}


def _sequence(value: object) -> Sequence[object]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else ()


def _cycle_from_terms(terms: object) -> str | None:
    lowered = " ".join(str(item).casefold() for item in _sequence(terms))
    for label, cycle in (
        ("fall 2026", "fall-2026"),
        ("summer 2027", "summer-2027"),
        ("spring 2027", "spring-2027"),
        ("winter 2027", "winter-2027"),
    ):
        if label in lowered:
            return cycle
    return None


def _simplify(source_id: str, url: str, program: Program) -> Snapshot:
    payload = get_json(url)
    if not isinstance(payload, list):
        raise ValueError(f"{source_id} did not return an array")
    observations: list[Observation] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        if not item.get("active") or item.get("is_visible") is False:
            continue
        company = clean_text(item.get("company_name"))
        title = clean_text(item.get("title"))
        job_url = str(item.get("url") or "").strip()
        locations = ", ".join(
            clean_text(location) for location in _sequence(item.get("locations")) if location
        )
        if not company or not title or not job_url:
            continue
        cycle = _cycle_from_terms(item.get("terms")) if program == "internship" else None
        if program == "internship" and item.get("terms") and cycle is None:
            continue
        observations.append(
            Observation(
                source_id=source_id,
                source_label="Simplify",
                source_url=_REPOSITORIES[source_id],
                external_id=str(item.get("id") or job_url),
                company=company,
                title=title,
                location=locations,
                url=job_url,
                program=program,
                cycle=cycle,
                posted_at=epoch_date(item.get("date_posted")),
                sponsorship=clean_text(item.get("sponsorship")) or None,
                trusted_us=False,
            )
        )
    return Snapshot(source_id, tuple(observations), complete=True)


_HTML_LINK = re.compile(r'href=["\'](https?://[^"\']+)', re.IGNORECASE)
_MD_LINK = re.compile(r"\[[^]]*]\((https?://[^)]+)\)", re.IGNORECASE)
_JOBRIGHT_PATH = re.compile(r"^/jobs/info/([A-Za-z0-9_-]+)$")
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_markdown_jobs(
    text: str,
    *,
    source_id: str,
    source_label: str,
    program: Program,
    cycle_hint: str | None,
) -> tuple[Observation, ...]:
    observations: list[Observation] = []
    for line in text.splitlines():
        if not line.startswith("|") or "🔒" in line:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or set(cells[0]) <= {"-", ":", " "}:
            continue
        apply_cell = next(
            (
                cell
                for cell in cells[3:]
                if 'alt="Apply"' in cell or "alt='Apply'" in cell or "[apply]" in cell.casefold()
            ),
            "",
        )
        links = _HTML_LINK.findall(apply_cell) or _MD_LINK.findall(apply_cell)
        if not links:
            continue
        company = clean_text(cells[0])
        title = clean_text(cells[1])
        location = clean_text(cells[2])
        job_url = links[-1]
        if not company or not title:
            continue
        date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", line)
        observations.append(
            Observation(
                source_id=source_id,
                source_label=source_label,
                source_url=_REPOSITORIES[source_id],
                external_id=job_url,
                company=company,
                title=title,
                location=location,
                url=job_url,
                program=program,
                cycle=cycle_hint,
                posted_at=date_match.group(1) if date_match else None,
                trusted_us=True,
            )
        )
    return tuple(observations)


def _markdown(
    source_id: str,
    url: str,
    label: str,
    program: Program,
    cycle_hint: str | None,
) -> Snapshot:
    observations = parse_markdown_jobs(
        get_text(url),
        source_id=source_id,
        source_label=label,
        program=program,
        cycle_hint=cycle_hint,
    )
    return Snapshot(source_id, observations, complete=True)


def _jobright_posted_at(value: str, *, today: date) -> str | None:
    match = re.fullmatch(r"([A-Za-z]{3})\s+(\d{1,2})", clean_text(value))
    if not match or match.group(1).casefold() not in _MONTHS:
        return None
    try:
        posted = date(today.year, _MONTHS[match.group(1).casefold()], int(match.group(2)))
    except ValueError:
        return None
    if posted > today + timedelta(days=1):
        posted = posted.replace(year=posted.year - 1)
    return posted.isoformat()


def parse_jobright_jobs(
    text: str,
    *,
    source_id: str,
    source_label: str,
    program: Program,
    cycle_hint: str | None,
    today: date | None = None,
) -> tuple[Observation, ...]:
    observations: list[Observation] = []
    previous_company = ""
    previous_company_url: str | None = None
    current_date = today or datetime.now(UTC).date()
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 5 or set(cells[0]) <= {"-", ":", " "}:
            continue

        title_links = _MD_LINK.findall(cells[1])
        if not title_links:
            continue
        job_url = title_links[-1]
        parsed = urlsplit(job_url)
        identifier = _JOBRIGHT_PATH.fullmatch(parsed.path.rstrip("/"))
        if parsed.hostname != "jobright.ai" or not identifier:
            continue

        company_links = _MD_LINK.findall(cells[0])
        company_url = company_links[-1] if company_links else None
        company = clean_text(cells[0]).strip("*_` ")
        if company == "↳":
            company = previous_company
            company_url = previous_company_url
        elif company:
            previous_company = company
            previous_company_url = company_url
        title = clean_text(cells[1]).strip("*_` ")
        location = clean_text(cells[2])
        if not company or not title or not location:
            continue

        observations.append(
            Observation(
                source_id=source_id,
                source_label=f"Jobright · {source_label}",
                source_url=_REPOSITORIES[source_id],
                external_id=identifier.group(1),
                company=company,
                title=title,
                location=location,
                url=job_url,
                program=program,
                cycle=cycle_hint,
                posted_at=_jobright_posted_at(cells[4], today=current_date),
                trusted_us=False,
                metadata={
                    "work_model": clean_text(cells[3]) or None,
                    "company_url": company_url,
                },
            )
        )
    return tuple(observations)


def _jobright(
    source_id: str,
    repository: str,
    label: str,
    program: Program,
    cycle_hint: str | None,
) -> Snapshot:
    url = f"https://raw.githubusercontent.com/jobright-ai/{repository}/master/README.md"
    observations = parse_jobright_jobs(
        get_text(url),
        source_id=source_id,
        source_label=label,
        program=program,
        cycle_hint=cycle_hint,
    )
    return Snapshot(source_id, observations, complete=True)


def _intern_engine() -> Snapshot:
    payload = get_json(INTERN_ENGINE)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("jobs"), list):
        raise ValueError("intern-engine did not return a jobs array")
    observations: list[Observation] = []
    for item in payload["jobs"]:
        if not isinstance(item, Mapping):
            continue
        company = clean_text(item.get("company"))
        title = clean_text(item.get("title"))
        job_url = str(item.get("url") or "").strip()
        if not company or not title or not job_url:
            continue
        season = clean_text(item.get("season")).casefold()
        cycle = {
            "fall 2026": "fall-2026",
            "summer 2027": "summer-2027",
            "spring 2027": "spring-2027",
            "winter 2027": "winter-2027",
        }.get(season)
        observations.append(
            Observation(
                source_id="intern-engine",
                source_label="Internship Engine",
                source_url=_REPOSITORIES["intern-engine"],
                external_id=str(item.get("id") or job_url),
                company=company,
                title=title,
                location=clean_text(item.get("location")),
                url=job_url,
                program="internship",
                cycle=cycle,
                posted_at=iso_date(item.get("posted_at")),
                sponsorship=clean_text(item.get("sponsorship")) or None,
                trusted_us=True,
                metadata={"ats": clean_text(item.get("source"))},
            )
        )
    return Snapshot("intern-engine", tuple(observations), complete=True)


def fetch_upstreams() -> tuple[tuple[Snapshot, ...], dict[str, str]]:
    loaders: dict[str, Callable[[], Snapshot]] = {
        "simplify-internships": lambda: _simplify(
            "simplify-internships", SIMPLIFY_INTERNSHIPS, "internship"
        ),
        "simplify-new-grad": lambda: _simplify("simplify-new-grad", SIMPLIFY_NEW_GRAD, "new-grad"),
        "speedy-internships": lambda: _markdown(
            "speedy-internships", SPEEDY_INTERNSHIPS, "SpeedyApply", "internship", None
        ),
        "speedy-new-grad": lambda: _markdown(
            "speedy-new-grad", SPEEDY_NEW_GRAD, "SpeedyApply", "new-grad", "2027"
        ),
        "sndsh-internships": lambda: _markdown(
            "sndsh-internships",
            SNDSH_INTERNSHIPS,
            "Summer 2027 list",
            "internship",
            "summer-2027",
        ),
        "intern-engine": _intern_engine,
    }
    loaders.update(
        {
            source_id: partial(_jobright, source_id, repository, label, program, cycle_hint)
            for source_id, repository, label, program, cycle_hint in _JOBRIGHT_FEEDS
        }
    )
    snapshots: list[Snapshot] = []
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(loaders)) as executor:
        futures = {executor.submit(loader): name for name, loader in loaders.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                snapshots.append(future.result())
            except (OSError, ValueError) as error:
                errors[name] = str(error)
    return tuple(sorted(snapshots, key=lambda item: item.source_id)), errors
