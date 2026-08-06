from __future__ import annotations

import re
from typing import Any

from .models import Observation
from .normalize import clean_text

ACADEMIC_EXTRACTOR_VERSION = 1

_MONTHS = {
    "jan": (1, "Jan"),
    "january": (1, "Jan"),
    "feb": (2, "Feb"),
    "february": (2, "Feb"),
    "mar": (3, "Mar"),
    "march": (3, "Mar"),
    "apr": (4, "Apr"),
    "april": (4, "Apr"),
    "may": (5, "May"),
    "jun": (6, "Jun"),
    "june": (6, "Jun"),
    "jul": (7, "Jul"),
    "july": (7, "Jul"),
    "aug": (8, "Aug"),
    "august": (8, "Aug"),
    "sep": (9, "Sep"),
    "sept": (9, "Sep"),
    "september": (9, "Sep"),
    "oct": (10, "Oct"),
    "october": (10, "Oct"),
    "nov": (11, "Nov"),
    "november": (11, "Nov"),
    "dec": (12, "Dec"),
    "december": (12, "Dec"),
}
_MONTH_PATTERN = "|".join(sorted(_MONTHS, key=len, reverse=True))
_SEASON_PATTERN = "spring|summer|fall|autumn|winter"
_DATE_REFERENCE = re.compile(
    rf"\b(?:(?P<month>{_MONTH_PATTERN})\.?\s+(?P<month_year>20\d{{2}})|"
    rf"(?P<season>{_SEASON_PATTERN})\s+(?:of\s+)?(?P<season_year>20\d{{2}})|"
    r"(?P<year>20\d{2}))\b",
    re.IGNORECASE,
)
_THREE_SHARED_SEASONS = re.compile(
    rf"\b(?P<first>{_SEASON_PATTERN})\s*,\s*(?P<second>{_SEASON_PATTERN})\s*,?\s*"
    rf"(?:or|and)\s+(?P<third>{_SEASON_PATTERN})\s+of\s+(?P<year>20\d{{2}})\b",
    re.IGNORECASE,
)
_TWO_SHARED_SEASONS = re.compile(
    rf"\b(?P<first>{_SEASON_PATTERN})\s+(?:or|and)\s+"
    rf"(?P<second>{_SEASON_PATTERN})\s+of\s+(?P<year>20\d{{2}})\b",
    re.IGNORECASE,
)
_GRADUATION_TRIGGER = re.compile(
    r"\b(?:graduat(?:e|es|ed|ing|ion)(?:\s+date)?|class\s+of)\b",
    re.IGNORECASE,
)
_CURRENTLY_ENROLLED = re.compile(
    r"\b(?:current\s+enrollment|currently\s+enrolled|enrolled\s+(?:full[- ]time\s+)?in|"
    r"currently\s+pursuing|pursuing\s+(?:a|an|your)\s+(?:bachelor|master|doctoral|ph\.?d))",
    re.IGNORECASE,
)
_RETURN_TO_SCHOOL = re.compile(
    r"\b(?:return(?:ing)?\s+to\s+(?:school|college|university|a\s+degree\s+program)|"
    r"(?:at\s+least\s+)?(?:one|1|a)\s+(?:academic\s+)?(?:semester|quarter|term)"
    r"(?:\s+of\s+(?:school|study|coursework))?\s+remaining|"
    r"enrolled\s+(?:in\s+school\s+)?for\s+(?:at\s+least\s+)?(?:one|1|a)\s+"
    r"(?:academic\s+)?(?:semester|quarter|term)\s+(?:after|following|post)|"
    r"continue\s+(?:their|your)\s+(?:education|degree|studies))\b",
    re.IGNORECASE,
)
_RANGE_CONNECTOR = re.compile(
    r"\b(?:through|until|to|and|or)\b|\s[-–—]\s",
    re.IGNORECASE,
)
_LOWER_BOUND = re.compile(
    r"\b(?:no\s+earlier\s+than|on\s+or\s+after|or\s+later|after)\b",
    re.IGNORECASE,
)
_UPPER_BOUND = re.compile(
    r"\b(?:no\s+later\s+than|on\s+or\s+before|or\s+earlier|before|by)\b",
    re.IGNORECASE,
)
_PREFERRED_INLINE = re.compile(
    r"\b(?:preferred|ideally|nice\s+to\s+have|a\s+plus|bonus)\b",
    re.IGNORECASE,
)
_REQUIRED_INLINE = re.compile(
    r"\b(?:must|required|need(?:s)?\s+to|have\s+to|only\s+applicants?\s+who)\b",
    re.IGNORECASE,
)
_PREFERRED_HEADING = re.compile(
    r"\b(?:preferred|desired|nice[- ]to[- ]have)\s+(?:qualifications?|skills?|experience)\b",
    re.IGNORECASE,
)
_REQUIRED_HEADING = re.compile(
    r"\b(?:minimum|basic|required)\s+qualifications?\b|"
    r"\b(?:eligibility|candidate)\s+requirements?\b|"
    r"\bwhat\s+(?:you(?:'ll)?|we)\s+(?:need|require)\b",
    re.IGNORECASE,
)


