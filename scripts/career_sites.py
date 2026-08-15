from __future__ import annotations

import hashlib
import html
import json
import os
import re
import tempfile
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, timedelta
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from .boards import Board, board_from_url
from .models import Observation, Snapshot
from .net import get_public_html
from .normalize import clean_text, reported_job_url

_CAREER_TERMS = re.compile(
    r"(?:career|employment|jobs?|join[-_ ]?(?:us|our team)|open[-_ ]roles?|"
    r"opportunit|positions?|vacanc|work[-_ ]?with[-_ ]?us)",
    re.IGNORECASE,
)
_RAW_URL = re.compile(r"https?:\\?/\\?/[^\s\"'<>]+", re.IGNORECASE)
_RESCAN_DAYS = 7


@dataclass(frozen=True)
class PageLink:
    url: str
    text: str


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[PageLink] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a" or self._href is not None:
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or self._href is None:
            return
        self.links.append(
            PageLink(
                url=urljoin(self.base_url, html.unescape(self._href)),
                text=clean_text(" ".join(self._text)),
            )
        )
        self._href = None
        self._text = []


def _normalized_site_url(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.startswith("http://"):
        raw = f"https://{raw[7:]}"
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    return urlunsplit(("https", parsed.netloc, parsed.path or "/", parsed.query, ""))


def _site_key(url: str) -> str:
    return hashlib.sha256(url.casefold().encode("utf-8")).hexdigest()[:24]


def _parse_links(base_url: str, document: str) -> list[PageLink]:
    parser = _LinkParser(base_url)
    with suppress(AssertionError, ValueError):
        parser.feed(document)
    seen = {link.url for link in parser.links}
    expanded = document.replace("\\u002F", "/").replace("\\u002f", "/")
    for match in _RAW_URL.findall(expanded):
        url = html.unescape(match.replace("\\/", "/")).rstrip("),.;")
        if url not in seen:
            parser.links.append(PageLink(url=url, text=""))
            seen.add(url)
    return parser.links


def _title_parts(value: object) -> tuple[str, set[str]]:
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())
    return normalized, set(normalized.split())


def _title_score(expected: str, candidate: str) -> float:
    expected_text, expected_tokens = _title_parts(expected)
    candidate_text, candidate_tokens = _title_parts(candidate)
    if not expected_text or not candidate_text:
        return 0.0
    if expected_text == candidate_text:
        return 1.0
    overlap = (
        len(expected_tokens & candidate_tokens) / len(expected_tokens | candidate_tokens)
        if expected_tokens | candidate_tokens
        else 0.0
    )
    sequence = SequenceMatcher(None, expected_text, candidate_text).ratio()
    return sequence if sequence >= 0.96 and overlap >= 0.8 else 0.0


