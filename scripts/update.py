from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.boards import Board, discover_boards, fetch_direct_boards  # noqa: E402
from scripts.career_sites import save_site_state, scan_company_sites  # noqa: E402
from scripts.discovery import prioritized_board_keys, split_jobright_discoveries  # noqa: E402
from scripts.models import Observation  # noqa: E402
from scripts.normalize import reported_job_url  # noqa: E402
from scripts.render import render_repository  # noqa: E402
from scripts.sources import fetch_upstreams  # noqa: E402
from scripts.state import eligible, merge_state  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _poll_slot(key: str) -> int:
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16) % 4


def _bounded_ats_batch(
    boards: list[Board], priority_keys: set[str], *, quarter: int
) -> list[Board]:
    """Keep rate-limited public boards useful without overwhelming their guest endpoints."""

    workable = [board for board in boards if board.get("ats") == "workable"]
    others = [board for board in boards if board.get("ats") != "workable"]
    workable.sort(
        key=lambda board: (
            board["key"] not in priority_keys,
            hashlib.sha256(f"{quarter}:{board['key']}".encode()).hexdigest(),
        )
    )
    return [*others, *workable[:4]]


def _quarantine_report(observations: list[Observation]) -> dict[str, Any]:
    records: dict[str, dict[str, str]] = {}
    for observation in observations:
        decision = reported_job_url(observation.url)
        if decision.url:
            continue
        fingerprint = hashlib.sha256(observation.url.encode("utf-8")).hexdigest()[:24]
        records[fingerprint] = {
            "fingerprint": fingerprint,
            "reason": decision.reason or "rejected",
            "reported_host": decision.host,
            "source_id": observation.source_id,
        }
    return {
        "schema_version": 1,
        "quarantined": [records[key] for key in sorted(records)],
    }


def main() -> int:
    upstreams, upstream_errors = fetch_upstreams()
    if not upstreams:
        details = "; ".join(f"{name}: {error}" for name, error in upstream_errors.items())
        raise RuntimeError(f"every upstream failed; refusing to alter the database ({details})")

    all_upstream_observations = [
        observation
        for snapshot in upstreams
        for observation in snapshot.observations
        if eligible(observation)
    ]
    non_jobright_observations, jobright_discoveries = split_jobright_discoveries(
        all_upstream_observations
    )
    today = datetime.now(UTC).date().isoformat()
    site_payload = _load_json(ROOT / "data/sites.json", {"schema_version": 1, "sites": []})
    scan_limit = min(max(int(os.environ.get("KERYX_SITE_SCAN_LIMIT", "96")), 0), 1_000)
    site_snapshots, site_boards, next_site_payload, site_errors = scan_company_sites(
        jobright_discoveries,
        site_payload,
        today=today,
        limit=scan_limit,
        force=os.environ.get("KERYX_FORCE_SITE_RESCAN") == "1",
    )
    board_payload = _load_json(ROOT / "data/boards.json", {"boards": []})
    existing_boards = [
        board for board in board_payload.get("boards", []) if isinstance(board, dict)
    ]
    existing_keys = {
        board["key"]
        for board in discover_boards([], existing_boards)  # type: ignore[arg-type]
    }
    boards = discover_boards(
        non_jobright_observations,
        [*existing_boards, *site_boards],  # type: ignore[list-item]
    )
    priority_keys = prioritized_board_keys(jobright_discoveries, boards)

    now = datetime.now(UTC)
    slot = now.minute // 15
    boards_to_poll = [
        board
        for board in boards
        if (
            board["key"] not in existing_keys
            or _poll_slot(board["key"]) == slot
            or board["key"] in priority_keys
        )
    ]
    boards_to_poll = _bounded_ats_batch(
        boards_to_poll,
        priority_keys,
        quarter=int(now.timestamp() // 900),
    )
    direct, direct_errors = fetch_direct_boards(boards_to_poll)
    snapshots = (*upstreams, *site_snapshots, *direct)
    site_observations = [item for snapshot in site_snapshots for item in snapshot.observations]
    direct_observations = [item for snapshot in direct for item in snapshot.observations]
    observations = [*all_upstream_observations, *site_observations, *direct_observations]
    complete_sources = {snapshot.source_id for snapshot in snapshots if snapshot.complete}

    previous = _load_json(
        ROOT / "data/jobs.json", {"schema_version": 2, "country": "United States", "jobs": []}
    )
    payload = merge_state(
        previous,
        observations,
        complete_sources=complete_sources,
        today=today,
    )
    render_repository(ROOT, payload, boards, _quarantine_report(observations))
    save_site_state(ROOT / "data/sites.json", next_site_payload)

    open_jobs = sum(job.get("status") == "open" for job in payload["jobs"])
    print(
        f"Keryx indexed {open_jobs} open US roles from {len(upstreams)} upstreams and "
        f"{len(direct)} direct ATS boards."
    )
    print(
        f"Jobright supplied {len(jobright_discoveries)} discovery signals; "
        f"scanned {len(site_snapshots) + len(site_errors)} company sites, discovered "
        f"{len(site_boards)} ATS boards, resolved {len(site_observations)} direct links, and "
        f"prioritized {len(priority_keys)} known employer boards."
    )
    errors = {**upstream_errors, **site_errors, **direct_errors}
    if errors:
        by_kind: dict[str, int] = {}
        for name in errors:
            if name.startswith("ats:"):
                kind = name.split(":", 2)[1]
            elif name.startswith("career-site:"):
                kind = "career-site"
            else:
                kind = "upstream"
            by_kind[kind] = by_kind.get(kind, 0) + 1
        summary = ", ".join(f"{kind}={count}" for kind, count in sorted(by_kind.items()))
        print(f"warning: {len(errors)} sources unavailable this run ({summary})", file=sys.stderr)
        for name, error in sorted(errors.items())[:8]:
            print(f"  {name}: {error}", file=sys.stderr)
        if len(errors) > 8:
            print(f"  ... {len(errors) - 8} additional errors suppressed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
