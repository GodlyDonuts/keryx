from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import tempfile
from collections import Counter
from datetime import UTC, datetime
from email.utils import format_datetime
from io import StringIO
from itertools import islice
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

_SITE_URL = "https://godlydonuts.github.io/keryx/"
_FEED_LIMIT = 100


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _open_jobs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_jobs = payload.get("jobs", [])
    if not isinstance(raw_jobs, list):
        raise ValueError("jobs payload must contain a list")
    jobs = [job for job in raw_jobs if isinstance(job, dict) and job.get("status") == "open"]
    return sorted(
        jobs,
        key=lambda job: (
            str(job.get("posted_at") or ""),
            str(job.get("first_seen") or ""),
            str(job.get("company") or "").casefold(),
            str(job.get("title") or "").casefold(),
        ),
        reverse=True,
    )


def _dataset_date(jobs: list[dict[str, Any]]) -> str:
    dates = [
        str(job.get(field))
        for job in jobs
        for field in ("last_changed", "first_seen", "posted_at")
        if isinstance(job.get(field), str)
    ]
    return max(dates, default="1970-01-01")[:10]


def _dataset_timestamp(jobs: list[dict[str, Any]]) -> str | None:
    timestamps = [
        str(job.get(field))
        for job in jobs
        for field in ("last_changed_at", "first_seen_at")
        if isinstance(job.get(field), str)
    ]
    return max(timestamps, default=None)


def _public_api(payload: dict[str, Any], jobs: list[dict[str, Any]]) -> dict[str, Any]:
    public_jobs = []
    for job in jobs:
        public_job = dict(job)
        public_job.setdefault("current_source_ids", _source_ids(job, "current_source_ids"))
        public_job.setdefault("historical_source_ids", [])
        public_jobs.append(public_job)
    return {
        "schema_version": payload.get("schema_version", 3),
        "country": "United States",
        "dataset_date": _dataset_date(jobs),
        "dataset_timestamp": _dataset_timestamp(jobs),
        "count": len(jobs),
        "jobs": public_jobs,
    }


def _intelligence(job: dict[str, Any]) -> dict[str, Any]:
    value = job.get("intelligence")
    return value if isinstance(value, dict) else {}


def _academic(job: dict[str, Any]) -> dict[str, Any]:
    value = job.get("academic_eligibility")
    return value if isinstance(value, dict) else {}


def _source_ids(job: dict[str, Any], field: str) -> list[str]:
    values = job.get(field, [])
    if isinstance(values, list) and (values or field in job):
        return [str(value) for value in values]
    if field != "current_source_ids":
        return []
    return [
        str(source["id"])
        for source in job.get("sources", [])
        if isinstance(source, dict) and source.get("id")
    ]


def _csv_text(jobs: list[dict[str, Any]]) -> str:
    output = StringIO(newline="")
    fields = (
        "id",
        "company",
        "title",
        "location",
        "program",
        "cycle",
        "category",
        "skills",
        "compensation",
        "workplace",
        "visa_status",
        "academic_status",
        "academic_summary",
        "graduation_requirement_level",
        "graduation_years",
        "posted_at",
        "first_seen",
        "first_seen_at",
        "last_changed_at",
        "apply_url",
        "link_status",
        "current_source_count",
        "historical_source_count",
        "previously_ats_observed",
        "source_count",
    )
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for job in jobs:
        intelligence = _intelligence(job)
        compensation = intelligence.get("compensation")
        workplace = intelligence.get("workplace")
        visa = intelligence.get("visa")
        academic = _academic(job)
        writer.writerow(
            {
                "id": job.get("id"),
                "company": job.get("company"),
                "title": job.get("title"),
                "location": job.get("location"),
                "program": job.get("program"),
                "cycle": job.get("cycle"),
                "category": intelligence.get("category"),
                "skills": "; ".join(
                    str(skill) for skill in intelligence.get("skills", []) if isinstance(skill, str)
                ),
                "compensation": (
                    compensation.get("summary") if isinstance(compensation, dict) else ""
                ),
                "workplace": workplace.get("value") if isinstance(workplace, dict) else "",
                "visa_status": visa.get("status") if isinstance(visa, dict) else "unknown",
                "academic_status": academic.get("status"),
                "academic_summary": academic.get("summary"),
                "graduation_requirement_level": academic.get("requirement_level"),
                "graduation_years": "; ".join(
                    str(year) for year in academic.get("graduation_years", [])
                ),
                "posted_at": job.get("posted_at"),
                "first_seen": job.get("first_seen"),
                "first_seen_at": job.get("first_seen_at"),
                "last_changed_at": job.get("last_changed_at"),
                "apply_url": job.get("url") or "",
                "link_status": job.get("link_status"),
                "current_source_count": len(_source_ids(job, "current_source_ids")),
                "historical_source_count": len(_source_ids(job, "historical_source_ids")),
                "previously_ats_observed": bool(job.get("previously_ats_observed")),
                "source_count": len(job.get("sources", [])),
            }
        )
    return output.getvalue()


def _feed_date(job: dict[str, Any]) -> str:
    raw = str(job.get("posted_at") or job.get("first_seen") or "1970-01-01")[:10]
    try:
        value = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        value = datetime(1970, 1, 1, tzinfo=UTC)
    return format_datetime(value)


