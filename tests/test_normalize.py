from __future__ import annotations

import unittest

from scripts.models import Observation
from scripts.normalize import (
    canonical_url,
    external_identity,
    infer_cycle,
    is_recruiting_platform_url,
    is_technical,
    is_us_role,
    job_id,
    sanitize_job_url,
)


class NormalizeTests(unittest.TestCase):
    def test_us_filter_accepts_states_and_rejects_foreign_only_locations(self) -> None:
        self.assertTrue(is_us_role("Austin, TX", trusted_us=False))
        self.assertTrue(is_us_role("Remote in USA", trusted_us=False))
        self.assertFalse(is_us_role("Toronto, Canada", trusted_us=False))
        self.assertFalse(is_us_role("Remote in Canada", trusted_us=True))
        self.assertFalse(is_us_role("Toronto, ON", trusted_us=True))
        self.assertFalse(is_us_role("Remote", trusted_us=False))
        self.assertTrue(is_us_role("Remote", trusted_us=True))
        self.assertTrue(is_us_role("London, UK, Chicago, IL", trusted_us=False))

    def test_foreign_job_url_can_disambiguate_bad_location_metadata(self) -> None:
        self.assertFalse(
            is_us_role(
                "Vancouver, BC, Toronto, ON, Winnipeg, MN",
                trusted_us=False,
                context="https://example.com/software-engineer-canada",
            )
        )

    def test_cycle_detection_prefers_explicit_cycle_over_source_hint(self) -> None:
        self.assertEqual(
            infer_cycle(
                title="Software Engineering Intern - Fall 2026",
                description="",
                program="internship",
                hint="summer-2027",
            ),
            "fall-2026",
        )
        self.assertEqual(
            infer_cycle(
                title="Software Engineering Internship",
                description="",
                program="internship",
                hint="summer-2027",
            ),
            "summer-2027",
        )

    def test_greenhouse_custom_and_board_urls_share_identity(self) -> None:
        custom = "https://company.com/careers/job?gh_jid=12345"
        board = "https://job-boards.greenhouse.io/example/jobs/12345"
        self.assertEqual(external_identity(custom, "one"), external_identity(board, "two"))
        custom_observation = Observation(
            source_id="source",
            source_label="Source",
            source_url="https://example.com",
            external_id="one",
            company="Example",
            title="Software Engineer Intern",
            location="Austin, TX",
            program="internship",
            url=custom,
        )
        board_observation = Observation(
            source_id="source",
            source_label="Source",
            source_url="https://example.com",
            external_id="one",
            company="Example",
            title="Software Engineer Intern",
            location="Austin, TX",
            program="internship",
            url=board,
        )
        self.assertEqual(
            job_id(custom_observation),
            job_id(board_observation),
        )

    def test_technical_filter_excludes_unrelated_internship(self) -> None:
        self.assertTrue(is_technical("Software Engineer Intern"))
        self.assertFalse(is_technical("Human Resources Intern"))

    def test_url_cleaner_keeps_only_bounded_job_identity_parameters(self) -> None:
        value = (
            "http://Jobs.Example.com/openings/123?utm_source=email&gh_jid=42&gh_jid=43"
            "&redirect=https://evil.example#apply"
        )
        self.assertEqual(
            canonical_url(value),
            "https://jobs.example.com/openings/123?gh_jid=42",
        )

    def test_url_cleaner_encodes_markdown_metacharacters(self) -> None:
        cleaned = canonical_url("https://jobs.example.com/[click](elsewhere)/123")
        self.assertEqual(
            cleaned,
            "https://jobs.example.com/%5Bclick%5D%28elsewhere%29/123",
        )

    def test_url_cleaner_rejects_hostile_or_ambiguous_destinations(self) -> None:
        rejected = {
            "credentials": "https://user:password@jobs.example.com/123",
            "private-ip": "https://127.0.0.1/admin",
            "local-name": "https://metadata.internal/latest",
            "shortener": "https://bit.ly/example",
            "generic-form": "https://forms.gle/example",
            "port": "https://jobs.example.com:8443/123",
            "encoded-slash": "https://jobs.example.com/company%2Fadmin",
            "double-encoding": "https://jobs.example.com/company%252Fadmin",
            "dot-segment": "https://jobs.example.com/company/%2e%2e/admin",
            "download": "https://jobs.example.com/application.exe",
            "reserved-domain": "https://jobs.example.test/123",
            "backslash": "https://jobs.example.com\\@evil.example/123",
        }
        for label, value in rejected.items():
            with self.subTest(label=label):
                decision = sanitize_job_url(value)
                self.assertEqual(decision.url, "")
                self.assertIsNotNone(decision.reason)

    def test_recruiting_platform_requires_a_structured_job_path(self) -> None:
        self.assertTrue(
            is_recruiting_platform_url("https://job-boards.greenhouse.io/example/jobs/1234567890")
        )
        self.assertFalse(is_recruiting_platform_url("https://job-boards.greenhouse.io/example"))
        self.assertFalse(is_recruiting_platform_url("https://careers.example.com/jobs/123"))


if __name__ == "__main__":
    unittest.main()
