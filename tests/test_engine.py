from __future__ import annotations

import unittest

from rolebeacon.engine import synchronize
from rolebeacon.models import Observation, SourceSnapshot
from rolebeacon.store import empty_state


def observation(identifier: str, *, active: bool = True, source: str = "feed") -> Observation:
    return Observation(
        source=source,
        external_id=identifier,
        company="Example",
        title=f"Software Intern {identifier}",
        url=f"https://jobs.example.com/{identifier}",
        locations=("New York, NY",),
        active=active,
    )


class EngineTests(unittest.TestCase):
    def test_initial_sync_is_silent_baseline(self) -> None:
        snapshot = SourceSnapshot("feed", (observation("one"),))
        state, result = synchronize(
            empty_state(), (snapshot,), now="2026-08-01T00:00:00Z", close_after_misses=2
        )
        self.assertTrue(result.baseline)
        self.assertEqual(result.events, ())
        self.assertEqual(len(state["jobs"]), 1)

    def test_explicit_inactive_record_closes_immediately(self) -> None:
        populated, _ = synchronize(
            empty_state(),
            (SourceSnapshot("feed", (observation("one"),)),),
            now="2026-08-01T00:00:00Z",
            close_after_misses=2,
        )
        closed, result = synchronize(
            populated,
            (SourceSnapshot("feed", (observation("one", active=False),)),),
            now="2026-08-01T01:00:00Z",
            close_after_misses=2,
        )
        self.assertEqual(next(iter(closed["jobs"].values()))["status"], "closed")
        self.assertEqual([event.event_type for event in result.events], ["closed"])

    def test_historical_closed_role_is_not_added_to_state(self) -> None:
        state, result = synchronize(
            empty_state(),
            (SourceSnapshot("feed", (observation("old", active=False),)),),
            now="2026-08-01T00:00:00Z",
            close_after_misses=2,
        )
        self.assertEqual(state["jobs"], {})
        self.assertEqual(result.events, ())

    def test_later_opening_emits_one_event(self) -> None:
        first = SourceSnapshot("feed", (observation("one"),))
        state, _ = synchronize(
            empty_state(), (first,), now="2026-08-01T00:00:00Z", close_after_misses=2
        )
        second = SourceSnapshot("feed", (observation("one"), observation("two")))
        updated, result = synchronize(
            state, (second,), now="2026-08-01T01:00:00Z", close_after_misses=2
        )
        self.assertEqual([event.event_type for event in result.events], ["opened"])
        self.assertEqual(result.event_history, result.events)

        _, later = synchronize(
            updated,
            (second,),
            now="2026-08-01T02:00:00Z",
            close_after_misses=2,
        )
        self.assertEqual(later.events, ())
        self.assertEqual([event.event_type for event in later.event_history], ["opened"])

    def test_two_complete_misses_close_a_role(self) -> None:
        populated, _ = synchronize(
            empty_state(),
            (SourceSnapshot("feed", (observation("one"),)),),
            now="2026-08-01T00:00:00Z",
            close_after_misses=2,
        )
        once, first_miss = synchronize(
            populated,
            (SourceSnapshot("feed", (), complete=True),),
            now="2026-08-01T01:00:00Z",
            close_after_misses=2,
        )
        twice, second_miss = synchronize(
            once,
            (SourceSnapshot("feed", (), complete=True),),
            now="2026-08-01T02:00:00Z",
            close_after_misses=2,
        )
        self.assertEqual(first_miss.events, ())
        self.assertEqual([event.event_type for event in second_miss.events], ["closed"])
        self.assertEqual(next(iter(twice["jobs"].values()))["status"], "closed")

    def test_incomplete_snapshot_does_not_increment_misses(self) -> None:
        populated, _ = synchronize(
            empty_state(),
            (SourceSnapshot("feed", (observation("one"),)),),
            now="2026-08-01T00:00:00Z",
            close_after_misses=1,
        )
        unchanged, result = synchronize(
            populated,
            (SourceSnapshot("feed", (), complete=False),),
            now="2026-08-01T01:00:00Z",
            close_after_misses=1,
        )
        job = next(iter(unchanged["jobs"].values()))
        self.assertEqual(job["status"], "open")
        self.assertEqual(result.events, ())

    def test_duplicate_url_merges_source_provenance(self) -> None:
        first = observation("same", source="one")
        second = Observation(
            source="two",
            external_id="different-upstream-id",
            company=first.company,
            title=first.title,
            url=first.url + "?utm_source=community",
        )
        state, _ = synchronize(
            empty_state(),
            (SourceSnapshot("one", (first,)), SourceSnapshot("two", (second,))),
            now="2026-08-01T00:00:00Z",
            close_after_misses=2,
        )
        self.assertEqual(len(state["jobs"]), 1)
        job = next(iter(state["jobs"].values()))
        self.assertEqual(set(job["sources"]), {"one", "two"})

    def test_other_active_source_prevents_closure(self) -> None:
        shared = observation("same", source="one")
        other = Observation(
            source="two",
            external_id="other",
            company=shared.company,
            title=shared.title,
            url=shared.url,
        )
        state, _ = synchronize(
            empty_state(),
            (SourceSnapshot("one", (shared,)), SourceSnapshot("two", (other,))),
            now="2026-08-01T00:00:00Z",
            close_after_misses=1,
        )
        state, result = synchronize(
            state,
            (SourceSnapshot("one", ()),),
            now="2026-08-01T01:00:00Z",
            close_after_misses=1,
        )
        self.assertEqual(next(iter(state["jobs"].values()))["status"], "open")
        self.assertEqual(result.events, ())


if __name__ == "__main__":
    unittest.main()
