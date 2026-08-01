from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.render import render_repository


class RenderTests(unittest.TestCase):
    def test_cycle_markdown_and_readme_counts_are_generated(self) -> None:
        payload = {
            "schema_version": 1,
            "country": "United States",
            "jobs": [
                {
                    "id": "job_1",
                    "company": "Example",
                    "title": "Software Engineer Intern",
                    "location": "Austin, TX",
                    "url": "https://jobs.example.com/1",
                    "program": "internship",
                    "cycle": "summer-2027",
                    "posted_at": "2026-08-01",
                    "status": "open",
                    "sources": [{"id": "source", "label": "Source", "url": "https://example.com"}],
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
            archive = (root / "archive/closed.md").read_text(encoding="utf-8")
            self.assertIn("**0 closed roles**", archive)
            readme = (root / "README.md").read_text(encoding="utf-8")
            self.assertIn("Summer 2027 US Internships](internships/summer-2027.md) | 1", readme)
            stored = json.loads((root / "data/jobs.json").read_text(encoding="utf-8"))
            self.assertEqual(stored["country"], "United States")


if __name__ == "__main__":
    unittest.main()
