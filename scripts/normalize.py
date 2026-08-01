from __future__ import annotations

import hashlib
import html
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import Observation, Program

_US_STATE_CODES = (
    "AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|"
    "MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC"
)
_US_STATE_NAMES = (
    "Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|"
    "Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|"
    "Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|"
    "New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|"
    "Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|"
    "Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|District of Columbia"
)
_EXPLICIT_US_MARKER = re.compile(
    rf"(?:\bUnited States\b|\bUSA\b|\bU\.S\.\b|\bUS remote\b|remote[^|;]*\bUS\b|"
    rf"\b(?:{_US_STATE_NAMES})\b)",
    re.IGNORECASE,
)
_US_STATE_CODE = re.compile(rf"(?:,\s*|\b)(?:{_US_STATE_CODES})\b")
_FOREIGN_MARKER = re.compile(
    r"\b(?:Canada|Canadian|Toronto|Vancouver|Montreal|Calgary|Ottawa|Edmonton|Kitchener|"
    r"United Kingdom|UK|London|India|Germany|France|Ireland|Poland|Singapore|Australia|"
    r"Netherlands|Spain|Sweden|Mexico|Brazil|China|Japan|Taiwan|Israel)\b",
    re.IGNORECASE,
)
_CANADIAN_PROVINCE = re.compile(r"(?:,\s*|\b)(?:AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT)\b")
_FOREIGN_URL = re.compile(
    r"(?:[-_/](?:canada|india|united-kingdom|uk|germany|france|singapore|australia)(?:[-_/]|$)|"
    r"(?:CAD|CAN)[-_]Remote)",
    re.IGNORECASE,
)
_TECH = re.compile(
    r"\b(?:software|developer|engineer|engineering|data|machine learning|ML|AI|artificial "
    r"intelligence|quant|quantitative|trading|technology|IT|cyber|security|product|hardware|"
    r"firmware|electrical|computer|robotics|systems|cloud|research|analyst|analytics|frontend|"
    r"backend|full[ -]?stack|devops|infrastructure)\b",
    re.IGNORECASE,
)
_INTERN = re.compile(r"\b(?:intern(?:ship)?|co[ -]?op)\b", re.IGNORECASE)
_NEW_GRAD = re.compile(
    r"\b(?:new grad(?:uate)?|university grad(?:uate)?|college grad(?:uate)?|early career|"
    r"entry[ -]?level|graduate program)\b",
    re.IGNORECASE,
)
_IDENTITY_QUERY = frozenset({"gh_jid", "job", "job_id", "jobid", "posting_id", "position"})


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"!\[[^]]*]\([^)]*\)", "", text)
    text = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    return " ".join(text.replace("|", "/").split()).strip()


def canonical_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    host = parsed.hostname.casefold()
    path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/")
    if path.casefold().endswith("/apply"):
        path = path[:-6]
    query_items = [
        (key.casefold(), item)
        for key, item in parse_qsl(parsed.query)
        if key.casefold() in _IDENTITY_QUERY
    ]
    return urlunsplit(("https", host, path or "/", urlencode(sorted(query_items)), ""))


def external_identity(url: str, fallback: str) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    parts = [part for part in parsed.path.split("/") if part and part.casefold() != "apply"]
    query = dict(parse_qsl(parsed.query))
    if "greenhouse.io" in host and "jobs" in parts:
        index = parts.index("jobs")
        if index + 1 < len(parts):
            return f"greenhouse:{parts[index + 1]}"
    if query.get("gh_jid"):
        return f"greenhouse:{query['gh_jid']}"
    if host == "jobs.lever.co" and len(parts) >= 2:
        return f"lever:{parts[1]}"
    if host == "jobs.ashbyhq.com" and len(parts) >= 2:
        return f"ashby:{parts[1]}"
    if "myworkdayjobs.com" in host or "myworkdaysite.com" in host:
        tenant = host.split(".")[0]
        requisition = parts[-1].rsplit("_", 1)[-1] if parts else fallback
        return f"workday:{tenant}:{requisition}"
    canonical = canonical_url(url)
    return canonical or fallback


def job_id(observation: Observation) -> str:
    identity = external_identity(observation.url, observation.external_id)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"job_{digest}"


def is_us_role(location: str, *, trusted_us: bool, context: str = "") -> bool:
    explicit_us = bool(_EXPLICIT_US_MARKER.search(location))
    state_code = bool(_US_STATE_CODE.search(location))
    foreign = bool(_FOREIGN_MARKER.search(location) or _CANADIAN_PROVINCE.search(location))
    if _FOREIGN_URL.search(context) and not explicit_us:
        return False
    if explicit_us or state_code:
        return True
    if foreign or _FOREIGN_MARKER.search(context):
        return False
    return trusted_us


def infer_program(title: str) -> Program | None:
    if _INTERN.search(title):
        return "internship"
    if _NEW_GRAD.search(title):
        return "new-grad"
    return None


def is_technical(title: str, description: str = "") -> bool:
    return bool(_TECH.search(f"{title} {description[:2_000]}"))


def infer_cycle(*, title: str, description: str, program: Program, hint: str | None = None) -> str:
    text = f"{title} {description[:4_000]}".casefold()
    if program == "internship":
        if re.search(r"(?:fall|autumn)[^\n]{0,25}2026|2026[^\n]{0,25}(?:fall|autumn)", text):
            return "fall-2026"
        if re.search(r"(?:summer)[^\n]{0,25}2027|2027[^\n]{0,25}(?:summer)", text):
            return "summer-2027"
        if re.search(r"(?:spring)[^\n]{0,25}2027|2027[^\n]{0,25}(?:spring)", text):
            return "spring-2027"
        if re.search(r"(?:winter)[^\n]{0,25}2027|2027[^\n]{0,25}(?:winter)", text):
            return "winter-2027"
        if hint in {"fall-2026", "summer-2027", "spring-2027", "winter-2027"}:
            return hint
        return "unscheduled"
    explicit_years = re.findall(r"\b20(?:26|27)\b", text)
    if "2027" in explicit_years:
        return "2027"
    if "2026" in explicit_years:
        return "2026"
    if hint in {"2026", "2027"}:
        return hint
    return "unscheduled"


def epoch_date(value: object) -> str | None:
    if not isinstance(value, int | float):
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC).date().isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def iso_date(value: object) -> str | None:
    text = str(value or "").strip()
    match = re.match(r"(20\d{2}-\d{2}-\d{2})", text)
    return match.group(1) if match else None
