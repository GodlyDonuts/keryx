from __future__ import annotations

import unittest
from datetime import date

from scripts.sources import parse_jobright_jobs, parse_markdown_jobs


class SourceParserTests(unittest.TestCase):
    def test_jobright_rows_preserve_jobs_and_repeated_companies(self) -> None:
        text = (
            "| Company | Job Title | Location | Work Model | Date Posted |\n"
            "|---|---|---|---|---|\n"
            "| **[Notion](https://notion.com)** | "
            "**[Software Engineer Intern (Summer 2027)](https://jobright.ai/jobs/info/"
            "abc123?utm_source=git)** "
            "| San Francisco, CA, United States | On Site | Aug 14 |\n"
            "| ↳ | **[Software Engineer Intern (Winter 2027)](https://jobright.ai/jobs/info/"
            "def456?utm_source=git)** "
            "| New York, NY, United States | Hybrid | Aug 13 |\n"
        )
        jobs = parse_jobright_jobs(
            text,
            source_id="jobright-swe-internships",
            source_label="Software Engineering",
            program="internship",
            cycle_hint=None,
            today=date(2026, 8, 14),
        )

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].company, "Notion")
        self.assertEqual(jobs[1].company, "Notion")
        self.assertEqual(jobs[0].external_id, "abc123")
        self.assertEqual(jobs[0].posted_at, "2026-08-14")
        self.assertEqual(jobs[1].posted_at, "2026-08-13")
        self.assertEqual(jobs[1].metadata["work_model"], "Hybrid")
        self.assertEqual(jobs[0].metadata["company_url"], "https://notion.com")
        self.assertEqual(jobs[1].metadata["company_url"], "https://notion.com")
        self.assertEqual(jobs[0].source_label, "Jobright · Software Engineering")
        self.assertEqual(
            jobs[0].url,
            "https://jobright.ai/jobs/info/abc123?utm_source=git",
        )

    def test_jobright_parser_rejects_non_jobright_title_links(self) -> None:
        text = (
            "| **[Example](https://example.com)** | "
            "**[Software Intern](https://jobs.example.com/123)** | "
            "Austin, TX | Remote | Aug 14 |\n"
        )
        jobs = parse_jobright_jobs(
            text,
            source_id="jobright-swe-internships",
            source_label="Software Engineering",
            program="internship",
            cycle_hint=None,
            today=date(2026, 8, 14),
        )
        self.assertEqual(jobs, ())

    def test_jobright_date_rolls_back_at_new_year(self) -> None:
        text = (
            "| **[Example](https://example.com)** | "
            "**[Software Intern](https://jobright.ai/jobs/info/abc123)** | "
            "Austin, TX | Remote | Dec 31 |\n"
        )
        jobs = parse_jobright_jobs(
            text,
            source_id="jobright-swe-internships",
            source_label="Software Engineering",
            program="internship",
            cycle_hint=None,
            today=date(2027, 1, 1),
        )
        self.assertEqual(jobs[0].posted_at, "2026-12-31")

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
