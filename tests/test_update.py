from __future__ import annotations

import unittest

from scripts.models import Observation
from scripts.update import _quarantine_report


class QuarantineTests(unittest.TestCase):
    def test_report_never_retains_the_rejected_url(self) -> None:
        observation = Observation(
            source_id="feed",
            source_label="Feed",
            source_url="https://example.com",
            external_id="bad",
            company="Example",
            title="Software Engineer Intern",
            location="Austin, TX",
            url="https://user:secret@127.0.0.1/collect?token=private",
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
