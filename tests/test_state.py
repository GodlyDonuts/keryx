from __future__ import annotations

import unittest

from scripts.models import Observation
from scripts.state import merge_state


def role(source: str = "feed", url: str = "https://jobs.example.com/123") -> Observation:
    return Observation(
        source_id=source,
        source_label=source,
        source_url="https://example.com/source",
        external_id="123",
        company="Example",
        title="Software Engineer Intern - Summer 2027",
        location="Austin, TX",
        url=url,
        program="internship",
        cycle="summer-2027",
        trusted_us=False,
    )


class StateTests(unittest.TestCase):
    def test_two_complete_misses_close_role(self) -> None:
        state = merge_state({"jobs": []}, [role()], complete_sources={"feed"}, today="2026-08-01")
        state = merge_state(state, [], complete_sources={"feed"}, today="2026-08-02")
        self.assertEqual(state["jobs"][0]["status"], "open")
        state = merge_state(state, [], complete_sources={"feed"}, today="2026-08-03")
        self.assertEqual(state["jobs"][0]["status"], "closed")

    def test_failed_source_does_not_increment_miss(self) -> None:
        state = merge_state({"jobs": []}, [role()], complete_sources={"feed"}, today="2026-08-01")
        state = merge_state(state, [], complete_sources=set(), today="2026-08-02")
        self.assertEqual(state["jobs"][0]["missed_runs"], 0)

    def test_duplicates_merge_provenance(self) -> None:
        first = role("community", "https://company.example/job?gh_jid=123")
        second = role("ats:greenhouse:example", "https://job-boards.greenhouse.io/example/jobs/123")
        state = merge_state(
            {"jobs": []},
            [first, second],
            complete_sources={first.source_id, second.source_id},
            today="2026-08-01",
        )
        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(len(state["jobs"][0]["sources"]), 2)


if __name__ == "__main__":
    unittest.main()