def _feed_text(jobs: list[dict[str, Any]]) -> str:
    dated = _dataset_date(jobs)
    build_date = format_datetime(datetime.strptime(dated, "%Y-%m-%d").replace(tzinfo=UTC))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0">',
        "  <channel>",
        "    <title>Keryx US opportunities</title>",
        f"    <link>{_SITE_URL}</link>",
        "    <description>Continuously updated US internships and "
        "new-graduate roles.</description>",
        f"    <lastBuildDate>{build_date}</lastBuildDate>",
    ]
    for job in islice((item for item in jobs if item.get("url")), _FEED_LIMIT):
        intelligence = _intelligence(job)
        category = str(intelligence.get("category") or "other-tech")
        description = (
            f"{job.get('program')} · {job.get('cycle')} · {job.get('location')} · {category}. "
            "Verify all requirements on the employer posting."
        )
        url = escape(str(job["url"]), {'"': "&quot;"})
        lines.extend(
            (
                "    <item>",
                f"      <title>{escape(str(job.get('company')))} — "
                f"{escape(str(job.get('title')))}</title>",
                f"      <link>{url}</link>",
                f'      <guid isPermaLink="false">{escape(str(job.get("id")))}</guid>',
                f"      <pubDate>{_feed_date(job)}</pubDate>",
                f"      <description>{escape(description)}</description>",
                "    </item>",
            )
        )
    lines.extend(("  </channel>", "</rss>", ""))
    return "\n".join(lines)


def _stats(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    categories: Counter[str] = Counter()
    programs: Counter[str] = Counter()
    cycles: Counter[str] = Counter()
    link_statuses: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    visa: Counter[str] = Counter()
    academic: Counter[str] = Counter()
    coverage = {
        "text_checked": 0,
        "skill_tagged": 0,
        "compensation": 0,
        "workplace_stated": 0,
        "clickable_link": 0,
    }
    for job in jobs:
        programs[str(job.get("program") or "unknown")] += 1
        cycles[str(job.get("cycle") or "unscheduled")] += 1
        link_statuses[str(job.get("link_status") or "unknown")] += 1
        coverage["clickable_link"] += int(bool(job.get("url")))
        for source_id in _source_ids(job, "current_source_ids"):
            sources[source_id.split(":", 1)[0]] += 1
        intelligence = _intelligence(job)
        categories[str(intelligence.get("category") or "other-tech")] += 1
        coverage["text_checked"] += int(intelligence.get("text_status") == "checked")
        skill_values = intelligence.get("skills")
        coverage["skill_tagged"] += int(isinstance(skill_values, list) and bool(skill_values))
        coverage["compensation"] += int(isinstance(intelligence.get("compensation"), dict))
        workplace = intelligence.get("workplace")
        coverage["workplace_stated"] += int(
            isinstance(workplace, dict) and workplace.get("value") != "unspecified"
        )
        visa_value = intelligence.get("visa")
        if isinstance(visa_value, dict):
            visa[str(visa_value.get("status") or "unknown")] += 1
        else:
            visa["unknown"] += 1
        academic_value = _academic(job)
        academic[str(academic_value.get("status") or "unavailable")] += 1
    return {
        "schema_version": 1,
        "country": "United States",
        "dataset_date": _dataset_date(jobs),
        "open_total": len(jobs),
        "programs": dict(sorted(programs.items())),
        "cycles": dict(sorted(cycles.items())),
        "categories": dict(sorted(categories.items())),
        "visa": dict(sorted(visa.items())),
        "academic": dict(sorted(academic.items())),
        "link_statuses": dict(sorted(link_statuses.items())),
        "source_observations": dict(sorted(sources.items())),
        "coverage": coverage,
    }


def publish_public_artifacts(
    output_root: Path,
    payload: dict[str, Any],
    *,
    static_root: Path | None = None,
    source_health: dict[str, Any] | None = None,
) -> None:
    if static_root is not None:
        if not static_root.is_dir():
            raise FileNotFoundError(f"static site directory does not exist: {static_root}")
        shutil.copytree(static_root, output_root, dirs_exist_ok=True)
    jobs = _open_jobs(payload)
    api = _public_api(payload, jobs)
    _write(output_root / "api/jobs.json", json.dumps(api, indent=2, sort_keys=True) + "\n")
    _write(
        output_root / "api/stats.json", json.dumps(_stats(jobs), indent=2, sort_keys=True) + "\n"
    )
    if source_health is not None:
        _write(
            output_root / "api/source-health.json",
            json.dumps(source_health, indent=2, sort_keys=True) + "\n",
        )
    _write(output_root / "opportunities.csv", _csv_text(jobs))
    _write(output_root / "feed.xml", _feed_text(jobs))
    _write(output_root / ".nojekyll", "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Keryx's static public data products")
    parser.add_argument("--data", type=Path, default=Path("data/jobs.json"))
    parser.add_argument("--source-health", type=Path, default=Path("data/source-health.json"))
    parser.add_argument("--static", type=Path, default=Path("site"))
    parser.add_argument("--output", type=Path, default=Path("_site"))
    arguments = parser.parse_args()
    payload = json.loads(arguments.data.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("jobs data must contain a JSON object")
    source_health = json.loads(arguments.source_health.read_text(encoding="utf-8"))
    if not isinstance(source_health, dict):
        raise ValueError("source-health data must contain a JSON object")
    publish_public_artifacts(
        arguments.output,
        payload,
        static_root=arguments.static,
        source_health=source_health,
    )
    print(f"Published Keryx dashboard artifacts to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
