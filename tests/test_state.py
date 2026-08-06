from __future__ import annotations

import unittest

from scripts.models import Observation
from scripts.state import merge_state


def role(
    source: str = "feed",
    url: str = "https://jobs.example.com/123",
    description: str = "",
    posted_at: str | None = None,
) -> Observation:
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
        description=description,
        posted_at=posted_at,
    )


def source_health(at: str, *source_ids: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "sources": {
            source_id: {
                "source_id": source_id,
                "outcome": "complete",
                "last_success_at": at,
                "last_complete_at": at,
            }
            for source_id in source_ids
        },
    }


class StateTests(unittest.TestCase):
    def test_single_source_custom_domain_is_not_published(self) -> None:
        state = merge_state(
            {"jobs": []},
            [role(url="https://careers.example.com/jobs/123")],
            complete_sources={"feed"},
            today="2026-08-01",
        )
        job = state["jobs"][0]
        self.assertIsNone(job["url"])
        self.assertEqual(job["url_host"], "careers.example.com")
        self.assertEqual(job["link_status"], "unverified")
        self.assertNotIn("_candidate_url", job)

    def test_structured_recruiting_platform_link_is_published(self) -> None:
        state = merge_state(
            {"jobs": []},
            [role(url="https://job-boards.greenhouse.io/example/jobs/123")],
            complete_sources={"feed"},
            today="2026-08-01",
        )
        job = state["jobs"][0]
        self.assertEqual(job["url"], "https://job-boards.greenhouse.io/example/jobs/123")
        self.assertEqual(job["link_status"], "platform-structured")

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
        first = role("community", "https://company.com/job?gh_jid=123")
        second = role("ats:greenhouse:example", "https://job-boards.greenhouse.io/example/jobs/123")
        state = merge_state(
            {"jobs": []},
            [first, second],
            complete_sources={first.source_id, second.source_id},
            today="2026-08-01",
        )
        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(len(state["jobs"][0]["sources"]), 2)
        self.assertEqual(state["jobs"][0]["link_status"], "ats-verified")

    def test_authoritative_field_selection_retains_conflicting_dates(self) -> None:
        community = role(
            "community",
            "https://company.com/job?gh_jid=123",
            posted_at="2026-08-01",
        )
        direct = role(
            "ats:greenhouse:example",
            "https://job-boards.greenhouse.io/example/jobs/123",
            posted_at="2026-08-03",
        )
        state = merge_state(
            {"jobs": []},
            [community, direct],
            complete_sources={community.source_id, direct.source_id},
            observed_at="2026-08-06T12:00:00Z",
        )

        job = state["jobs"][0]
        self.assertEqual(job["posted_at"], "2026-08-03")
        self.assertEqual(job["field_sources"]["posted_at"], direct.source_id)
        self.assertEqual(
            job["field_conflicts"]["posted_at"],
            [{"value": "2026-08-01", "source_id": community.source_id}],
        )

    def test_completed_ats_disappearance_downgrades_current_verification(self) -> None:
        community = role("community", "https://company.com/job?gh_jid=123")
        direct = role(
            "ats:greenhouse:example",
            "https://job-boards.greenhouse.io/example/jobs/123",
        )
        first_at = "2026-08-06T12:00:00Z"
        state = merge_state(
            {"jobs": []},
            [community, direct],
            complete_sources={community.source_id, direct.source_id},
            observed_at=first_at,
            source_health=source_health(first_at, community.source_id, direct.source_id),
        )
        second_at = "2026-08-06T12:15:00Z"
        state = merge_state(
            state,
            [community],
            complete_sources={community.source_id, direct.source_id},
            observed_at=second_at,
            source_health=source_health(second_at, community.source_id, direct.source_id),
        )

        job = state["jobs"][0]
        self.assertEqual(job["link_status"], "unverified")
        self.assertIsNone(job["url"])
        self.assertEqual(job["current_source_ids"], ["community"])
        self.assertEqual(job["historical_source_ids"], [direct.source_id])
        self.assertTrue(job["previously_ats_observed"])
        direct_record = next(item for item in job["sources"] if item["id"] == direct.source_id)
        self.assertEqual(direct_record["state"], "historical")

    def test_unpolled_direct_source_remains_current_only_while_fresh(self) -> None:
        community = role("community", "https://company.com/job?gh_jid=123")
        direct = role(
            "ats:greenhouse:example",
            "https://job-boards.greenhouse.io/example/jobs/123",
        )
        first_at = "2026-08-06T12:00:00Z"
        health = source_health(first_at, community.source_id, direct.source_id)
        state = merge_state(
            {"jobs": []},
            [community, direct],
            complete_sources={community.source_id, direct.source_id},
            observed_at=first_at,
            source_health=health,
        )
        state = merge_state(
            state,
            [community],
            complete_sources={community.source_id},
            observed_at="2026-08-06T12:30:00Z",
            source_health=health,
        )
        self.assertEqual(state["jobs"][0]["link_status"], "ats-verified")

        state = merge_state(
            state,
            [community],
            complete_sources={community.source_id},
            observed_at="2026-08-06T14:01:00Z",
            source_health=health,
        )
        self.assertEqual(state["jobs"][0]["link_status"], "unverified")
        self.assertIn(direct.source_id, state["jobs"][0]["historical_source_ids"])

    def test_unsafe_previous_link_is_removed_without_a_grace_period(self) -> None:
        previous = {
            "jobs": [
                {
                    "id": "unsafe",
                    "url": "https://127.0.0.1/collect",
                    "status": "open",
                    "sources": [{"id": "feed", "label": "Feed", "url": "https://example.com"}],
                }
            ]
        }
        state = merge_state(previous, [], complete_sources=set(), today="2026-08-01")
        self.assertEqual(state["jobs"], [])

    def test_academic_requirement_survives_metadata_only_polling_run(self) -> None:
        direct = role(
            "ats:greenhouse:example",
            "https://job-boards.greenhouse.io/example/jobs/123",
            "Expected graduation date between December 2026 and June 2027.",
        )
        state = merge_state(
            {"jobs": []},
            [direct],
            complete_sources={direct.source_id},
            observed_at="2026-08-01T12:00:00Z",
            source_health=source_health("2026-08-01T12:00:00Z", direct.source_id),
        )
        self.assertEqual(
            state["jobs"][0]["academic_eligibility"]["summary"],
            "Dec 2026–Jun 2027",
        )

        community = role("community", "https://job-boards.greenhouse.io/example/jobs/123")
        state = merge_state(
            state,
            [community],
            complete_sources={community.source_id},
            observed_at="2026-08-01T12:30:00Z",
            source_health=source_health(
                "2026-08-01T12:00:00Z", direct.source_id, community.source_id
            ),
        )

        self.assertEqual(
            state["jobs"][0]["academic_eligibility"]["summary"],
            "Dec 2026–Jun 2027",
        )
        self.assertEqual(
            state["jobs"][0]["academic_eligibility"]["checked_at"],
            "2026-08-01T12:00:00Z",
        )
        self.assertEqual(state["schema_version"], 3)

    def test_stale_academic_extractor_result_is_not_preserved(self) -> None:
        direct = role(
            "ats:greenhouse:example",
            "https://job-boards.greenhouse.io/example/jobs/123",
            "Expected graduation is May 2028.",
        )
        state = merge_state(
            {"jobs": []},
            [direct],
            complete_sources={direct.source_id},
            today="2026-08-01",
        )
        state["jobs"][0]["academic_eligibility"].pop("extractor_version")

        community = role("community", "https://job-boards.greenhouse.io/example/jobs/123")
        state = merge_state(
            state,
            [community],
            complete_sources={community.source_id},
            today="2026-08-02",
        )

        eligibility = state["jobs"][0]["academic_eligibility"]
        self.assertEqual(eligibility["status"], "unavailable")
        self.assertEqual(eligibility["extractor_version"], 1)


if __name__ == "__main__":
    unittest.main()