def _career_pages(links: Iterable[PageLink], *, limit: int = 6) -> list[str]:
    candidates: dict[str, int] = {}
    for link in links:
        parsed = urlsplit(link.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        if board_from_url(link.url, "discovery") is not None:
            continue
        if _CAREER_TERMS.search(f"{parsed.path} {link.text}"):
            normalized = _normalized_site_url(link.url)
            if normalized:
                score = 2 if _CAREER_TERMS.fullmatch(link.text.strip()) else 1
                candidates[normalized] = max(candidates.get(normalized, 0), score)
    return [
        url
        for url, _ in sorted(candidates.items(), key=lambda item: (item[1], item[0]), reverse=True)[
            :limit
        ]
    ]


def _resolved_observations(
    company: str,
    source_url: str,
    discoveries: list[Observation],
    links: list[PageLink],
) -> tuple[Observation, ...]:
    source_id = f"career-site:{_site_key(source_url)}"
    observations: list[Observation] = []
    for discovery in discoveries:
        candidates: dict[str, float] = {}
        for link in links:
            decision = reported_job_url(link.url)
            if not decision.url or decision.host == "jobright.ai":
                continue
            score = _title_score(discovery.title, link.text)
            if score:
                candidates[decision.url] = max(candidates.get(decision.url, 0.0), score)
        if not candidates:
            continue
        ranked = sorted(candidates.items(), key=lambda item: (item[1], item[0]), reverse=True)
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            continue
        job_url = ranked[0][0]
        observations.append(
            Observation(
                source_id=source_id,
                source_label="Employer careers",
                source_url=source_url,
                external_id=job_url,
                company=company,
                title=discovery.title,
                location=discovery.location,
                url=job_url,
                program=discovery.program,
                cycle=discovery.cycle,
                posted_at=discovery.posted_at,
                sponsorship=discovery.sponsorship,
                trusted_us=discovery.trusted_us,
                metadata={"resolved_from": discovery.source_id},
            )
        )
    return tuple(observations)


def _scan_site(
    company: str,
    source_url: str,
    discoveries: list[Observation],
) -> tuple[Snapshot, list[Board]]:
    final_url, document = get_public_html(source_url)
    links = _parse_links(final_url, document)
    followed = {final_url}
    for career_url in _career_pages(links):
        if career_url in followed:
            continue
        followed.add(career_url)
        try:
            career_final, career_document = get_public_html(career_url)
        except (OSError, ValueError):
            continue
        links.extend(_parse_links(career_final, career_document))

    boards: dict[str, Board] = {}
    for link in links:
        board = board_from_url(link.url, company)
        if board is not None:
            boards[board["key"]] = board
    source_id = f"career-site:{_site_key(source_url)}"
    snapshot = Snapshot(
        source_id,
        _resolved_observations(company, source_url, discoveries, links),
        complete=True,
    )
    return snapshot, [boards[key] for key in sorted(boards)]


def scan_company_sites(
    discoveries: Iterable[Observation],
    previous_payload: Mapping[str, Any],
    *,
    today: str,
    limit: int = 48,
    max_workers: int = 16,
    force: bool = False,
) -> tuple[tuple[Snapshot, ...], list[Board], dict[str, Any], dict[str, str]]:
    grouped: dict[str, tuple[str, str, list[Observation], str]] = {}
    for discovery in discoveries:
        url = _normalized_site_url(discovery.metadata.get("company_url"))
        if not url:
            continue
        key = _site_key(url)
        if key not in grouped:
            grouped[key] = (discovery.company, url, [], discovery.posted_at or "")
        company, stored_url, roles, newest = grouped[key]
        roles.append(discovery)
        grouped[key] = (company, stored_url, roles, max(newest, discovery.posted_at or ""))

    previous_sites = {
        str(item.get("key")): dict(item)
        for item in previous_payload.get("sites", [])
        if isinstance(item, Mapping) and item.get("key")
    }
    unscanned: list[tuple[str, str]] = []
    stale: list[tuple[str, str]] = []
    cutoff = (date.fromisoformat(today) - timedelta(days=_RESCAN_DAYS)).isoformat()
    for key, (_, _, _, newest) in grouped.items():
        last_scanned = str(previous_sites.get(key, {}).get("last_scanned") or "")
        if force or not last_scanned:
            unscanned.append((newest, key))
        elif (
            previous_sites.get(key, {}).get("error") and last_scanned < today
        ) or last_scanned <= cutoff:
            stale.append((last_scanned, key))
    unscanned.sort(reverse=True)
    stale.sort()
    selected = [key for _, key in [*unscanned, *stale][: max(0, limit)]]

    snapshots: list[Snapshot] = []
    boards: dict[str, Board] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_scan_site, grouped[key][0], grouped[key][1], grouped[key][2]): key
            for key in selected
        }
        for future in as_completed(futures):
            key = futures[future]
            company, url, _, _ = grouped[key]
            record = previous_sites.get(key, {"key": key, "company": company, "url": url})
            record.update({"company": company, "url": url, "last_scanned": today})
            try:
                snapshot, found_boards = future.result()
                snapshots.append(snapshot)
                for board in found_boards:
                    boards[board["key"]] = board
                record["boards"] = [board["key"] for board in found_boards]
                record["resolved_roles"] = len(snapshot.observations)
                record.pop("error", None)
            except (OSError, ValueError) as error:
                message = str(error)
                errors[f"career-site:{key}"] = message
                record["error"] = message[:240]
            previous_sites[key] = record

    payload = {
        "schema_version": 1,
        "sites": [previous_sites[key] for key in sorted(previous_sites)],
    }
    return (
        tuple(sorted(snapshots, key=lambda item: item.source_id)),
        [boards[key] for key in sorted(boards)],
        payload,
        errors,
    )


def save_site_state(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
