from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_IDENTITY_QUERY_KEYS = frozenset(
    {
        "gh_jid",
        "job",
        "job_id",
        "jobid",
        "posting_id",
        "position",
        "req",
        "requisitionid",
    }
)


def canonical_url(value: str) -> str:
    """Remove delivery-only URL differences while retaining job identity."""
    parsed = urlsplit(value.strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        return ""
    host = parsed.hostname.casefold()
    if parsed.port and parsed.port not in {80, 443}:
        host = f"{host}:{parsed.port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path.casefold().endswith("/apply"):
        path = path[:-6] or "/"
    path = path.rstrip("/") or "/"
    query = urlencode(
        sorted(
            (key.casefold(), item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=False)
            if key.casefold() in _IDENTITY_QUERY_KEYS
        )
    )
    return urlunsplit(("https", host, path, query, ""))


def job_identity(*, url: str, source: str, external_id: str) -> str:
    canonical = canonical_url(url)
    identity = canonical or f"{source.casefold()}:{external_id.strip()}"
    return "job_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def exact_role_fingerprint(*, company: str, title: str, locations: tuple[str, ...]) -> str:
    """Conservative fallback for records that have no usable URL."""
    fields = [company, title, *sorted(locations)]
    normalized = "|".join(" ".join(field.casefold().split()) for field in fields)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
