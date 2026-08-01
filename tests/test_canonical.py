from __future__ import annotations

import unittest

from keryx.canonical import canonical_url, job_identity


class CanonicalTests(unittest.TestCase):
    def test_tracking_parameters_and_apply_suffix_do_not_change_identity(self) -> None:
        first = "http://Jobs.Example.com/roles/123/apply?utm_source=github#top"
        second = "https://jobs.example.com/roles/123"
        self.assertEqual(canonical_url(first), second)
        self.assertEqual(
            job_identity(url=first, source="one", external_id="a"),
            job_identity(url=second, source="two", external_id="b"),
        )

    def test_job_identifying_query_parameter_is_retained(self) -> None:
        first = canonical_url("https://example.com/job?gh_jid=123&utm_source=x")
        second = canonical_url("https://example.com/job?gh_jid=456")
        self.assertEqual(first, "https://example.com/job?gh_jid=123")
        self.assertNotEqual(first, second)

    def test_invalid_url_falls_back_to_source_identity(self) -> None:
        self.assertEqual(
            job_identity(url="not a URL", source="Feed", external_id="123"),
            job_identity(url="", source="feed", external_id="123"),
        )


if __name__ == "__main__":
    unittest.main()
