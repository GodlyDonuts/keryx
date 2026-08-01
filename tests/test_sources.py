from __future__ import annotations

import unittest

from scripts.sources import parse_markdown_jobs


class SourceParserTests(unittest.TestCase):
    def test_speedyapply_html_table_row(self) -> None:
        text = (
            "| Company | Position | Location | Posting | Age |\n"
            "|---|---|---|---|---|\n"
            '| <a href="https://example.com"><strong>Example</strong></a> | '
            "Software Engineer Intern - Summer 2027 | Austin, TX | "
            '<a href="https://jobs.example.com/123"><img alt="Apply"/></a> | 1d |\n'
        )
        jobs = parse_markdown_jobs(
            text,
            source_id="speedy-internships",
            source_label="SpeedyApply",
            program="internship",
            cycle_hint=None,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "Example")
        self.assertEqual(jobs[0].url, "https://jobs.example.com/123")

    def test_plain_markdown_table_row_and_closed_filter(self) -> None:
        text = (
            "| Example | Data Science Intern (Summer 2027) | Boston, MA | "
            "[apply](https://jobs.example.com/1) | 2026-08-01 |\n"
            "| Closed | Software Intern 🔒 | Boston, MA | "
            "[apply](https://jobs.example.com/2) | 2026-08-01 |\n"
        )
        jobs = parse_markdown_jobs(
            text,
            source_id="sndsh-internships",
            source_label="List",
            program="internship",
            cycle_hint="summer-2027",
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].posted_at, "2026-08-01")


if __name__ == "__main__":
    unittest.main()
