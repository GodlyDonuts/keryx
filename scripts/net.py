from __future__ import annotations

import json
import time
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_MAX_BYTES = 50 * 1024 * 1024
_HEADERS = {
    "Accept": "application/json,text/plain,text/markdown;q=0.9,*/*;q=0.8",
    "User-Agent": "Keryx/1.0 (+https://github.com/GodlyDonuts/keryx)",
}


def _request(
    url: str,
    *,
    body: bytes | None = None,
    timeout: float = 25.0,
    extra_headers: dict[str, str] | None = None,
) -> bytes:
    headers = dict(_HEADERS)
    headers.update(extra_headers or {})
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method="POST" if body else "GET")
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed public feeds
                payload = cast(bytes, response.read(_MAX_BYTES + 1))
            if len(payload) > _MAX_BYTES:
                raise ValueError(f"response exceeded {_MAX_BYTES} bytes")
            return payload
        except (HTTPError, URLError, TimeoutError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(0.5 * (2**attempt))
    raise OSError(f"request failed for {url}: {last_error}")


def get_text(url: str) -> str:
    try:
        return _request(url).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"source was not UTF-8: {url}") from error


def get_json(url: str) -> Any:
    try:
        return json.loads(_request(url))
    except json.JSONDecodeError as error:
        raise ValueError(f"source was not valid JSON: {url}") from error


def post_json(url: str, body: dict[str, Any], *, headers: dict[str, str] | None = None) -> Any:
    encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
    try:
        return json.loads(_request(url, body=encoded, extra_headers=headers))
    except json.JSONDecodeError as error:
        raise ValueError(f"source was not valid JSON: {url}") from error
