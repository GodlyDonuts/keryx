from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .models import Observation

_LEGAL_SUFFIXES = frozenset(
    {
        "co",
        "company",
        "corp",
        "corporation",
        "inc",
        "incorporated",
        "llc",
        "ltd",
    }
)


def is_jobright_source(source_id: object) -> bool:
    return str(source_id or "").startswith("jobright-")


def is_jobright_observation(observation: Observation) -> bool:
    return is_jobright_source(observation.source_id)


def company_key(value: object) -> str:
    tokens = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split()
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def split_jobright_discoveries(
    observations: Iterable[Observation],
) -> tuple[list[Observation], list[Observation]]:
    publishable: list[Observation] = []
    discoveries: list[Observation] = []
    for observation in observations:
        target = discoveries if is_jobright_observation(observation) else publishable
        target.append(observation)
    return publishable, discoveries


def prioritized_board_keys(
    discoveries: Iterable[Observation],
    boards: Iterable[Mapping[str, object]],
    *,
    limit: int = 32,
) -> set[str]:
    """Choose known employer boards worth polling immediately.

    A matching board is queried through its public ATS API so Keryx can replace a Jobright fallback
    with a direct employer destination as quickly as possible.
    """

    newest_by_company: dict[str, str] = {}
    for discovery in discoveries:
        key = company_key(discovery.company)
        if not key:
            continue
        newest_by_company[key] = max(
            newest_by_company.get(key, ""),
            discovery.posted_at or "",
        )

    candidates: list[tuple[str, str]] = []
    for board in boards:
        key = company_key(board.get("company"))
        board_key = str(board.get("key") or "")
        if key in newest_by_company and board_key:
            candidates.append((newest_by_company[key], board_key))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return {board_key for _, board_key in candidates[:limit]}
