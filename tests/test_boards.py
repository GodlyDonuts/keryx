from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.boards import board_from_observation, discover_boards, fetch_board
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

    def test_workday_keyword_search_is_never_a_complete_board_snapshot(self) -> None:
        board = {
            "key": "workday:example.wd5.myworkdayjobs.com:example:careers",
            "ats": "workday",
            "company": "Example",
            "slug": "example",
            "site": "careers",
            "host": "example.wd5.myworkdayjobs.com",
        }
        payload = {
            "total": 1,
            "jobPostings": [
                {
                    "title": "Software Engineer Intern",
                    "locationsText": "Austin, TX",
                    "externalPath": "/job/Austin/Software-Engineer-Intern_REQ1",
                }
            ],
        }

        with patch("scripts.boards.post_json", return_value=payload):
            snapshot = fetch_board(board)  # type: ignore[arg-type]

        self.assertFalse(snapshot.complete)
        self.assertEqual(len(snapshot.observations), 1)


if __name__ == "__main__":
    unittest.main()