def _context(
    text: str,
    start: int,
    end: int,
    *,
    radius: int = 260,
    max_chars: int = 280,
) -> str:
    """Return bounded evidence that always contains the matched condition."""
    left_limit = max(0, start - radius)
    right_limit = min(len(text), end + radius)
    left = max((text.rfind(mark, left_limit, start) for mark in (".", ";", "!", "?")), default=-1)
    right_candidates = [
        position
        for mark in (".", ";", "!", "?")
        if (position := text.find(mark, end, right_limit)) >= 0
    ]
    right = min(right_candidates) + 1 if right_candidates else right_limit
    excerpt_start = left + 1
    excerpt_end = right
    whole = clean_text(text[excerpt_start:excerpt_end])
    if len(whole) <= max_chars:
        return whole

    # Keep enough lead-in to understand the condition while guaranteeing the trigger itself is
    # retained. Ellipses make clipping explicit rather than presenting a fragment as a sentence.
    clip_start = max(excerpt_start, start - 96)
    raw_budget = max_chars - 2
    clip_end = min(excerpt_end, clip_start + raw_budget)
    if clip_end < end:
        clip_end = min(excerpt_end, end + 96)
        clip_start = max(excerpt_start, clip_end - raw_budget)
    prefix = "…" if clip_start > excerpt_start else ""
    suffix = "…" if clip_end < excerpt_end else ""
    available = max_chars - len(prefix) - len(suffix)
    clipped = clean_text(text[clip_start:clip_end])[:available].rstrip()
    return f"{prefix}{clipped}{suffix}"


def _season_label(value: str, year: int) -> str:
    season = value.casefold()
    if season == "autumn":
        season = "fall"
    return f"{season.title()} {year}"


