from __future__ import annotations

import unittest

from rolebeacon.config import SourceConfig
from rolebeacon.providers import fetch_source


class ProviderTests(unittest.TestCase):
    def test_intern_engine_adapter(self) -> None:
        payload = {
            "jobs": [
                {
                    "id": "lever:example:123",
                    "company": "Example",
                    "title": "Software Intern",
                    "season": "Summer 2027",
                    "location": "Remote",
                    "url": "https://jobs.example.com/123",
                    "posted_at": "2026-08-01T00:00:00Z",
                    "remote": True,
                    "source": "lever",
                },
                {"id": "malformed"},
            ]
        }
        source = SourceConfig("engine", "intern-engine", "https://example.com/jobs.json")
        snapshot = fetch_source(source, fetcher=lambda _: payload)
        self.assertTrue(snapshot.complete)
        self.assertEqual(len(snapshot.observations), 1)
        self.assertEqual(snapshot.observations[0].cycles, ("Summer 2027",))
        self.assertEqual(snapshot.observations[0].metadata["upstream_source"], "lever")

    def test_simplify_adapter_preserves_explicit_inactive_state(self) -> None:
        payload = [
            {
                "id": "abc",
                "company_name": "Example",
                "title": "Data Intern",
                "url": "https://jobs.example.com/abc/apply",
                "locations": ["Boston, MA"],
                "terms": ["Fall 2026"],
                "active": False,
                "is_visible": True,
                "date_posted": 1785542400,
            }
        ]
        source = SourceConfig("list", "simplify", "https://example.com/listings.json")
        snapshot = fetch_source(source, fetcher=lambda _: payload)
        self.assertFalse(snapshot.observations[0].active)
        self.assertEqual(snapshot.observations[0].locations, ("Boston, MA",))

    def test_unknown_adapter_is_rejected(self) -> None:
        source = SourceConfig("bad", "unknown", "https://example.com/jobs.json")
        with self.assertRaisesRegex(ValueError, "unsupported source kind"):
            fetch_source(source, fetcher=lambda _: {})


if __name__ == "__main__":
    unittest.main()
