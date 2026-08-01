from __future__ import annotations

import unittest

from scripts.boards import board_from_observation, discover_boards
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


if __name__ == "__main__":
    unittest.main()
