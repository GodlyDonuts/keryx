from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

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
    return " ".join(str(value or "—").replace("|", "/").split())


def _source_links(job: dict[str, Any]) -> str:
    links = []
    for source in job.get("sources", [])[:4]:
        label = _cell(source.get("label"))
        url = str(source.get("url") or "")
        links.append(f"[{label}]({url})" if url else label)
    return ", ".join(links) or "—"


def _markdown(title: str, jobs: list[dict[str, Any]], *, count_label: str = "open roles") -> str:
    lines = [
        f"# {title}",
        "",
        "> Generated automatically by Keryx. US roles only. "
        "Use the employer link to confirm current details.",
        "",
        f"**{len(jobs)} {count_label}**",
        "",
    ]
    if not jobs:
        lines.extend(["_No open roles currently indexed._", ""])
        return "\n".join(lines)
    lines.extend(
        [
            "| Company | Role | Location | Posted | Seen in | Apply |",
            "|---|---|---|---|---|---|",
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
                    _cell(job.get("posted_at")),
                    _source_links(job),
                    f"[apply]({job['url']})",
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


def render_repository(root: Path, payload: dict[str, Any], boards: object) -> None:
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

    readme_path = root / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    start, end = "<!-- COUNTS:START -->", "<!-- COUNTS:END -->"
    before, remainder = readme.split(start, 1)
    _, after = remainder.split(end, 1)
    _write(readme_path, f"{before}{start}\n{_count_table(counts)}\n{end}{after}")
