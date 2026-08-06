from __future__ import annotations

import unittest

from scripts.models import Observation, Snapshot
from scripts.provenance import source_is_fresh, update_source_health


def observation(source_id: str) -> Observation:
    return Observation(
        source_id=source_id,
        source_label="Source",
        source_url="https://example.com/source",
        external_id="123",
        company="Example",
        title="Software Engineer Intern",
        location="Austin, TX",
        url="https://job-boards.greenhouse.io/example/jobs/123",
        program="internship",
    )


class ProvenanceTests(unittest.TestCase):
    def test_source_health_preserves_last_complete_run_across_failure(self) -> None:
        source_id = "ats:greenhouse:example"
        complete = Snapshot(source_id, (observation(source_id),), complete=True)
        health = update_source_health(
            {},
            (complete,),
            {},
            checked_at="2026-08-06T12:00:00Z",
        )
        health = update_source_health(
            health,
            (),
            {source_id: "temporary failure"},
            checked_at="2026-08-06T12:15:00Z",
        )

        record = health["sources"][source_id]
        self.assertEqual(record["outcome"], "failed")
        self.assertEqual(record["last_complete_at"], "2026-08-06T12:00:00Z")
        self.assertFalse(source_is_fresh(source_id, health, as_of="2026-08-06T12:16:00Z"))

    def test_partial_snapshot_is_visible_but_not_called_complete(self) -> None:
        source_id = "ats:workday:example"
        partial = Snapshot(source_id, (observation(source_id),), complete=False)
        health = update_source_health(
            {},
            (partial,),
            {},
            checked_at="2026-08-06T12:00:00Z",
        )

        record = health["sources"][source_id]
        self.assertEqual(record["outcome"], "partial")
        self.assertNotIn("last_complete_at", record)
        self.assertFalse(source_is_fresh(source_id, health, as_of="2026-08-06T12:30:00Z"))

    def test_direct_and_upstream_freshness_windows_are_bounded(self) -> None:
        direct_id = "ats:greenhouse:example"
        upstream_id = "community"
        health = update_source_health(
            {},
            (
                Snapshot(direct_id, (observation(direct_id),), complete=True),
                Snapshot(upstream_id, (observation(upstream_id),), complete=True),
            ),
            {},
            checked_at="2026-08-06T12:00:00Z",
        )

        self.assertTrue(source_is_fresh(direct_id, health, as_of="2026-08-06T13:30:00Z"))
        self.assertFalse(source_is_fresh(direct_id, health, as_of="2026-08-06T14:01:00Z"))
        self.assertFalse(source_is_fresh(upstream_id, health, as_of="2026-08-06T12:46:00Z"))


if __name__ == "__main__":
    unittest.main()
