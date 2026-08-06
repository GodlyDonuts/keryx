from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from .models import Observation
from .normalize import clean_text

INTELLIGENCE_EXTRACTOR_VERSION = 1
MAX_SKILLS = 10

_SKILL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, re.compile(rf"(?<![\w+#])(?:{pattern})(?![\w+])", flags))
    for name, pattern, flags in (
        ("Python", r"python", re.IGNORECASE),
        ("Java", r"java(?!\s*script)", re.IGNORECASE),
        ("C++", r"c\+\+", re.IGNORECASE),
        ("C#", r"c#|c[- ]sharp", re.IGNORECASE),
        ("Go", r"golang|go\s+programming", re.IGNORECASE),
        ("Rust", r"Rust", 0),
        ("TypeScript", r"typescript", re.IGNORECASE),
        ("JavaScript", r"javascript|ecmascript", re.IGNORECASE),
        ("SQL", r"sql", re.IGNORECASE),
        ("Swift", r"Swift(?:UI)?", 0),
        ("Kotlin", r"kotlin", re.IGNORECASE),
        ("Scala", r"scala", re.IGNORECASE),
        ("Ruby", r"ruby", re.IGNORECASE),
        ("Bash", r"bash|shell\s+scripting", re.IGNORECASE),
        ("MATLAB", r"matlab", re.IGNORECASE),
        ("PyTorch", r"pytorch|torch", re.IGNORECASE),
        ("TensorFlow", r"tensorflow", re.IGNORECASE),
        ("JAX", r"jax", re.IGNORECASE),
        ("scikit-learn", r"scikit[\s-]?learn|sklearn", re.IGNORECASE),
        ("Pandas", r"pandas", re.IGNORECASE),
        ("NumPy", r"numpy", re.IGNORECASE),
        ("LLMs", r"llms?|large\s+language\s+models?|generative\s+ai", re.IGNORECASE),
        ("Computer Vision", r"computer\s+vision|opencv", re.IGNORECASE),
        ("CUDA", r"cuda", re.IGNORECASE),
        ("React", r"React(?:\.?[jJ]s)?(?:\s+Native)?", 0),
        ("Next.js", r"next\.?js", re.IGNORECASE),
        ("Node.js", r"node\.?js", re.IGNORECASE),
        ("Angular", r"Angular(?:JS)?", 0),
        ("Vue", r"vue\.?js|Vue", 0),
        ("Django", r"django", re.IGNORECASE),
        ("Flask", r"flask", re.IGNORECASE),
        ("FastAPI", r"fastapi", re.IGNORECASE),
        ("Spring", r"spring\s+boot", re.IGNORECASE),
        (".NET", r"dotnet|asp\.net|\.net\s*(?:core|framework|\d)", re.IGNORECASE),
        ("GraphQL", r"graphql", re.IGNORECASE),
        ("AWS", r"aws|amazon\s+web\s+services", re.IGNORECASE),
        ("GCP", r"gcp|google\s+cloud", re.IGNORECASE),
        ("Azure", r"azure", re.IGNORECASE),
        ("Kubernetes", r"kubernetes|k8s", re.IGNORECASE),
        ("Docker", r"docker", re.IGNORECASE),
        ("Terraform", r"terraform", re.IGNORECASE),
        ("Linux", r"linux|unix", re.IGNORECASE),
        ("Git", r"git|github|gitlab", re.IGNORECASE),
        ("Spark", r"apache\s+spark|pyspark|spark\s*(?:sql|streaming)", re.IGNORECASE),
        ("Kafka", r"kafka", re.IGNORECASE),
        ("Airflow", r"airflow", re.IGNORECASE),
        ("Databricks", r"databricks", re.IGNORECASE),
        ("Snowflake", r"snowflake", re.IGNORECASE),
        ("PostgreSQL", r"postgres(?:ql)?", re.IGNORECASE),
        ("MongoDB", r"mongodb|mongo", re.IGNORECASE),
        ("Redis", r"redis", re.IGNORECASE),
        ("ROS", r"ros\s*2|robot\s+operating\s+system", re.IGNORECASE),
        ("Verilog", r"(?:system)?verilog|vhdl", re.IGNORECASE),
    )
)
_SKILL_RANK = {name: index for index, (name, _) in enumerate(_SKILL_PATTERNS)}

