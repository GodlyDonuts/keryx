from __future__ import annotations

import re
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import TypedDict
from urllib.parse import urlencode, urlsplit

from .models import Observation, Snapshot
from .net import get_json, get_text, post_json
from .normalize import clean_text, infer_program, is_technical, iso_date, sanitize_job_url

_BOARD_COMPONENT = re.compile(r"(?:[A-Za-z0-9._-]|%[0-9A-Fa-f]{2}){1,128}")
_RESERVED_BOARD_COMPONENTS = (
    "assets",
    "embed",
    "external_greenhouse_job_boards",
    "introduceyourself",
    "job_board_renderer",
    "jobalerts",
    "jobs",
    "login",
    "logo",
    "my-applications",
    "search",
    "userhome",
    "v1",
)


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


def _reserved_component(value: object) -> bool:
    lowered = str(value or "").casefold()
    return any(
        lowered == item or lowered.startswith(f"{item}%") for item in _RESERVED_BOARD_COMPONENTS
    )


def _safe_board(board: Board) -> bool:
    ats = board.get("ats")
    if ats not in {
        "greenhouse",
        "lever",
        "ashby",
        "bamboohr",
        "oracle",
        "smartrecruiters",
        "workable",
        "workday",
    }:
        return False
    if not _safe_component(board.get("slug")):
        return False
    if _reserved_component(board.get("slug")):
        return False
    if ats in {"greenhouse", "lever", "ashby", "smartrecruiters", "workable"}:
        return True
    host = str(board.get("host") or "").casefold()
    if ats == "bamboohr":
        return host == f"{str(board.get('slug') or '').casefold()}.bamboohr.com"
    if ats == "oracle":
        return (
            host.endswith(".oraclecloud.com")
            and bool(sanitize_job_url(f"https://{host}/").url)
            and _safe_component(board.get("site"))
            and not _reserved_component(board.get("site"))
        )
    if not host.endswith((".myworkdayjobs.com", ".myworkdaysite.com")):
        return False
    return (
        bool(sanitize_job_url(f"https://{host}/").url)
        and _safe_component(board.get("site"))
        and not _reserved_component(board.get("site"))
    )


def board_from_url(url: str, company: str) -> Board | None:
    safe_url = sanitize_job_url(url).url
    if not safe_url:
        return None
    parsed = urlsplit(safe_url)
    host = (parsed.hostname or "").casefold()
    parts = [part for part in parsed.path.split("/") if part]
    if "greenhouse.io" in host:
        slug = ""
        if "jobs" in parts:
            index = parts.index("jobs")
            if index >= 1:
                slug = parts[index - 1]
        elif parts:
            slug = parts[0]
        if slug:
            board: Board = {
                "key": f"greenhouse:{slug.casefold()}",
                "ats": "greenhouse",
                "company": company,
                "slug": slug,
            }
            return board if _safe_board(board) else None
    if host == "jobs.lever.co" and parts:
        slug = parts[0]
        board = {
            "key": f"lever:{slug.casefold()}",
            "ats": "lever",
            "company": company,
            "slug": slug,
        }
        return board if _safe_board(board) else None
    if host == "jobs.ashbyhq.com" and parts:
        slug = parts[0]
        board = {
            "key": f"ashby:{slug.casefold()}",
            "ats": "ashby",
            "company": company,
            "slug": slug,
        }
        return board if _safe_board(board) else None
    if host == "jobs.smartrecruiters.com" and parts:
        slug = parts[0]
        board = {
            "key": f"smartrecruiters:{slug.casefold()}",
            "ats": "smartrecruiters",
            "company": company,
            "slug": slug,
        }
        return board if _safe_board(board) else None
    if host == "apply.workable.com" and parts:
        slug = parts[0]
        board = {
            "key": f"workable:{slug.casefold()}",
            "ats": "workable",
            "company": company,
            "slug": slug,
        }
        return board if _safe_board(board) else None
    if host.endswith(".bamboohr.com") and "careers" in [part.casefold() for part in parts]:
        slug = host.split(".")[0]
        board = {
            "key": f"bamboohr:{slug.casefold()}",
            "ats": "bamboohr",
            "company": company,
            "slug": slug,
            "host": host,
        }
        return board if _safe_board(board) else None
    if host.endswith(".oraclecloud.com"):
        lowered = [part.casefold() for part in parts]
        if "sites" in lowered:
            index = lowered.index("sites")
            if index + 1 < len(parts):
                site = parts[index + 1]
                slug = host.split(".")[0]
                board = {
                    "key": f"oracle:{host}:{site.casefold()}",
                    "ats": "oracle",
                    "company": company,
                    "slug": slug,
                    "site": site,
                    "host": host,
                }
                return board if _safe_board(board) else None
    if "myworkdayjobs.com" in host:
        labels = host.split(".")
        tenant = labels[0]
        wd = labels[1] if len(labels) > 1 else "wd1"
        lowered = [part.casefold() for part in parts]
        job_index = lowered.index("job") if "job" in lowered else len(parts)
        site_parts = [
            part
            for part in parts[:job_index]
            if not re.fullmatch(r"[a-z]{2}-[a-z]{2}", part, flags=re.IGNORECASE)
        ]
        if not site_parts:
            return None
        site = site_parts[0]
        board = {
            "key": f"workday:{host}:{tenant.casefold()}:{site.casefold()}",
            "ats": "workday",
            "company": company,
            "slug": tenant,
            "site": site,
            "host": host,
            "wd": wd,
        }
        return board if _safe_board(board) else None
    if "myworkdaysite.com" in host and len(parts) >= 4 and parts[0] == "recruiting":
        tenant, site = parts[1], parts[2]
        board = {
            "key": f"workday:{host}:{tenant.casefold()}:{site.casefold()}",
            "ats": "workday",
            "company": company,
            "slug": tenant,
            "site": site,
            "host": host,
        }
        return board if _safe_board(board) else None
    return None


