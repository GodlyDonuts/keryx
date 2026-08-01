from __future__ import annotations

from html import escape
from pathlib import Path

from .models import SyncResult
from .store import atomic_write_json, atomic_write_text


def _atom(result: SyncResult, *, generated_at: str) -> str:
    entries: list[str] = []
    for event in result.event_history:
        job = event.job
        title = f"{event.event_type.title()}: {job['company']} — {job['title']}"
        entries.append(
            "  <entry>\n"
            f"    <id>urn:rolebeacon:{escape(event.event_id)}</id>\n"
            f"    <title>{escape(title)}</title>\n"
            f"    <updated>{escape(event.occurred_at)}</updated>\n"
            f'    <link href="{escape(str(job["url"]), quote=True)}"/>\n'
            f"    <summary>{escape(', '.join(job.get('locations', [])))}</summary>\n"
            "  </entry>"
        )
    body = "\n".join(entries)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        "  <id>urn:rolebeacon:events</id>\n"
        "  <title>RoleBeacon job changes</title>\n"
        f"  <updated>{escape(generated_at)}</updated>\n"
        f"{body}\n"
        "</feed>\n"
    )


def publish(output_dir: Path, result: SyncResult, *, generated_at: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    open_jobs = [job for job in result.jobs if job["status"] == "open"]
    atomic_write_json(
        output_dir / "jobs-v1.json",
        {
            "schema_version": 1,
            "generated_at": generated_at,
            "count": len(open_jobs),
            "jobs": open_jobs,
        },
    )
    atomic_write_json(
        output_dir / "events-v1.json",
        {
            "schema_version": 1,
            "generated_at": generated_at,
            "baseline": result.baseline,
            "batch_count": len(result.events),
            "count": len(result.event_history),
            "events": [event.__dict__ for event in result.event_history],
        },
    )
    atomic_write_json(
        output_dir / "status.json",
        {
            "generated_at": generated_at,
            "healthy": not result.errors,
            "open_jobs": len(open_jobs),
            "source_counts": result.source_counts,
            "source_errors": result.errors,
        },
    )
    atomic_write_text(output_dir / "feed.xml", _atom(result, generated_at=generated_at))
