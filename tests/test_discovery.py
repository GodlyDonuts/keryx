from __future__ import annotations

import unittest

from scripts.discovery import company_key, prioritized_board_keys, split_jobright_discoveries
from scripts.models import Observation


def role(source: str, company: str = "Example, Inc.", posted_at: str | None = None) -> Observation:
    return Observation(
        source_id=source,
        source_label=source,
        source_url="https://example.com/source",
        external_id="123",
        company=company,
        title="Software Engineer Intern",
        location="Austin, TX",
        url=(
            "https://jobright.ai/jobs/info/123"
            if source.startswith("jobright-")
            else "https://jobs.example.com/123"
        ),
        program="internship",
        posted_at=posted_at,
    )


class JobrightDiscoveryTests(unittest.TestCase):
    def test_split_separates_jobright_signals_from_other_upstreams(self) -> None:
        direct = role("simplify-internships")
        discovery = role("jobright-swe-internships")

        non_jobright, discoveries = split_jobright_discoveries([discovery, direct])

        self.assertEqual(non_jobright, [direct])
        self.assertEqual(discoveries, [discovery])

    def test_company_key_normalizes_legal_suffixes_without_fuzzy_aliasing(self) -> None:
        self.assertEqual(company_key("Example Corporation"), "example")
        self.assertEqual(company_key("Example Labs"), "example labs")

    def test_recent_discoveries_prioritize_matching_known_boards_with_a_cap(self) -> None:
        discoveries = [
            role("jobright-swe-internships", "Older LLC", "2026-08-13"),
            role("jobright-swe-internships", "Newest Corp.", "2026-08-14"),
        ]
        boards = [
            {"key": "greenhouse:older", "company": "Older"},
            {"key": "ashby:newest", "company": "Newest, Inc."},
            {"key": "lever:unrelated", "company": "Unrelated"},
        ]

        self.assertEqual(
            prioritized_board_keys(discoveries, boards, limit=1),
            {"ashby:newest"},
        )


if __name__ == "__main__":
    unittest.main()
