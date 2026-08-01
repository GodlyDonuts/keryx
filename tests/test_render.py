from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from scripts.render import render_repository


class RenderTests(unittest.TestCase):
    def test_cycle_markdown_and_readme_counts_are_generated(self) -> None:
        payload: dict[str, Any] = {
            "schema_version": 1,
            "country": "United States",
            "jobs": [
                {
                    "id": "job_1",
                    "company": "Example",
                    "title": "Software Engineer Intern [click](https://evil.example)",
                    "location": "Austin, TX",
                    "url": "https://jobs.example.com/1",
                    "url_host": "jobs.example.com",
                    "url_fingerprint": hashlib.sha256(b"https://jobs.example.com/1").hexdigest()[
                        :24
                    ],
                    "link_status": "cross-source",
                    "program": "internship",
                    "cycle": "summer-2027",
                    "posted_at": "2026-08-01",
                    "status": "open",
                    "sources": [
                        {"id": "source-a", "label": "Source A", "url": "https://example.com"},
                        {"id": "source-b", "label": "Source B", "url": "https://example.org"},
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "# Keryx\n\n<!-- COUNTS:START -->\nold\n<!-- COUNTS:END -->\n",
                encoding="utf-8",
            )
            render_repository(root, payload, [])
            summer = (root / "internships/summer-2027.md").read_text(encoding="utf-8")
            self.assertIn("**1 open roles**", summer)
            self.assertIn("Example", summer)
            self.assertIn("apply · jobs.example.com", summer)
            self.assertIn("cross-checked", summer)
            archive = (root / "archive/closed.md").read_text(encoding="utf-8")
            self.assertIn("**0 closed roles**", archive)
            readme = (root / "README.md").read_text(encoding="utf-8")
            self.assertIn("Summer 2027 US Internships](internships/summer-2027.md) | 1", readme)
            stored = json.loads((root / "data/jobs.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["country"], "United States")

    def test_unverified_destination_is_not_rendered_as_a_link(self) -> None:
        payload: dict[str, Any] = {
            "jobs": [
                {
                    "id": "job_unsafe",
                    "company": "Example",
                    "title": "Software Engineer Intern",
                    "location": "Austin, TX",
                    "url": None,
                    "url_host": "careers.example.com",
                    "url_fingerprint": "b" * 24,
                    "link_status": "unverified",
                    "program": "internship",
                    "cycle": "summer-2027",
                    "posted_at": "2026-08-01",
                    "status": "open",
                    "sources": [
                        {
                            "id": "bad-source",
                            "label": "Reported source",
                            "url": "https://user:password@github.com/example/jobs",
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<!-- COUNTS:START -->\nold\n<!-- COUNTS:END -->\n", encoding="utf-8"
            )
            render_repository(root, payload, [])
            summer = (root / "internships/summer-2027.md").read_text(encoding="utf-8")
        self.assertIn("destination withheld", summer)
        self.assertIn("careers.example.com", summer)
        self.assertNotIn("careers.example.com](", summer)
        self.assertNotIn("](https://evil.example)", summer)
        self.assertNotIn("password", summer)

    def test_render_refuses_an_unverified_clickable_url(self) -> None:
        payload: dict[str, Any] = {
            "jobs": [
                {
                    "id": "job_bad",
                    "url": "https://evil.example/jobs/123",
                    "url_host": "evil.example",
                    "url_fingerprint": "c" * 24,
                    "link_status": "unverified",
                    "status": "open",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<!-- COUNTS:START -->\nold\n<!-- COUNTS:END -->\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                render_repository(root, payload, [])


if __name__ == "__main__":
    unittest.main()
