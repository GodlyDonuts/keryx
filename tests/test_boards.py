from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.boards import board_from_observation, board_from_url, discover_boards, fetch_board
from scripts.models import Observation


def role(url: str, external_id: str = "source:job") -> Observation:
    return Observation(
        source_id="source",
        source_label="Source",
        source_url="https://example.com",
        external_id=external_id,
        company="Example",
        title="Software Engineer Intern",
        location="Austin, TX",
        url=url,
        program="internship",
    )


class BoardDiscoveryTests(unittest.TestCase):
    def test_greenhouse(self) -> None:
        board = board_from_observation(
            role("https://job-boards.greenhouse.io/example/jobs/123", "greenhouse:example:123")
        )
        self.assertEqual(board["key"], "greenhouse:example")  # type: ignore[index]

    def test_lever(self) -> None:
        board = board_from_observation(role("https://jobs.lever.co/example/uuid"))
        self.assertEqual(board["slug"], "example")  # type: ignore[index]

    def test_ashby(self) -> None:
        board = board_from_observation(role("https://jobs.ashbyhq.com/example/uuid"))
        self.assertEqual(board["ats"], "ashby")  # type: ignore[index]

    def test_workday(self) -> None:
        board = board_from_observation(
            role("https://example.wd5.myworkdayjobs.com/en-US/careers/job/Austin/Intern_REQ1")
        )
        self.assertEqual(board["slug"], "example")  # type: ignore[index]
        self.assertEqual(board["site"], "careers")  # type: ignore[index]
        self.assertEqual(board["wd"], "wd5")  # type: ignore[index]

    def test_workday_landing_page_can_seed_board(self) -> None:
        board = board_from_url(
            "https://example.wd5.myworkdayjobs.com/en-US/University_Careers",
            "Example",
        )
        self.assertEqual(board["site"], "University_Careers")  # type: ignore[index]

    def test_workday_navigation_links_do_not_seed_fake_boards(self) -> None:
        self.assertIsNone(
            board_from_url("https://example.wd5.myworkdayjobs.com/en-US/login", "Example")
        )
        self.assertIsNone(board_from_url("https://boards.greenhouse.io/embed", "Example"))

    def test_smartrecruiters_landing_page_can_seed_board(self) -> None:
        board = board_from_url("https://jobs.smartrecruiters.com/Example", "Example")
        self.assertEqual(board["key"], "smartrecruiters:example")  # type: ignore[index]

    def test_workable_landing_page_can_seed_board(self) -> None:
        board = board_from_url("https://apply.workable.com/example/", "Example")
        self.assertEqual(board["key"], "workable:example")  # type: ignore[index]

    def test_bamboohr_job_page_can_seed_board(self) -> None:
        board = board_from_url("https://example.bamboohr.com/careers/123/", "Example")
        self.assertEqual(board["key"], "bamboohr:example")  # type: ignore[index]

    def test_oracle_cloud_job_page_can_seed_board(self) -> None:
        board = board_from_url(
            "https://example.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/"
            "en/sites/External/job/123",
            "Example",
        )
        self.assertEqual(
            board["key"],  # type: ignore[index]
            "oracle:example.fa.us2.oraclecloud.com:external",
        )

    def test_workday_site_case_does_not_create_duplicate_boards(self) -> None:
        observations = [
            role("https://example.wd5.myworkdayjobs.com/Careers/job/Austin/Intern_REQ1"),
            role("https://example.wd5.myworkdayjobs.com/careers/job/Boston/Intern_REQ2"),
        ]
        boards = discover_boards(observations, [])
        self.assertEqual(len(boards), 1)
        self.assertEqual(boards[0]["key"], "workday:example.wd5.myworkdayjobs.com:example:careers")

    def test_invalid_existing_board_is_pruned_instead_of_retried(self) -> None:
        invalid = {
            "key": "workday:bad_host.wd5.myworkdayjobs.com:bad_host:careers",
            "ats": "workday",
            "company": "Invalid",
            "slug": "bad_host",
            "site": "careers",
            "host": "bad_host.wd5.myworkdayjobs.com",
        }

        self.assertEqual(discover_boards([], [invalid]), [])  # type: ignore[list-item]

    def test_invalid_observation_url_cannot_seed_board_registry(self) -> None:
        observation = role(
            url="https://bad_host.wd5.myworkdayjobs.com/en-US/Careers/job/Example/123"
        )

        self.assertIsNone(board_from_observation(observation))

    def test_greenhouse_requests_and_retains_public_posting_content(self) -> None:
        board = {
            "key": "greenhouse:example",
            "ats": "greenhouse",
            "company": "Example",
            "slug": "example",
        }
        payload = {
            "jobs": [
                {
                    "id": 123,
                    "title": "Software Engineer Intern",
                    "location": {"name": "Austin, TX"},
                    "absolute_url": "https://job-boards.greenhouse.io/example/jobs/123",
                    "content": "<p>Expected graduation between December 2026 and June 2027.</p>",
                }
            ]
        }

        with patch("scripts.boards.get_json", return_value=payload) as get_json:
            snapshot = fetch_board(board)  # type: ignore[arg-type]

        self.assertTrue(get_json.call_args.args[0].endswith("/jobs?content=true"))
        self.assertIn("Expected graduation", snapshot.observations[0].description)

    def test_lever_includes_requirement_lists_in_description_text(self) -> None:
        board = {
            "key": "lever:example",
            "ats": "lever",
            "company": "Example",
            "slug": "example",
        }
        payload = [
            {
                "id": "abc",
                "text": "Software Engineer Intern",
                "categories": {"location": "Austin, TX"},
                "hostedUrl": "https://jobs.lever.co/example/abc",
                "descriptionPlain": "Build reliable systems.",
                "lists": [
                    {
                        "text": "Requirements",
                        "content": "<li>Must return to school after the internship.</li>",
                    }
                ],
            }
        ]

        with patch("scripts.boards.get_json", return_value=payload):
            snapshot = fetch_board(board)  # type: ignore[arg-type]

        self.assertIn("return to school", snapshot.observations[0].description)

    def test_smartrecruiters_fetches_public_postings(self) -> None:
        board = {
            "key": "smartrecruiters:example",
            "ats": "smartrecruiters",
            "company": "Example",
            "slug": "Example",
        }
        payload = {
            "totalFound": 1,
            "content": [
                {
                    "id": "abc",
                    "name": "Software Engineer Intern",
                    "location": {"city": "Austin", "region": "TX", "country": "US"},
                    "ref": "https://jobs.smartrecruiters.com/Example/abc",
                    "releasedDate": "2026-08-15T00:00:00Z",
                }
            ],
        }

        with patch("scripts.boards.get_json", return_value=payload):
            snapshot = fetch_board(board)  # type: ignore[arg-type]

        self.assertEqual(snapshot.observations[0].title, "Software Engineer Intern")
        self.assertEqual(snapshot.observations[0].location, "Austin, TX, US")
        self.assertEqual(
            snapshot.observations[0].url,
            "https://jobs.smartrecruiters.com/Example/abc",
        )

    def test_workable_fetches_public_markdown_and_emits_application_page(self) -> None:
        board = {
            "key": "workable:example",
            "ats": "workable",
            "company": "Example",
            "slug": "example",
        }
        index = (
            "| Title | Department | Location | Type | Salary | Posted | Details |\n"
            "|---|---|---|---|---|---|---|\n"
            "| Software Engineer Intern | Engineering | Austin, United States | Internship | — | "
            "2026-08-15 | [View](https://apply.workable.com/example/jobs/view/ABC123.md) |\n"
        )

        with patch("scripts.boards.get_text", return_value=index):
            snapshot = fetch_board(board)  # type: ignore[arg-type]

        self.assertEqual(len(snapshot.observations), 1)
        self.assertEqual(
            snapshot.observations[0].url,
            "https://apply.workable.com/example/j/ABC123/",
        )
        self.assertEqual(snapshot.observations[0].description, "")

    def test_bamboohr_fetches_public_board_and_job_description(self) -> None:
        board = {
            "key": "bamboohr:example",
            "ats": "bamboohr",
            "company": "Example",
            "slug": "example",
            "host": "example.bamboohr.com",
        }
        payload = {
            "result": [
                {
                    "id": "123",
                    "jobOpeningName": "Software Engineer Intern",
                    "location": {"city": "Austin", "state": "Texas"},
                }
            ]
        }

        with (
            patch("scripts.boards.get_json", return_value=payload),
            patch("scripts.boards.get_text", return_value="Expected graduation in 2029."),
        ):
            snapshot = fetch_board(board)  # type: ignore[arg-type]

        self.assertEqual(snapshot.observations[0].location, "Austin, Texas")
        self.assertEqual(
            snapshot.observations[0].url,
            "https://example.bamboohr.com/careers/123/",
        )

    def test_oracle_fetches_public_requisitions_and_details(self) -> None:
        board = {
            "key": "oracle:example.fa.us2.oraclecloud.com:external",
            "ats": "oracle",
            "company": "Example",
            "slug": "example",
            "site": "External",
            "host": "example.fa.us2.oraclecloud.com",
        }
        listing = {
            "items": [
                {
                    "TotalJobsCount": 1,
                    "requisitionList": [
                        {
                            "Id": "123",
                            "Title": "Software Engineer Intern",
                            "PrimaryLocation": "Austin, TX, United States",
                            "PostedDate": "2026-08-15",
                        }
                    ],
                }
            ]
        }

        with patch(
            "scripts.boards.get_json",
            side_effect=lambda url: (
                {"ExternalDescriptionStr": "Expected graduation in 2029."}
                if "RequisitionDetails" in url
                else listing
            ),
        ):
            snapshot = fetch_board(board)  # type: ignore[arg-type]

        self.assertEqual(len(snapshot.observations), 1)
        self.assertEqual(
            snapshot.observations[0].url,
            "https://example.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/"
            "en/sites/External/job/123",
        )
        self.assertIn("Expected graduation", snapshot.observations[0].description)


if __name__ == "__main__":
    unittest.main()
