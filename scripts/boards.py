from __future__ import annotations

import re
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import TypedDict
from urllib.parse import urlsplit

from .models import Observation, Snapshot
from .net import get_json, post_json
from .normalize import clean_text, infer_program, is_technical, iso_date, sanitize_job_url

_BOARD_COMPONENT = re.compile(r"(?:[A-Za-z0-9._-]|%[0-9A-Fa-f]{2}){1,128}")


class Board(TypedDict, total=False):
    key: str
    ats: str
    company: str
    slug: str
    site: str
    host: str
    wd: str


def _safe_component(value: object) -> bool:
    text = str(value or "")
    return text not in {".", ".."} and _BOARD_COMPONENT.fullmatch(text) is not None


def _safe_board(board: Board) -> bool:
    ats = board.get("ats")
    if ats not in {"greenhouse", "lever", "ashby", "workday"}:
        return False
    if not _safe_component(board.get("slug")):
        return False
    if ats != "workday":
        return True
    host = str(board.get("host") or "").casefold()
    if not host.endswith((".myworkdayjobs.com", ".myworkdaysite.com")):
        return False
    return bool(sanitize_job_url(f"https://{host}/").url) and _safe_component(board.get("site"))


def board_from_observation(observation: Observation) -> Board | None:
    safe_url = sanitize_job_url(observation.url).url
    if not safe_url:
        return None
    parsed = urlsplit(safe_url)
    host = (parsed.hostname or "").casefold()
    parts = [part for part in parsed.path.split("/") if part]
    external = observation.external_id.split(":")
    if "greenhouse.io" in host:
        slug = ""
        if "jobs" in parts:
            index = parts.index("jobs")
            if index >= 1:
                slug = parts[index - 1]
        if not slug and len(external) >= 3 and external[0] == "greenhouse":
            slug = external[1]
        if slug:
            return {
                "key": f"greenhouse:{slug.casefold()}",
                "ats": "greenhouse",
                "company": observation.company,
                "slug": slug,
            }
    if host == "jobs.lever.co" and parts:
        slug = parts[0]
        return {
            "key": f"lever:{slug.casefold()}",
            "ats": "lever",
            "company": observation.company,
            "slug": slug,
        }
    if host == "jobs.ashbyhq.com" and parts:
        slug = parts[0]
        return {
            "key": f"ashby:{slug.casefold()}",
            "ats": "ashby",
            "company": observation.company,
            "slug": slug,
        }
    if "myworkdayjobs.com" in host:
        labels = host.split(".")
        tenant = labels[0]
        wd = labels[1] if len(labels) > 1 else "wd1"
        lowered = [part.casefold() for part in parts]
        if "job" not in lowered:
            return None
        job_index = lowered.index("job")
        site_parts = [
            part for part in parts[:job_index] if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", part)
        ]
        if not site_parts:
            return None
        site = site_parts[-1]
        return {
            "key": f"workday:{host}:{tenant.casefold()}:{site.casefold()}",
            "ats": "workday",
            "company": observation.company,
            "slug": tenant,
            "site": site,
            "host": host,
            "wd": wd,
        }
    if "myworkdaysite.com" in host and len(parts) >= 4 and parts[0] == "recruiting":
        tenant, site = parts[1], parts[2]
        return {
            "key": f"workday:{host}:{tenant.casefold()}:{site.casefold()}",
            "ats": "workday",
            "company": observation.company,
            "slug": tenant,
            "site": site,
            "host": host,
        }
    return None


def discover_boards(observations: list[Observation], existing: list[Board]) -> list[Board]:
    boards: dict[str, Board] = {}
    for observation in observations:
        board = board_from_observation(observation)
        if board is None:
            continue
        current = boards.get(board["key"])
        if current is None:
            boards[board["key"]] = board
        elif not current.get("company") and board.get("company"):
            current["company"] = board["company"]
    # Existing entries are only fallbacks. Rediscovery from a live upstream wins so
    # case-sensitive Workday site names stay current while identities remain normalized.
    for old_board in existing:
        if not old_board.get("key") or not _safe_board(old_board):
            continue
        board = old_board.copy()
        if board.get("ats") == "workday":
            board["key"] = (
                f"workday:{str(board.get('host', '')).casefold()}:"
                f"{str(board.get('slug', '')).casefold()}:"
                f"{str(board.get('site', '')).casefold()}"
            )
        else:
            board["key"] = str(board["key"]).casefold()
        boards.setdefault(board["key"], board)
    return [boards[key] for key in sorted(boards)]


def _source(board: Board) -> tuple[str, str, str]:
    source_id = f"ats:{board['key']}"
    ats = board["ats"]
    label = f"{ats.title()} direct"
    slug = board["slug"]
    if ats == "greenhouse":
        url = f"https://job-boards.greenhouse.io/{slug}"
    elif ats == "lever":
        url = f"https://jobs.lever.co/{slug}"
    elif ats == "ashby":
        url = f"https://jobs.ashbyhq.com/{slug}"
    else:
        url = f"https://{board['host']}/{board['site']}"
    return source_id, label, url


def _observation(
    board: Board,
    *,
    external_id: str,
    title: object,
    location: object,
    url: object,
    posted_at: object = None,
    description: object = "",
) -> Observation | None:
    clean_title = clean_text(title)
    clean_description = clean_text(description)
    program = infer_program(clean_title)
    if program is None or not is_technical(clean_title, clean_description):
        return None
    job_url = str(url or "").strip()
    if not job_url:
        return None
    source_id, label, source_url = _source(board)
    return Observation(
        source_id=source_id,
        source_label=label,
        source_url=source_url,
        external_id=external_id,
        company=clean_text(board.get("company")) or board["slug"],
        title=clean_title,
        location=clean_text(location),
        url=job_url,
        program=program,
        posted_at=iso_date(posted_at),
        trusted_us=False,
        description=clean_description,
        metadata={"ats": board["ats"]},
    )


