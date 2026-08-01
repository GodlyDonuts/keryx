from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

_MAX_FEED_BYTES = 20 * 1024 * 1024


def fetch_json(url: str, *, timeout: float = 30.0) -> Any:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("feed URL must be an absolute HTTPS URL")
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "RoleBeacon/0.1"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - explicit HTTPS above
            final = urlsplit(response.geturl())
            if final.scheme != "https" or not final.hostname:
                raise ValueError("feed redirected outside HTTPS")
            payload = response.read(_MAX_FEED_BYTES + 1)
    except (HTTPError, URLError) as error:
        raise OSError(f"could not fetch feed: {error}") from error
    if len(payload) > _MAX_FEED_BYTES:
        raise ValueError("feed exceeds the 20 MiB limit")
    try:
        return json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("feed did not return valid UTF-8 JSON") from error