def board_from_observation(observation: Observation) -> Board | None:
    board = board_from_url(observation.url, observation.company)
    if board is not None:
        return board
    external = observation.external_id.split(":")
    if len(external) >= 3 and external[0] == "greenhouse":
        slug = external[1]
        if _safe_component(slug):
            return {
                "key": f"greenhouse:{slug.casefold()}",
                "ats": "greenhouse",
                "company": observation.company,
                "slug": slug,
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
    elif ats == "smartrecruiters":
        url = f"https://jobs.smartrecruiters.com/{slug}"
    elif ats == "workable":
        url = f"https://apply.workable.com/{slug}/"
    elif ats == "bamboohr":
        url = f"https://{board['host']}/careers/"
    elif ats == "oracle":
        url = f"https://{board['host']}/hcmUI/CandidateExperience/en/sites/{board['site']}"
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


def _smartrecruiters(board: Board) -> Snapshot:
    source_id, _, _ = _source(board)
    observations: list[Observation] = []
    complete = True
    for offset in range(0, 500, 100):
        payload = get_json(
            f"https://api.smartrecruiters.com/v1/companies/{board['slug']}/postings"
            f"?limit=100&offset={offset}"
        )
        if not isinstance(payload, Mapping) or not isinstance(payload.get("content"), list):
            raise ValueError("SmartRecruiters response did not contain postings")
        postings = payload["content"]
        for item in postings:
            if not isinstance(item, Mapping):
                continue
            location = item.get("location")
            if isinstance(location, Mapping):
                location_text = ", ".join(
                    str(location.get(key) or "")
                    for key in ("city", "region", "country")
                    if location.get(key)
                )
            else:
                location_text = str(location or "")
            identifier = str(item.get("id") or "")
            job_url = (
                f"https://jobs.smartrecruiters.com/{board['slug']}/{identifier}"
                if identifier
                else ""
            )
            observation = _observation(
                board,
                external_id=f"smartrecruiters:{board['slug']}:{identifier}",
                title=item.get("name"),
                location=location_text,
                url=job_url,
                posted_at=item.get("releasedDate"),
            )
            if observation:
                observations.append(observation)
        total = payload.get("totalFound")
        if len(postings) < 100 or (isinstance(total, int) and offset + len(postings) >= total):
            break
    else:
        complete = False
    return Snapshot(source_id, tuple(observations), complete=complete)


_WORKABLE_ROW = re.compile(
    r"^\|\s*(?P<title>.*?)\s*\|\s*(?P<department>.*?)\s*\|\s*"
    r"(?P<location>.*?)\s*\|\s*(?P<worktype>.*?)\s*\|\s*"
    r"(?P<salary>.*?)\s*\|\s*(?P<posted>.*?)\s*\|\s*"
    r"\[View\]\(https://apply\.workable\.com/[^/]+/jobs/view/"
    r"(?P<identifier>[A-Za-z0-9_-]+)\.md\)\s*\|$"
)


def _workable(board: Board) -> Snapshot:
    source_id, _, _ = _source(board)
    rows: dict[str, tuple[str, str, str]] = {}
    query = urlencode({"location[0][country]": "United States"})
    document = get_text(f"https://apply.workable.com/{board['slug']}/jobs.md?{query}")
    for line in document.splitlines():
        match = _WORKABLE_ROW.match(line)
        if not match:
            continue
        identifier = match.group("identifier")
        rows.setdefault(
            identifier,
            (
                clean_text(match.group("title")),
                clean_text(match.group("location")),
                iso_date(match.group("posted")) or "",
            ),
        )

    observations: list[Observation] = []
    for identifier, (title, location, posted_at) in rows.items():
        observation = _observation(
            board,
            external_id=f"workable:{board['slug']}:{identifier}",
            title=title,
            location=location,
            url=f"https://apply.workable.com/{board['slug']}/j/{identifier}/",
            posted_at=posted_at,
        )
        if observation:
            observations.append(observation)
    return Snapshot(source_id, tuple(observations), complete=True)


def _bamboohr(board: Board) -> Snapshot:
    source_id, _, source_url = _source(board)
    payload = get_json(f"https://{board['host']}/careers/list")
    if not isinstance(payload, Mapping) or not isinstance(payload.get("result"), list):
        raise ValueError("BambooHR response did not contain jobs")
    observations: list[Observation] = []
    for item in payload["result"]:
        if not isinstance(item, Mapping):
            continue
        title = clean_text(item.get("jobOpeningName"))
        if infer_program(title) is None or not is_technical(title):
            continue
        identifier = str(item.get("id") or "")
        if not identifier:
            continue
        location = item.get("location")
        if isinstance(location, Mapping):
            location_text = ", ".join(
                str(location.get(key) or "") for key in ("city", "state") if location.get(key)
            )
        else:
            location_text = str(location or "")
        job_url = f"{source_url}{identifier}/"
        try:
            description = get_text(job_url)
        except OSError:
            description = ""
        observation = _observation(
            board,
            external_id=f"bamboohr:{board['slug']}:{identifier}",
            title=title,
            location=location_text,
            url=job_url,
            description=description,
        )
        if observation:
            observations.append(observation)
    return Snapshot(source_id, tuple(observations), complete=True)


def _oracle(board: Board) -> Snapshot:
    source_id, _, source_url = _source(board)
    rows: dict[str, Mapping[str, object]] = {}
    for term in ("intern", "co-op", "new grad"):
        for offset in (0, 100):
            finder = (
                f"findReqs;siteNumber={board['site']},keyword={term},"
                f"workLocationCountryCode=US,limit=100,offset={offset}"
            )
            query = urlencode({"onlyData": "true", "expand": "requisitionList", "finder": finder})
            payload = get_json(
                f"https://{board['host']}/hcmRestApi/resources/latest/"
                f"recruitingCEJobRequisitions?{query}"
            )
            if not isinstance(payload, Mapping) or not isinstance(payload.get("items"), list):
                raise ValueError("Oracle Recruiting response did not contain a search result")
            items = payload["items"]
            if not items or not isinstance(items[0], Mapping):
                break
            result = items[0]
            requisitions = result.get("requisitionList")
            if not isinstance(requisitions, list):
                raise ValueError("Oracle Recruiting response did not contain requisitions")
            for item in requisitions:
                if not isinstance(item, Mapping):
                    continue
                title = clean_text(item.get("Title"))
                identifier = str(item.get("Id") or "")
                if identifier and infer_program(title) is not None and is_technical(title):
                    rows.setdefault(identifier, item)
            total = result.get("TotalJobsCount")
            if len(requisitions) < 100 or (
                isinstance(total, int) and offset + len(requisitions) >= total
            ):
                break

    observations: list[Observation] = []
    for identifier, row in rows.items():
        try:
            detail = get_json(
                f"https://{board['host']}/hcmRestApi/resources/latest/"
                f"recruitingCEJobRequisitionDetails/{identifier}?onlyData=true"
            )
        except OSError:
            detail = {}
        if not isinstance(detail, Mapping):
            detail = {}
        description = " ".join(
            str(detail.get(key) or row.get(key) or "")
            for key in (
                "ExternalDescriptionStr",
                "ExternalQualificationsStr",
                "ExternalResponsibilitiesStr",
                "ShortDescriptionStr",
            )
        )
        observation = _observation(
            board,
            external_id=f"oracle:{board['host']}:{board['site']}:{identifier}",
            title=row.get("Title"),
            location=row.get("PrimaryLocation"),
            url=f"{source_url}/job/{identifier}",
            posted_at=row.get("PostedDate"),
            description=description,
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
        "bamboohr": _bamboohr,
        "oracle": _oracle,
        "smartrecruiters": _smartrecruiters,
        "workable": _workable,
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
