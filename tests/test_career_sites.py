from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.career_sites import scan_company_sites
from scripts.models import Observation


def discovery(title: str = "Software Engineer Intern") -> Observation:
    return Observation(
        source_id="jobright-swe-internships",
        source_label="Jobright",
        source_url="https://github.com/jobright-ai/feed",
        external_id="jr-123",
        company="Example, Inc.",
        title=title,
        location="Austin, TX, United States",
        url="https://jobright.ai/jobs/info/jr-123",
        program="internship",
        posted_at="2026-08-15",
        metadata={"company_url": "http://example.com"},
    )


class CareerSiteDiscoveryTests(unittest.TestCase):
    def test_company_site_finds_board_and_exact_direct_job_link(self) -> None:
        home = (
            '<a href="/careers">Careers</a>'
            '<a href="https://jobs.ashbyhq.com/example">Open roles</a>'
        )
        careers = '<a href="https://jobs.ashbyhq.com/example/role-123">Software Engineer Intern</a>'

        def fetch(url: str) -> tuple[str, str]:
            return (url, careers if url.endswith("/careers") else home)

        with patch("scripts.career_sites.get_public_html", side_effect=fetch):
            snapshots, boards, payload, errors = scan_company_sites(
                [discovery()],
                {"sites": []},
                today="2026-08-15",
                limit=1,
                max_workers=1,
            )

        self.assertEqual(errors, {})
        self.assertEqual(boards[0]["key"], "ashby:example")
        self.assertEqual(
            snapshots[0].observations[0].url,
            "https://jobs.ashbyhq.com/example/role-123",
        )
        self.assertEqual(payload["sites"][0]["resolved_roles"], 1)

    def test_ambiguous_identical_titles_do_not_guess_a_direct_link(self) -> None:
        document = (
            '<a href="https://jobs.example.com/a">Software Engineer Intern</a>'
            '<a href="https://jobs.example.com/b">Software Engineer Intern</a>'
        )
        with patch(
            "scripts.career_sites.get_public_html",
            return_value=("https://example.com/", document),
        ):
            snapshots, _, _, _ = scan_company_sites(
                [discovery()],
                {"sites": []},
                today="2026-08-15",
                limit=1,
                max_workers=1,
            )

        self.assertEqual(snapshots[0].observations, ())


if __name__ == "__main__":
    unittest.main()