def _greenhouse(board: Board) -> Snapshot:
    source_id, _, _ = _source(board)
    payload = get_json(
        f"https://boards-api.greenhouse.io/v1/boards/{board['slug']}/jobs?content=true"
    )
    if not isinstance(payload, Mapping) or not isinstance(payload.get("jobs"), list):
        raise ValueError("Greenhouse response did not contain jobs")
    observations = []
    for item in payload["jobs"]:
        if not isinstance(item, Mapping):
            continue
        location = item.get("location")
        location_text = location.get("name") if isinstance(location, Mapping) else location
        observation = _observation(
            board,
            external_id=f"greenhouse:{board['slug']}:{item.get('id')}",
            title=item.get("title"),
            location=location_text,
            url=item.get("absolute_url"),
            posted_at=item.get("first_published"),
            description=item.get("content"),
        )
        if observation:
            observations.append(observation)
    return Snapshot(source_id, tuple(observations), complete=True)


def _lever(board: Board) -> Snapshot:
    source_id, _, _ = _source(board)
    payload = get_json(f"https://api.lever.co/v0/postings/{board['slug']}?mode=json")
    if not isinstance(payload, list):
        raise ValueError("Lever response was not an array")
    observations = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        categories = item.get("categories")
        location = categories.get("location") if isinstance(categories, Mapping) else ""
        description_parts = [
            str(item.get(key) or "") for key in ("descriptionPlain", "additionalPlain")
        ]
        lists = item.get("lists")
        if isinstance(lists, list):
            for section in lists:
                if isinstance(section, Mapping):
                    description_parts.extend(
                        (str(section.get("text") or ""), str(section.get("content") or ""))
                    )
        description = " ".join(description_parts)
        created = item.get("createdAt")
        posted = None
        if isinstance(created, int | float):
            posted = datetime.fromtimestamp(created / 1_000, tz=UTC).date().isoformat()
        observation = _observation(
            board,
            external_id=f"lever:{board['slug']}:{item.get('id')}",
            title=item.get("text"),
            location=location,
            url=item.get("hostedUrl") or item.get("applyUrl"),
            posted_at=posted,
            description=description,
        )
        if observation:
            observations.append(observation)
    return Snapshot(source_id, tuple(observations), complete=True)


def _ashby(board: Board) -> Snapshot:
    source_id, _, _ = _source(board)
    payload = get_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{board['slug']}?includeCompensation=true"
    )
    if not isinstance(payload, Mapping) or not isinstance(payload.get("jobs"), list):
        raise ValueError("Ashby response did not contain jobs")
    observations = []
    for item in payload["jobs"]:
        if not isinstance(item, Mapping) or item.get("isListed") is False:
            continue
        job_url = item.get("jobUrl") or item.get("applyUrl")
        external = str(job_url or item.get("title") or "").rstrip("/").rsplit("/", 1)[-1]
        observation = _observation(
            board,
            external_id=f"ashby:{board['slug']}:{external}",
            title=item.get("title"),
            location=item.get("location"),
            url=job_url,
            posted_at=item.get("publishedAt"),
            description=item.get("descriptionPlain") or item.get("descriptionHtml"),
        )
        if observation:
            observations.append(observation)
    return Snapshot(source_id, tuple(observations), complete=True)


def _workday(board: Board) -> Snapshot:
    source_id, _, source_url = _source(board)
    tenant, site, host = board["slug"], board["site"], board["host"]
    api_url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    observations: dict[str, Observation] = {}
    complete = True
    for term in ("intern", "co-op", "new grad"):
        exhausted = False
        for offset in range(0, 100, 20):
            payload = post_json(
                api_url,
                {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term},
                headers={
                    "Accept": "application/json",
                    "Origin": f"https://{host}",
                    "Referer": source_url,
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    ),
                },
            )
            if not isinstance(payload, Mapping) or not isinstance(payload.get("jobPostings"), list):
                raise ValueError("Workday response did not contain jobPostings")
            postings = payload["jobPostings"]
            for item in postings:
                if not isinstance(item, Mapping):
                    continue
                path = str(item.get("externalPath") or "")
                observation = _observation(
                    board,
                    external_id=f"workday:{tenant}:{path or item.get('title')}",
                    title=item.get("title"),
                    location=item.get("locationsText"),
                    url=f"{source_url}{path}" if path else source_url,
                )
                if observation:
                    observations[observation.external_id] = observation
            total = payload.get("total")
            if len(postings) < 20 or (isinstance(total, int) and offset + len(postings) >= total):
                exhausted = True
                break
        if not exhausted:
            complete = False
    return Snapshot(source_id, tuple(observations.values()), complete=complete)


def fetch_board(board: Board) -> Snapshot:
    if not _safe_board(board):
        raise ValueError("board metadata is invalid or unsafe")
    return {
        "greenhouse": _greenhouse,
        "lever": _lever,
        "ashby": _ashby,
        "workday": _workday,
    }[board["ats"]](board)


def fetch_direct_boards(
    boards: list[Board], *, max_workers: int = 16
) -> tuple[tuple[Snapshot, ...], dict[str, str]]:
    snapshots: list[Snapshot] = []
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_board, board): board["key"] for board in boards}
        for future in as_completed(futures):
            key = futures[future]
            try:
                snapshots.append(future.result())
            except (OSError, ValueError, KeyError) as error:
                errors[f"ats:{key}"] = str(error)
    return tuple(sorted(snapshots, key=lambda item: item.source_id)), errors