_CATEGORY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "quant",
        re.compile(
            r"\b(?:quant(?:itative)?|trading|trader|alpha|systematic|market\s+making)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "security",
        re.compile(
            r"\b(?:cyber|security|infosec|vulnerability|penetration|threat|soc\s+analyst)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "data-ml",
        re.compile(
            r"\b(?:machine\s+learning|artificial\s+intelligence|data\s+(?:science|scientist|"
            r"engineering|engineer)|analytics|computer\s+vision|nlp|research\s+scientist)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "hardware",
        re.compile(
            r"\b(?:hardware|firmware|embedded|electrical|silicon|fpga|asic|semiconductor|"
            r"robotics|controls?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "product-design",
        re.compile(
            r"\b(?:product\s+(?:manager|management|designer)|ux|ui\s+designer|user\s+experience)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "software",
        re.compile(
            r"\b(?:software|developer|development|frontend|backend|full[ -]?stack|web|mobile|"
            r"platform|devops|site\s+reliability|infrastructure|cloud)\b",
            re.IGNORECASE,
        ),
    ),
)

_CITIZENSHIP = re.compile(
    r"(?:must\s+be\s+(?:a\s+)?(?:u\.?s\.?|united\s+states)\s+citizen|"
    r"(?:u\.?s\.?|united\s+states)\s+citizenship\s+(?:is\s+)?(?:required|mandatory)|"
    r"(?:security|government|top\s+secret|ts/?sci|secret)\s+clearance\s+(?:is\s+)?required|"
    r"\bitar\b|export\s+control.{0,80}(?:u\.?s\.?)\s+person)",
    re.IGNORECASE,
)
_NO_SPONSORSHIP = re.compile(
    r"(?:will\s+not|won'?t|cannot|can\s+not|unable\s+to|does\s+not|do\s+not)\s+"
    r"(?:provide\s+|offer\s+)?(?:visa\s+|immigration\s+|work\s+visa\s+)?sponsor(?:ship)?|"
    r"(?:visa\s+|immigration\s+|work\s+visa\s+)?sponsorship\s+(?:is\s+)?"
    r"(?:not\s+available|not\s+offered|not\s+provided|unavailable)|"
    r"no\s+(?:visa\s+|immigration\s+|h-?1b\s+)?sponsorship|"
    r"without\s+(?:the\s+need\s+for\s+)?(?:visa\s+)?sponsorship",
    re.IGNORECASE,
)
_OFFERS_SPONSORSHIP = re.compile(
    r"(?:visa\s+|immigration\s+|h-?1b\s+)?sponsorship\s+(?:is\s+)?"
    r"(?:available|offered|provided)|"
    r"(?:we\s+)?(?:will|can|do|are\s+able\s+to)\s+(?:provide\s+)?sponsor(?:ship)?|"
    r"open\s+to\s+sponsor(?:ship)?",
    re.IGNORECASE,
)

_REMOTE = re.compile(
    r"\b(?:fully\s+remote|remote(?:[- ]first)?(?!\s+(?:access|control|desktop|sensing|support))|"
    r"work\s+from\s+home|anywhere\s+in\s+the\s+u\.?s\.?)\b",
    re.IGNORECASE,
)
_HYBRID = re.compile(r"\bhybrid\b", re.IGNORECASE)
_ONSITE = re.compile(r"\b(?:on[- ]?site|in[- ]office)\b", re.IGNORECASE)

_HOURLY_PAY = re.compile(
    r"\$\s*(?P<minimum>\d{2,3}(?:\.\d{1,2})?)"
    r"(?:\s*(?:-|–|—|to|and)\s*\$?\s*(?P<maximum>\d{2,3}(?:\.\d{1,2})?))?"
    r"\s*(?:/\s*|per\s+)(?:hour|hr)\b",
    re.IGNORECASE,
)
_ANNUAL_PAY = re.compile(
    r"\$\s*(?P<minimum>\d{1,3}(?:,\d{3})+|\d{5,6})"
    r"(?:\s*(?:-|–|—|to|and)\s*\$?\s*(?P<maximum>\d{1,3}(?:,\d{3})+|\d{5,6}))?"
    r"[^$\n]{0,32}?(?:/\s*(?:year|yr)|per\s+(?:year|annum)|annual(?:ly|ized)?)",
    re.IGNORECASE,
)

_UPSTREAM_CATEGORIES = {
    "software": "software",
    "data & ml/ai": "data-ml",
    "quant": "quant",
    "security": "security",
    "hardware": "hardware",
    "product": "product-design",
}
_UPSTREAM_VISA = {
    "citizens-only": "citizenship-required",
    "citizenship-required": "citizenship-required",
    "no-sponsorship": "no-sponsorship",
    "does not offer sponsorship": "no-sponsorship",
    "offers": "sponsorship-available",
    "sponsorship-available": "sponsorship-available",
}


def _excerpt(text: str, start: int, end: int, *, maximum: int = 240) -> str:
    left = max(0, start - 100)
    right = min(len(text), end + 120)
    sentence_start = max(
        (text.rfind(mark, left, start) for mark in (".", ";", "!", "?")), default=-1
    )
    sentence_end_candidates = [
        position for mark in (".", ";", "!", "?") if (position := text.find(mark, end, right)) >= 0
    ]
    sentence_end = min(sentence_end_candidates) + 1 if sentence_end_candidates else right
    value = clean_text(text[sentence_start + 1 : sentence_end])
    if len(value) <= maximum:
        return value
    clipped = value[: maximum - 1].rstrip()
    return f"{clipped}…"


def extract_skills(text: str, *, title: str = "") -> list[str]:
    found = [name for name, pattern in _SKILL_PATTERNS if pattern.search(text)]
    title_matches = {name for name, pattern in _SKILL_PATTERNS if pattern.search(title)}
    return sorted(
        dict.fromkeys(found),
        key=lambda value: (value not in title_matches, _SKILL_RANK[value]),
    )[:MAX_SKILLS]


def classify_category(title: str, description: str = "") -> str:
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(title):
            return category
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(description):
            return category
    return "other-tech"


def extract_compensation(text: str) -> dict[str, object] | None:
    flattened = " ".join(text.split())
    for period, pattern, lower, upper in (
        ("hour", _HOURLY_PAY, 10.0, 250.0),
        ("year", _ANNUAL_PAY, 15_000.0, 750_000.0),
    ):
        match = pattern.search(flattened)
        if match is None:
            continue
        minimum = float(match.group("minimum").replace(",", ""))
        maximum_value = match.group("maximum")
        maximum = float(maximum_value.replace(",", "")) if maximum_value else None
        if not lower <= minimum <= upper or maximum is not None and not minimum <= maximum <= upper:
            continue
        if period == "hour":
            low_text = f"${minimum:g}"
            high_text = f"–${maximum:g}" if maximum is not None and maximum != minimum else ""
            summary = f"{low_text}{high_text}/hr"
        else:
            low_text = f"${minimum / 1000:g}k"
            high_text = (
                f"–${maximum / 1000:g}k" if maximum is not None and maximum != minimum else ""
            )
            summary = f"{low_text}{high_text}/yr"
        return {
            "currency": "USD",
            "period": period,
            "minimum": minimum,
            "maximum": maximum,
            "summary": summary,
            "evidence": _excerpt(flattened, match.start(), match.end()),
        }
    return None


def classify_visa(text: str) -> dict[str, str]:
    for status, pattern, summary in (
        ("citizenship-required", _CITIZENSHIP, "Citizenship or clearance restriction stated"),
        ("no-sponsorship", _NO_SPONSORSHIP, "Posting states sponsorship is unavailable"),
        ("sponsorship-available", _OFFERS_SPONSORSHIP, "Posting states sponsorship is available"),
    ):
        match = pattern.search(text)
        if match is not None:
            return {
                "status": status,
                "summary": summary,
                "evidence": _excerpt(text, match.start(), match.end()),
            }
    return {"status": "unknown", "summary": "Posting text has no conclusive visa statement"}


def classify_workplace(title: str, location: str, description: str = "") -> dict[str, str]:
    combined = " ".join((title, location, description))
    for value, pattern, summary in (
        ("remote", _REMOTE, "Remote work stated"),
        ("hybrid", _HYBRID, "Hybrid work stated"),
        ("onsite", _ONSITE, "On-site work stated"),
    ):
        match = pattern.search(combined)
        if match is not None:
            return {
                "value": value,
                "summary": summary,
                "evidence": _excerpt(combined, match.start(), match.end()),
            }
    return {"value": "unspecified", "summary": "Work arrangement not explicitly stated"}


def _metadata_skills(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    known = {name.casefold(): name for name, _ in _SKILL_PATTERNS}
    result: list[str] = []
    for item in value:
        canonical = known.get(str(item).casefold())
        if canonical and canonical not in result:
            result.append(canonical)
    return result[:MAX_SKILLS]


def _first_metadata(
    observations: Iterable[Observation], key: str
) -> tuple[object, Observation] | None:
    for observation in observations:
        if key in observation.metadata and observation.metadata[key] is not None:
            return observation.metadata[key], observation
    return None


def build_job_intelligence(observations: list[Observation], *, checked_at: str) -> dict[str, Any]:
    if not observations:
        raise ValueError("job intelligence requires at least one observation")
    preferred = observations[0]
    text_source = next((item for item in observations if item.description.strip()), None)
    text = (
        " ".join((text_source.title, text_source.description))
        if text_source is not None
        else preferred.title
    )
    source = text_source or preferred
    category = classify_category(preferred.title, text_source.description if text_source else "")
    metadata_category = _first_metadata(observations, "category")
    if category == "other-tech" and metadata_category is not None:
        category = _UPSTREAM_CATEGORIES.get(str(metadata_category[0]).casefold(), category)

    skills = extract_skills(text, title=preferred.title)
    metadata_skills = _first_metadata(observations, "skills")
    if metadata_skills is not None:
        for skill in _metadata_skills(metadata_skills[0]):
            if skill not in skills and len(skills) < MAX_SKILLS:
                skills.append(skill)

    compensation = extract_compensation(text_source.description) if text_source else None
    compensation_source = text_source
    if compensation is None:
        upstream_compensation = _first_metadata(observations, "salary")
        if upstream_compensation is not None:
            compensation = extract_compensation(str(upstream_compensation[0]))
            compensation_source = upstream_compensation[1]
    if compensation is not None and compensation_source is not None:
        compensation.update(
            {
                "source_id": compensation_source.source_id,
                "source_label": compensation_source.source_label,
                "confidence": "source-text"
                if compensation_source.description
                else "source-metadata",
            }
        )

    visa = (
        classify_visa(text_source.description)
        if text_source
        else {
            "status": "unknown",
            "summary": "Complete posting text unavailable",
        }
    )
    visa_source = text_source
    if visa["status"] == "unknown":
        upstream_visa = next(
            (
                (item.sponsorship, item)
                for item in observations
                if item.sponsorship and str(item.sponsorship).casefold() not in {"unknown", "other"}
            ),
            None,
        )
        if upstream_visa is not None:
            status = _UPSTREAM_VISA.get(str(upstream_visa[0]).casefold())
            if status:
                visa = {
                    "status": status,
                    "summary": "Classification supplied by a public source",
                }
                visa_source = upstream_visa[1]
    if visa_source is not None:
        visa.update(
            {
                "source_id": visa_source.source_id,
                "source_label": visa_source.source_label,
                "confidence": "source-text" if visa_source.description else "source-metadata",
            }
        )

    workplace = classify_workplace(
        preferred.title,
        preferred.location,
        text_source.description if text_source else "",
    )
    workplace_source = source
    upstream_remote = _first_metadata(observations, "remote")
    if (
        workplace["value"] == "unspecified"
        and upstream_remote is not None
        and upstream_remote[0] is True
    ):
        workplace = {
            "value": "remote",
            "summary": "Remote classification supplied by a public source",
        }
        workplace_source = upstream_remote[1]
    workplace.update(
        {
            "source_id": workplace_source.source_id,
            "source_label": workplace_source.source_label,
            "confidence": "source-text" if workplace_source.description else "source-metadata",
        }
    )

    h1b_history: dict[str, object] | None = None
    approvals = _first_metadata(observations, "h1b_approvals")
    if approvals is not None and isinstance(approvals[0], int) and approvals[0] >= 0:
        h1b_window = _first_metadata(observations, "h1b_window")
        h1b_history = {
            "approvals": approvals[0],
            "period": str(h1b_window[0]) if h1b_window is not None else "historical",
            "source_id": approvals[1].source_id,
            "source_label": approvals[1].source_label,
            "summary": "Historical employer approvals; not a promise for this role",
        }

    result: dict[str, Any] = {
        "extractor_version": INTELLIGENCE_EXTRACTOR_VERSION,
        "text_status": "checked" if text_source is not None else "metadata-only",
        "category": category,
        "category_source_id": source.source_id,
        "skills": skills,
    }
    if text_source is not None:
        result["checked_at"] = checked_at
    if skills:
        result["skills_source_id"] = source.source_id
    if compensation is not None:
        result["compensation"] = compensation
    if workplace["value"] != "unspecified":
        result["workplace"] = workplace
    if visa["status"] != "unknown":
        result["visa"] = visa
    if h1b_history is not None:
        result["h1b_history"] = h1b_history
    return result


def visa_compatibility_value(intelligence: Mapping[str, object]) -> str | None:
    visa = intelligence.get("visa")
    if not isinstance(visa, Mapping):
        return None
    return {
        "citizenship-required": "citizens-only",
        "no-sponsorship": "no-sponsorship",
        "sponsorship-available": "offers",
    }.get(str(visa.get("status") or ""))
