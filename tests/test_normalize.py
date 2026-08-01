from __future__ import annotations

import unittest

from scripts.models import Observation
from scripts.normalize import (
    external_identity,
    infer_cycle,
    is_technical,
    is_us_role,
    job_id,
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
        custom = "https://company.example/careers/job?gh_jid=12345"
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


if __name__ == "__main__":
    unittest.main()
