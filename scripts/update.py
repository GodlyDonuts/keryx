from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.boards import discover_boards, fetch_direct_boards  # noqa: E402
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

    upstream_observations = [
        observation
        for snapshot in upstreams
        for observation in snapshot.observations
        if eligible(observation)
    ]
    board_payload = _load_json(ROOT / "data/boards.json", {"boards": []})
    existing_boards = [
        board for board in board_payload.get("boards", []) if isinstance(board, dict)
    ]
    existing_keys = {
        board["key"]
        for board in discover_boards([], existing_boards)  # type: ignore[arg-type]
    }
    boards = discover_boards(upstream_observations, existing_boards)  # type: ignore[arg-type]

    slot = datetime.now(UTC).minute // 15
    boards_to_poll = [
        board
        for board in boards
        if board["key"] not in existing_keys or _poll_slot(board["key"]) == slot
    ]
    direct, direct_errors = fetch_direct_boards(boards_to_poll)
    snapshots = (*upstreams, *direct)
    observations = [item for snapshot in snapshots for item in snapshot.observations]
    complete_sources = {snapshot.source_id for snapshot in snapshots if snapshot.complete}

    previous = _load_json(
        ROOT / "data/jobs.json", {"schema_version": 2, "country": "United States", "jobs": []}
    )
    today = datetime.now(UTC).date().isoformat()
    payload = merge_state(
        previous,
        observations,
        complete_sources=complete_sources,
        today=today,
    )
    render_repository(ROOT, payload, boards, _quarantine_report(observations))

    open_jobs = sum(job.get("status") == "open" for job in payload["jobs"])
    print(
        f"Keryx indexed {open_jobs} open US roles from {len(upstreams)} upstreams and "
        f"{len(direct)} direct ATS boards."
    )
    errors = {**upstream_errors, **direct_errors}
    if errors:
        by_kind: dict[str, int] = {}
        for name in errors:
            kind = name.split(":", 2)[1] if name.startswith("ats:") else "upstream"
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