def _date_references(text: str) -> list[dict[str, Any]]:
    references: list[dict[str, Any]] = []
    shared_spans: list[tuple[int, int]] = []
    for pattern in (_THREE_SHARED_SEASONS, _TWO_SHARED_SEASONS):
        for match in pattern.finditer(text):
            if any(match.start() < end and match.end() > start for start, end in shared_spans):
                continue
            shared_spans.append((match.start(), match.end()))
            year = int(match.group("year"))
            group = f"shared:{match.start()}:{match.end()}"
            for name in ("first", "second", "third"):
                season = match.groupdict().get(name)
                if season is None:
                    continue
                references.append(
                    {
                        "value": None,
                        "year": year,
                        "label": _season_label(season, year),
                        "start": match.start(name),
                        "end": match.end(name),
                        "group": group,
                    }
                )
    for match in _DATE_REFERENCE.finditer(text):
        if any(match.start() < end and match.end() > start for start, end in shared_spans):
            continue
        if match.group("month"):
            month, abbreviation = _MONTHS[match.group("month").casefold()]
            year = int(match.group("month_year"))
            references.append(
                {
                    "value": f"{year:04d}-{month:02d}",
                    "year": year,
                    "label": f"{abbreviation} {year}",
                    "start": match.start(),
                    "end": match.end(),
                }
            )
        elif match.group("season"):
            year = int(match.group("season_year"))
            references.append(
                {
                    "value": None,
                    "year": year,
                    "label": _season_label(match.group("season"), year),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
        else:
            year = int(match.group("year"))
            references.append(
                {
                    "value": str(year),
                    "year": year,
                    "label": str(year),
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    return sorted(references, key=lambda item: int(item["start"]))


def _range_summary(first: dict[str, Any], last: dict[str, Any]) -> str:
    if first["label"] == last["label"]:
        return str(first["label"])
    if first["year"] == last["year"]:
        suffix = f" {first['year']}"
        first_label = str(first["label"])
        if first_label.endswith(suffix):
            return f"{first_label[: -len(suffix)]}–{last['label']}"
    return f"{first['label']}–{last['label']}"


def _is_negated_required(text: str, start: int) -> bool:
    prefix = text[max(0, start - 20) : start]
    return bool(re.search(r"\b(?:not|isn't|is\s+not|aren't|are\s+not)\s*$", prefix, re.IGNORECASE))


def _closest_signal(
    text: str,
    start: int,
    end: int,
    pattern: re.Pattern[str],
    *,
    reject_negated_required: bool = False,
) -> int | None:
    closest: int | None = None
    for match in pattern.finditer(text):
        if reject_negated_required and _is_negated_required(text, match.start()):
            continue
        distance = min(abs(match.start() - end), abs(match.end() - start))
        closest = distance if closest is None else min(closest, distance)
    return closest


def _requirement_level(text: str, start: int, end: int) -> str:
    """Classify explicit modality without turning a preference into a gate."""
    sentence_start = max(text.rfind(mark, 0, start) for mark in (".", ";", "!", "?")) + 1
    sentence_ends = [
        position for mark in (".", ";", "!", "?") if (position := text.find(mark, end)) >= 0
    ]
    sentence_end = min(sentence_ends) if sentence_ends else min(len(text), end + 180)
    sentence = text[sentence_start:sentence_end]
    local_start = start - sentence_start
    local_end = end - sentence_start

    preferred_distance = _closest_signal(
        sentence,
        local_start,
        local_end,
        _PREFERRED_INLINE,
    )
    required_distance = _closest_signal(
        sentence,
        local_start,
        local_end,
        _REQUIRED_INLINE,
        reject_negated_required=True,
    )
    # An inline modifier must be close to the condition. This prevents phrases such as
    # "graduating in 2027 with a degree, ideally in Finance" from marking the graduation date
    # preferred, or "pursuing a degree (PhD preferred)" from modifying enrollment.
    if preferred_distance is not None and preferred_distance > 48:
        preferred_distance = None
    if required_distance is not None and required_distance > 48:
        required_distance = None
    if preferred_distance is not None or required_distance is not None:
        if preferred_distance is not None and (
            required_distance is None or preferred_distance <= required_distance
        ):
            return "preferred"
        return "required"

    # Qualification headings often occupy their own sentence after HTML list cleanup. Only the
    # nearest preceding heading applies; ordinary wording in an earlier bullet does not leak.
    heading_context = text[max(0, sentence_start - 320) : sentence_start]
    headings: list[tuple[int, str]] = []
    headings.extend(
        (match.start(), "preferred") for match in _PREFERRED_HEADING.finditer(heading_context)
    )
    headings.extend(
        (match.start(), "required") for match in _REQUIRED_HEADING.finditer(heading_context)
    )
    if headings:
        return max(headings, key=lambda item: item[0])[1]
    return "stated"


def _graduation_requirement(text: str) -> dict[str, Any] | None:
    for trigger in _GRADUATION_TRIGGER.finditer(text):
        excerpt = _context(text, trigger.start(), trigger.end())
        references = _date_references(excerpt)
        if not references:
            continue
        local_trigger = _GRADUATION_TRIGGER.search(excerpt)
        if local_trigger is None:
            continue
        references = [
            item
            for item in references
            if min(
                abs(int(item["start"]) - local_trigger.end()),
                abs(int(item["end"]) - local_trigger.start()),
            )
            <= 180
        ]
        if not references:
            continue
        nearby = min(
            references,
            key=lambda item: min(
                abs(int(item["start"]) - local_trigger.start()),
                abs(int(item["end"]) - local_trigger.end()),
            ),
        )
        result: dict[str, Any] = {
            "status": "explicit-date",
            "requirement_level": _requirement_level(
                text,
                trigger.start(),
                trigger.end(),
            ),
            "evidence": excerpt,
            "graduation_evidence": excerpt,
        }
        range_references = [
            item for item in references if int(item["start"]) >= local_trigger.end()
        ]
        first = range_references[0] if range_references else None
        if first is not None and first.get("group"):
            grouped = [item for item in range_references if item.get("group") == first["group"]]
            second = grouped[-1] if len(grouped) >= 2 else None
        else:
            second = range_references[1] if len(range_references) >= 2 else None
        range_prefix = excerpt[local_trigger.end() : int(first["start"])] if first else ""
        range_connector = (
            excerpt[int(first["end"]) : int(second["start"])] if first and second else ""
        )
        if (
            first is not None
            and second is not None
            and (
                re.search(r"\b(?:between|from)\b", range_prefix, re.IGNORECASE)
                or _RANGE_CONNECTOR.search(range_connector)
            )
        ):
            result["status"] = "explicit-window"
            result["summary"] = _range_summary(first, second)
            result["graduation_years"] = sorted({int(first["year"]), int(second["year"])})
            if first["value"]:
                result["graduation_start"] = first["value"]
            if second["value"]:
                result["graduation_end"] = second["value"]
            return result
        if _LOWER_BOUND.search(excerpt):
            result["status"] = "explicit-lower-bound"
            result["summary"] = f"{nearby['label']} or later"
            result["graduation_years"] = [int(nearby["year"])]
            if nearby["value"]:
                result["graduation_start"] = nearby["value"]
            return result
        if _UPPER_BOUND.search(excerpt):
            result["status"] = "explicit-upper-bound"
            result["summary"] = f"By {nearby['label']}"
            result["graduation_years"] = [int(nearby["year"])]
            if nearby["value"]:
                result["graduation_end"] = nearby["value"]
            return result
        result["summary"] = f"Expected {nearby['label']} graduation"
        result["graduation_years"] = [int(nearby["year"])]
        if nearby["value"]:
            result["graduation_start"] = nearby["value"]
            result["graduation_end"] = nearby["value"]
        return result
    return None


def extract_academic_eligibility(text: str) -> dict[str, Any] | None:
    """Extract only explicit academic timing/status language from one posting description."""
    normalized = clean_text(text)[:50_000]
    if not normalized:
        return None
    graduation = _graduation_requirement(normalized)
    enrollment = _CURRENTLY_ENROLLED.search(normalized)
    return_to_school = _RETURN_TO_SCHOOL.search(normalized)
    if graduation is None and enrollment is None and return_to_school is None:
        return None
    status_match = enrollment or return_to_school
    if status_match is None:
        return graduation
    result = graduation or {
        "status": "student-status",
        "summary": (
            "Student status conditions"
            if enrollment is not None and return_to_school is not None
            else "Current student status"
        ),
        "evidence": _context(normalized, status_match.start(), status_match.end()),
    }
    result["currently_enrolled"] = enrollment is not None
    result["return_to_school"] = return_to_school is not None
    if enrollment is not None:
        result["currently_enrolled_evidence"] = _context(
            normalized,
            enrollment.start(),
            enrollment.end(),
        )
        result["currently_enrolled_level"] = _requirement_level(
            normalized,
            enrollment.start(),
            enrollment.end(),
        )
    if return_to_school is not None:
        result["return_to_school_evidence"] = _context(
            normalized,
            return_to_school.start(),
            return_to_school.end(),
        )
        result["return_to_school_level"] = _requirement_level(
            normalized,
            return_to_school.start(),
            return_to_school.end(),
        )
    if graduation is None and return_to_school is not None and enrollment is None:
        result["summary"] = "Return-to-school condition"
    return result


def classify_academic_eligibility(observations: list[Observation]) -> dict[str, Any]:
    """Choose the highest-provenance explicit requirement and retain its source."""
    descriptions = [observation for observation in observations if observation.description]
    matches: list[dict[str, Any]] = []
    for observation in descriptions:
        extracted = extract_academic_eligibility(observation.description)
        if extracted is None:
            continue
        extracted.update(
            {
                "extractor_version": ACADEMIC_EXTRACTOR_VERSION,
                "source_id": observation.source_id,
                "source_label": observation.source_label,
                "confidence": (
                    "direct-ats" if observation.source_id.startswith("ats:") else "source-text"
                ),
            }
        )
        matches.append(extracted)
    if matches:
        direct = [item for item in matches if item["confidence"] == "direct-ats"]
        return (direct or matches)[0]
    if descriptions:
        preferred = descriptions[0]
        return {
            "extractor_version": ACADEMIC_EXTRACTOR_VERSION,
            "status": "not-found",
            "summary": "No academic timing requirement detected",
            "source_id": preferred.source_id,
            "source_label": preferred.source_label,
            "confidence": (
                "direct-ats" if preferred.source_id.startswith("ats:") else "source-text"
            ),
        }
    return {
        "extractor_version": ACADEMIC_EXTRACTOR_VERSION,
        "status": "unavailable",
        "summary": "Posting text unavailable",
        "confidence": "metadata-only",
    }
