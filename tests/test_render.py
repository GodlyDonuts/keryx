from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from scripts.render import _latest_table, render_repository


class RenderTests(unittest.TestCase):
    def test_front_page_prefers_direct_link_when_posting_dates_tie(self) -> None:
        common = {
            "program": "internship",
            "cycle": "summer-2027",
            "location": "Austin, TX",
            "posted_at": "2026-08-15",
        }
        fallback = {
            **common,
            "company": "A Company",
            "title": "Software Engineer Intern",
            "url": "https://jobright.ai/jobs/info/123",
            "url_host": "jobright.ai",
        }
        direct = {
            **common,
            "company": "Z Company",
            "title": "Data Engineer Intern",
            "url": "https://jobs.example.com/456",
            "url_host": "jobs.example.com",
        }

        table = _latest_table([fallback, direct], "internship", limit=1)

        self.assertIn("Z Company", table)
        self.assertNotIn("A Company", table)

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
                    "academic_eligibility": {
                        "extractor_version": 1,
                        "checked_at": "2026-08-01",
                        "status": "explicit-window",
                        "summary": "Dec 2026–Jun 2027",
                        "requirement_level": "required",
                        "graduation_start": "2026-12",
                        "graduation_end": "2027-06",
                        "graduation_years": [2026, 2027],
                        "currently_enrolled": True,
                        "currently_enrolled_level": "preferred",
                        "source_id": "source-a",
                        "source_label": "Source A",
                        "confidence": "source-text",
                        "evidence": "Expected graduation between December 2026 and June 2027.",
                        "graduation_evidence": (
                            "Expected graduation between December 2026 and June 2027."
                        ),
                        "currently_enrolled_evidence": "Currently enrolled is preferred.",
                    },
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
                "# Keryx\n\n<!-- COUNTS:START -->\nold\n<!-- COUNTS:END -->\n"
                "<!-- LATEST-INTERNSHIPS:START -->\nold\n<!-- LATEST-INTERNSHIPS:END -->\n"
                "<!-- LATEST-NEW-GRAD:START -->\nold\n<!-- LATEST-NEW-GRAD:END -->\n",
                encoding="utf-8",
            )
            render_repository(root, payload, [])
            summer = (root / "internships/summer-2027.md").read_text(encoding="utf-8")
            self.assertIn("**1 open roles**", summer)
            self.assertIn("Example", summer)
            self.assertIn("apply · jobs.example.com", summer)
            self.assertIn("cross-checked", summer)
            self.assertIn("Academic eligibility", summer)
            self.assertIn("Dec 2026–Jun 2027", summer)
            self.assertIn("graduation: required", summer)
            self.assertIn("enrollment: preferred", summer)
            self.assertIn("checked 2026-08-01", summer)
            self.assertIn("Source A", summer)
            archive = (root / "archive/closed.md").read_text(encoding="utf-8")
            self.assertIn("**0 closed roles**", archive)
            readme = (root / "README.md").read_text(encoding="utf-8")
            self.assertIn("**1 internships · 0 new-grad roles · 1 total openings**", readme)
            self.assertIn("☀️ Summer 2027 | 1", readme)
            self.assertIn("Software Engineer Intern", readme)
            self.assertIn("Dec 2026–Jun 2027<br><sub>required / preferred</sub>", readme)
            self.assertIn("**[Apply →](https://jobs.example.com/1)**", readme)
            self.assertNotIn("old", readme)
            stored = json.loads((root / "data/jobs.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["country"], "United States")

    def test_missing_destination_is_rendered_as_unavailable(self) -> None:
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
                "<!-- COUNTS:START -->\nold\n<!-- COUNTS:END -->\n"
                "<!-- LATEST-INTERNSHIPS:START -->\nold\n<!-- LATEST-INTERNSHIPS:END -->\n"
                "<!-- LATEST-NEW-GRAD:START -->\nold\n<!-- LATEST-NEW-GRAD:END -->\n",
                encoding="utf-8",
            )
            render_repository(root, payload, [])
            summer = (root / "internships/summer-2027.md").read_text(encoding="utf-8")
        self.assertIn("link unavailable", summer)
        self.assertIn("careers.example.com", summer)
        self.assertNotIn("careers.example.com](", summer)
        self.assertNotIn("](https://evil.example)", summer)
        self.assertNotIn("password", summer)

    def test_source_reported_destination_is_rendered_as_a_link(self) -> None:
        url = (
            "https://jobs.bytedance.com/en/position/(123)/detail?source=trusted-feed"
            "&campaign=fall|2026#apply"
        )
        payload: dict[str, Any] = {
            "jobs": [
                {
                    "id": "job_reported",
                    "company": "ByteDance",
                    "title": "Software Engineer Intern",
                    "location": "San Jose, CA",
                    "url": url,
                    "url_host": "jobs.bytedance.com",
                    "url_fingerprint": hashlib.sha256(url.encode()).hexdigest()[:24],
                    "link_status": "source-reported",
                    "program": "internship",
                    "cycle": "summer-2027",
                    "posted_at": "2026-08-01",
                    "status": "open",
                    "sources": [
                        {
                            "id": "simplify-internships",
                            "label": "Simplify",
                            "url": "https://github.com/SimplifyJobs/Summer2027-Internships",
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<!-- COUNTS:START -->\nold\n<!-- COUNTS:END -->\n"
                "<!-- LATEST-INTERNSHIPS:START -->\nold\n<!-- LATEST-INTERNSHIPS:END -->\n"
                "<!-- LATEST-NEW-GRAD:START -->\nold\n<!-- LATEST-NEW-GRAD:END -->\n",
                encoding="utf-8",
            )
            render_repository(root, payload, [])
            summer = (root / "internships/summer-2027.md").read_text(encoding="utf-8")

        self.assertIn(
            "](https://jobs.bytedance.com/en/position/%28123%29/detail?"
            "source=trusted-feed&campaign=fall%7C2026#apply)",
            summer,
        )
        self.assertIn("source reported", summer)

    def test_jobright_discovery_is_not_labeled_as_direct_apply(self) -> None:
        url = "https://jobright.ai/jobs/info/abc123?utm_source=git"
        payload: dict[str, Any] = {
            "jobs": [
                {
                    "id": "job_jobright",
                    "company": "Example",
                    "title": "Software Engineer Intern",
                    "location": "Austin, TX",
                    "url": url,
                    "url_host": "jobright.ai",
                    "url_fingerprint": hashlib.sha256(url.encode()).hexdigest()[:24],
                    "link_status": "source-reported",
                    "program": "internship",
                    "cycle": "summer-2027",
                    "posted_at": "2026-08-14",
                    "status": "open",
                    "sources": [
                        {
                            "id": "jobright-swe-internships",
                            "label": "Jobright · Software Engineering",
                            "url": "https://github.com/jobright-ai/2026-Software-Engineer-Internship",
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<!-- COUNTS:START -->\nold\n<!-- COUNTS:END -->\n"
                "<!-- LATEST-INTERNSHIPS:START -->\nold\n<!-- LATEST-INTERNSHIPS:END -->\n"
                "<!-- LATEST-NEW-GRAD:START -->\nold\n<!-- LATEST-NEW-GRAD:END -->\n",
                encoding="utf-8",
            )
            render_repository(root, payload, [])
            readme = (root / "README.md").read_text(encoding="utf-8")
            summer = (root / "internships/summer-2027.md").read_text(encoding="utf-8")

        self.assertIn("**[View job →]", readme)
        self.assertNotIn("**[Apply →]", readme)
        self.assertIn("[view job · Jobright]", summer)
        self.assertNotIn("[apply · jobright.ai]", summer)

    def test_render_does_not_hide_a_clickable_url_based_on_status(self) -> None:
        url = "https://careers.example.com/jobs/123?source=trusted-feed"
        payload: dict[str, Any] = {
            "jobs": [
                {
                    "id": "job_bad",
                    "company": "Example",
                    "title": "Software Engineer Intern",
                    "location": "Austin, TX",
                    "url": url,
                    "url_host": "careers.example.com",
                    "url_fingerprint": hashlib.sha256(url.encode()).hexdigest()[:24],
                    "link_status": "unverified",
                    "program": "internship",
                    "cycle": "summer-2027",
                    "posted_at": "2026-08-01",
                    "status": "open",
                    "sources": [
                        {
                            "id": "configured-feed",
                            "label": "Configured feed",
                            "url": "https://example.com/feed",
                        }
                    ],
                }
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(
                "<!-- COUNTS:START -->\nold\n<!-- COUNTS:END -->\n"
                "<!-- LATEST-INTERNSHIPS:START -->\nold\n<!-- LATEST-INTERNSHIPS:END -->\n"
                "<!-- LATEST-NEW-GRAD:START -->\nold\n<!-- LATEST-NEW-GRAD:END -->\n",
                encoding="utf-8",
            )
            render_repository(root, payload, [])
            summer = (root / "internships/summer-2027.md").read_text(encoding="utf-8")

        self.assertIn(f"]({url})", summer)


if __name__ == "__main__":
    unittest.main()
