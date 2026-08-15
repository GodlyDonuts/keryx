from __future__ import annotations

import unittest

from scripts.boards import Board
from scripts.models import Observation
from scripts.update import _bounded_ats_batch, _quarantine_report


class QuarantineTests(unittest.TestCase):
    def test_workable_polling_is_bounded_without_limiting_other_boards(self) -> None:
        workable: list[Board] = [
            {"key": f"workable:{index}", "ats": "workable", "slug": str(index)}
            for index in range(10)
        ]
        greenhouse: Board = {
            "key": "greenhouse:example",
            "ats": "greenhouse",
            "slug": "example",
        }

        selected = _bounded_ats_batch(
            [greenhouse, *workable],
            {"workable:9"},
            quarter=123,
        )

        self.assertIn(greenhouse, selected)
        self.assertEqual(sum(board["ats"] == "workable" for board in selected), 4)
        self.assertIn(workable[9], selected)

    def test_report_never_retains_the_rejected_url(self) -> None:
        observation = Observation(
            source_id="feed",
            source_label="Feed",
            source_url="https://example.com",
            external_id="bad",
            company="Example",
            title="Software Engineer Intern",
            location="Austin, TX",
            url="mailto:secret@example.com?token=private",
            program="internship",
        )
        report = _quarantine_report([observation])
        serialized = str(report)
        self.assertEqual(len(report["quarantined"]), 1)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("token", serialized)
        self.assertNotIn("collect", serialized)


if __name__ == "__main__":
    unittest.main()
