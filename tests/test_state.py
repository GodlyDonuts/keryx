from __future__ import annotations

import unittest

from scripts.models import Observation
from scripts.state import merge_state


def role(
    source: str = "feed",
    url: str = "https://jobs.example.com/123",
    description: str = "",
    location: str = "Austin, TX",
) -> Observation:
    return Observation(
        source_id=source,
        source_label=source,
        source_url="https://example.com/source",
        external_id="123",
        company="Example",
        title="Software Engineer Intern - Summer 2027",
        location=location,
        url=url,
        program="internship",
        cycle="summer-2027",
        trusted_us=False,
        description=description,
    )


class StateTests(unittest.TestCase):
    def test_single_source_custom_domain_is_published(self) -> None:
        url = (
            "https://careers.example.com/jobs/123?mobile=true&needsRedirect=false"
            "&source=trusted-feed#apply"
        )
        state = merge_state(
            {"jobs": []},
            [role(url=url)],
            complete_sources={"feed"},
            today="2026-08-01",
        )
        job = state["jobs"][0]
        self.assertEqual(job["url"], url)
        self.assertEqual(job["url_host"], "careers.example.com")
        self.assertEqual(job["link_status"], "source-reported")
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

    def test_jobright_duplicate_uses_existing_employer_link(self) -> None:
        direct = role("simplify-internships", "https://jobs.example.com/123")
        jobright = role(
            "jobright-swe-internships",
            "https://jobright.ai/jobs/info/abc123?utm_source=git",
        )
        state = merge_state(
            {"jobs": []},
            [jobright, direct],
            complete_sources={jobright.source_id, direct.source_id},
            today="2026-08-01",
        )

        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(state["jobs"][0]["url"], direct.url)
        self.assertEqual(len(state["jobs"][0]["sources"]), 2)

    def test_jobright_location_suffix_does_not_block_direct_link_upgrade(self) -> None:
        direct = role("simplify-internships", "https://amazon.jobs/jobs/123/apply")
        jobright = role(
            "jobright-swe-internships",
            "https://jobright.ai/jobs/info/abc123?utm_source=git",
            location="Austin, TX, United States",
        )

        state = merge_state(
            {"jobs": []},
            [jobright, direct],
            complete_sources={jobright.source_id, direct.source_id},
            today="2026-08-01",
        )

        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(state["jobs"][0]["url"], direct.url)

    def test_unique_company_and_title_match_can_resolve_location_formatting(self) -> None:
        direct = role(
            "ats:greenhouse:example",
            "https://job-boards.greenhouse.io/example/jobs/123",
            location="San Francisco, CA +1",
        )
        jobright = role(
            "jobright-swe-internships",
            "https://jobright.ai/jobs/info/abc123",
            location="Bellevue, WA, United States",
        )

        state = merge_state(
            {"jobs": []},
            [jobright, direct],
            complete_sources={jobright.source_id, direct.source_id},
            today="2026-08-01",
        )

        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(state["jobs"][0]["url"], direct.url)

    def test_corporate_descriptor_alias_resolves_jobright_link(self) -> None:
        direct = role(
            "ats:greenhouse:example",
            "https://job-boards.greenhouse.io/example/jobs/123",
        )
        direct = Observation(**{**direct.__dict__, "company": "Amazon Web Services"})
        jobright = role(
            "jobright-swe-internships",
            "https://jobright.ai/jobs/info/abc123",
        )
        jobright = Observation(**{**jobright.__dict__, "company": "Amazon"})

        state = merge_state(
            {"jobs": []},
            [jobright, direct],
            complete_sources={jobright.source_id, direct.source_id},
            today="2026-08-01",
        )

        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(state["jobs"][0]["url"], direct.url)

    def test_company_alias_match_refuses_ambiguous_direct_roles(self) -> None:
        first = role("feed-a", "https://amazon.jobs/jobs/123")
        first = Observation(**{**first.__dict__, "company": "Amazon Web Services"})
        second = role("feed-b", "https://amazon.jobs/jobs/456")
        second = Observation(**{**second.__dict__, "company": "Amazon Technologies"})
        jobright = role(
            "jobright-swe-internships",
            "https://jobright.ai/jobs/info/abc123",
        )
        jobright = Observation(**{**jobright.__dict__, "company": "Amazon"})

        state = merge_state(
            {"jobs": []},
            [jobright, first, second],
            complete_sources={jobright.source_id, first.source_id, second.source_id},
            today="2026-08-01",
        )

        self.assertEqual(len(state["jobs"]), 3)
        fallback = next(job for job in state["jobs"] if job["url_host"] == "jobright.ai")
        self.assertEqual(fallback["url"], jobright.url)

    def test_jobright_listing_upgrades_to_employer_link_without_duplication(self) -> None:
        jobright = role(
            "jobright-swe-internships",
            "https://jobright.ai/jobs/info/abc123?utm_source=git",
        )
        state = merge_state(
            {"jobs": []},
            [jobright],
            complete_sources={jobright.source_id},
            today="2026-08-01",
        )
        direct = role("simplify-internships", "https://jobs.example.com/123")
        state = merge_state(
            state,
            [jobright, direct],
            complete_sources={jobright.source_id, direct.source_id},
            today="2026-08-02",
        )

        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(state["jobs"][0]["url"], direct.url)
        self.assertEqual(state["jobs"][0]["first_seen"], "2026-08-01")

    def test_current_jobright_role_reuses_previous_direct_link_between_board_polls(self) -> None:
        direct = role("ats:greenhouse:example", "https://jobs.example.com/123")
        state = merge_state(
            {"jobs": []},
            [direct],
            complete_sources={direct.source_id},
            today="2026-08-01",
        )
        jobright = role(
            "jobright-swe-internships",
            "https://jobright.ai/jobs/info/abc123",
            location="Austin, TX, United States",
        )

        state = merge_state(
            state,
            [jobright],
            complete_sources={jobright.source_id},
            today="2026-08-02",
        )

        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(state["jobs"][0]["url"], direct.url)
        self.assertEqual(len(state["jobs"][0]["sources"]), 2)

    def test_reused_direct_link_removes_previous_jobright_duplicate(self) -> None:
        direct = role("ats:greenhouse:example", "https://jobs.example.com/123")
        direct_state = merge_state(
            {"jobs": []},
            [direct],
            complete_sources={direct.source_id},
            today="2026-08-01",
        )
        jobright = role(
            "jobright-swe-internships",
            "https://jobright.ai/jobs/info/abc123",
            location="Austin, TX, United States",
        )
        fallback_state = merge_state(
            {"jobs": []},
            [jobright],
            complete_sources={jobright.source_id},
            today="2026-08-01",
        )
        previous = {"jobs": [*direct_state["jobs"], *fallback_state["jobs"]]}

        state = merge_state(
            previous,
            [jobright],
            complete_sources={jobright.source_id},
            today="2026-08-02",
        )

        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(state["jobs"][0]["url"], direct.url)

    def test_career_site_resolution_wins_over_jobright_fallback(self) -> None:
        direct = role("career-site:example", "https://example.com/careers/jobs/123")
        jobright = role(
            "jobright-swe-internships",
            "https://jobright.ai/jobs/info/abc123",
        )

        state = merge_state(
            {"jobs": []},
            [jobright, direct],
            complete_sources={jobright.source_id, direct.source_id},
            today="2026-08-01",
        )

        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(state["jobs"][0]["url"], direct.url)

    def test_jobright_feeds_deduplicate_matching_roles(self) -> None:
        first = role(
            "jobright-swe-internships",
            "https://jobright.ai/jobs/info/abc123?utm_source=git",
        )
        second = role(
            "jobright-engineering-internships",
            "https://jobright.ai/jobs/info/def456?utm_source=git",
        )
        state = merge_state(
            {"jobs": []},
            [first, second],
            complete_sources={first.source_id, second.source_id},
            today="2026-08-01",
        )

        self.assertEqual(len(state["jobs"]), 1)
        self.assertEqual(len(state["jobs"][0]["sources"]), 2)

    def test_previous_source_reported_link_is_retained(self) -> None:
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
        self.assertEqual(state["jobs"][0]["url"], "https://127.0.0.1/collect")
        self.assertEqual(state["jobs"][0]["link_status"], "source-reported")

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
            today="2026-08-01",
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
            today="2026-08-02",
        )

        self.assertEqual(
            state["jobs"][0]["academic_eligibility"]["summary"],
            "Dec 2026–Jun 2027",
        )
        self.assertEqual(state["jobs"][0]["academic_eligibility"]["checked_at"], "2026-08-01")
        self.assertEqual(state["schema_version"], 2)

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
