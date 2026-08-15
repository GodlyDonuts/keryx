from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

_MAX_BYTES = 50 * 1024 * 1024
_MAX_HTML_BYTES = 3 * 1024 * 1024
_HEADERS = {
    "Accept": "application/json,text/plain,text/markdown;q=0.9,*/*;q=0.8",
    "User-Agent": "Keryx/1.0 (+https://github.com/GodlyDonuts/keryx)",
}
_EXACT_NETWORK_HOSTS = frozenset(
    {
        "api.ashbyhq.com",
        "api.lever.co",
        "api.smartrecruiters.com",
        "apply.workable.com",
        "boards-api.greenhouse.io",
        "raw.githubusercontent.com",
    }
)
_NETWORK_HOST_SUFFIXES = (
    ".bamboohr.com",
    ".myworkdayjobs.com",
    ".myworkdaysite.com",
    ".oraclecloud.com",
)
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> None:
        return None


_OPENER = build_opener(_NoRedirects)


def _validated_network_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host_value = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise ValueError("outbound URL has an invalid authority") from error
    if parsed.scheme != "https" or not host_value:
        raise ValueError("outbound requests require HTTPS and a hostname")
    if parsed.username is not None or parsed.password is not None or port not in {None, 443}:
        raise ValueError("outbound URL credentials and nonstandard ports are forbidden")
    try:
        host = host_value.encode("ascii", "strict").decode("ascii").casefold()
    except UnicodeError as error:
        raise ValueError("outbound hostname must be ASCII") from error
    if any(not _HOST_LABEL.fullmatch(label) for label in host.split(".")):
        raise ValueError("outbound hostname is invalid")
    if host not in _EXACT_NETWORK_HOSTS and not any(
        host.endswith(suffix) for suffix in _NETWORK_HOST_SUFFIXES
    ):
        raise ValueError(f"outbound host is not allowlisted: {host}")
    return url


def _validated_public_url(url: str) -> str:
    """Validate an official company page without restricting it to known ATS hosts."""

    try:
        parsed = urlsplit(url)
        host_value = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise ValueError("public URL has an invalid authority") from error
    if parsed.scheme != "https" or not host_value:
        raise ValueError("public requests require HTTPS and a hostname")
    if parsed.username is not None or parsed.password is not None or port not in {None, 443}:
        raise ValueError("public URL credentials and nonstandard ports are forbidden")
    try:
        host = host_value.encode("ascii", "strict").decode("ascii").casefold()
    except UnicodeError as error:
        raise ValueError("public hostname must be ASCII") from error
    if any(not _HOST_LABEL.fullmatch(label) for label in host.split(".")):
        raise ValueError("public hostname is invalid")
    addresses: tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]
    try:
        literal = ipaddress.ip_address(host)
        addresses = (literal,)
    except ValueError:
        try:
            addresses = tuple(
                {
                    ipaddress.ip_address(item[4][0])
                    for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
                }
            )
        except (OSError, ValueError) as error:
            raise ValueError(f"public hostname did not resolve: {host}") from error
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("public hostname resolves to a non-public address")
    return url


def _request(
    url: str,
    *,
    body: bytes | None = None,
    timeout: float = 25.0,
    extra_headers: dict[str, str] | None = None,
) -> bytes:
    _validated_network_url(url)
    headers = dict(_HEADERS)
    headers.update(extra_headers or {})
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method="POST" if body else "GET")
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with _OPENER.open(request, timeout=timeout) as response:  # noqa: S310
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


def get_public_html(url: str, *, timeout: float = 10.0) -> tuple[str, str]:
    """Fetch a bounded public company page while validating every redirect target."""

    current = url
    for _ in range(5):
        _validated_public_url(current)
        request = Request(current, headers={**_HEADERS, "Accept": "text/html,*/*;q=0.8"})
        try:
            with _OPENER.open(request, timeout=timeout) as response:  # noqa: S310
                payload = cast(bytes, response.read(_MAX_HTML_BYTES + 1))
                final_url = response.geturl()
        except HTTPError as error:
            if error.code not in {301, 302, 303, 307, 308}:
                raise OSError(f"public request failed for {current}: {error}") from error
            location = error.headers.get("Location")
            if not location:
                raise OSError(f"public redirect lacked a destination: {current}") from error
            current = urljoin(current, location)
            continue
        except (URLError, TimeoutError) as error:
            raise OSError(f"public request failed for {current}: {error}") from error
        if len(payload) > _MAX_HTML_BYTES:
            raise ValueError(f"public response exceeded {_MAX_HTML_BYTES} bytes")
        _validated_public_url(final_url)
        try:
            return final_url, payload.decode("utf-8")
        except UnicodeDecodeError:
            return final_url, payload.decode("utf-8", errors="replace")
    raise OSError(f"too many public redirects: {url}")


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
