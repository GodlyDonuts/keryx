from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from .config import SourceConfig
from .http import fetch_json
from .models import Observation, SourceSnapshot

JsonFetcher = Callable[[str], Any]


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(text for item in value if (text := _text(item)))


def _iso_from_epoch(value: object) -> str | None:
    if not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value, tz=UTC).isoformat().replace("+00:00", "Z")


def _intern_engine(config: SourceConfig, payload: object) -> SourceSnapshot:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("jobs"), list):
        raise ValueError("intern-engine feed must contain a jobs array")
    observations: list[Observation] = []
    for raw in payload["jobs"]:
        if not isinstance(raw, Mapping):
            continue
        external_id = _text(raw.get("id"))
        company = _text(raw.get("company"))
        title = _text(raw.get("title"))
        url = _text(raw.get("url"))
        if not external_id or not company or not title or not url:
            continue
        season_values = _strings(raw.get("seasons"))
        season = _text(raw.get("season"))
        if not season_values and season and season.casefold() != "not stated":
            season_values = (season,)
        location = _text(raw.get("location"))
        observations.append(
            Observation(
                source=config.name,
                external_id=external_id,
                company=company,
                title=title,
                url=url,
                locations=(location,) if location else (),
                category=_text(raw.get("category")) or None,
                cycles=season_values,
                posted_at=_text(raw.get("posted_at")) or None,
                remote=raw.get("remote") if isinstance(raw.get("remote"), bool) else None,
                sponsorship=_text(raw.get("sponsorship")) or None,
                active=True,
                metadata={"upstream_source": _text(raw.get("source"))},
            )
        )
    return SourceSnapshot(config.name, tuple(observations), complete=True)


def _simplify(config: SourceConfig, payload: object) -> SourceSnapshot:
    if not isinstance(payload, list):
        raise ValueError("simplify feed must be an array")
    observations: list[Observation] = []
    for raw in payload:
        if not isinstance(raw, Mapping):
            continue
        external_id = _text(raw.get("id"))
        company = _text(raw.get("company_name"))
        title = _text(raw.get("title"))
        url = _text(raw.get("url"))
        if not external_id or not company or not title or not url:
            continue
        observations.append(
            Observation(
                source=config.name,
                external_id=external_id,
                company=company,
                title=title,
                url=url,
                locations=_strings(raw.get("locations")),
                category=_text(raw.get("category")) or None,
                cycles=_strings(raw.get("terms")),
                posted_at=_iso_from_epoch(raw.get("date_posted")),
                sponsorship=_text(raw.get("sponsorship")) or None,
                active=bool(raw.get("active", False) and raw.get("is_visible", True)),
                metadata={"upstream_source": _text(raw.get("source"))},
            )
        )
    return SourceSnapshot(config.name, tuple(observations), complete=True)


def fetch_source(config: SourceConfig, *, fetcher: JsonFetcher = fetch_json) -> SourceSnapshot:
    payload = fetcher(config.url)
    if config.kind == "intern-engine":
        return _intern_engine(config, payload)
    if config.kind == "simplify":
        return _simplify(config, payload)
    raise ValueError(f"unsupported source kind: {config.kind}")
