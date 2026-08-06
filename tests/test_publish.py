from __future__ import annotations

import csv
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path
from typing import Any

from scripts.publish import publish_public_artifacts


def _job(identifier: str, *, status: str = "open", url: str | None = None) -> dict[str, Any]:
    return {
        "id": identifier,
        "company": "Example & Partners",
        "title": "Software <Engineer> Intern",
        "location": "New York, NY",
        "program": "internship",
        "cycle": "summer-2027",
        "status": status,
        "posted_at": "2026-08-02",
        "first_seen": "2026-08-03",
        "first_seen_at": "2026-08-03T12:00:00Z",
        "last_changed": "2026-08-03",
        "last_changed_at": "2026-08-03T12:15:00Z",
        "url": url,
        "link_status": "ats-verified" if url else "unverified",
        "sources": [
            {"id": "ats:greenhouse:example", "label": "Example", "url": "https://example.com"},
            {"id": "community:old", "label": "Old source", "url": "https://example.org"},
        ],
        "current_source_ids": ["ats:greenhouse:example"],
        "historical_source_ids": ["community:old"],
        "previously_ats_observed": False,
        "academic_eligibility": {
            "status": "explicit-window",
            "summary": "May 2027–Dec 2028",
            "requirement_level": "required",
            "graduation_years": [2027, 2028],
        },
        "intelligence": {
            "text_status": "checked",
            "category": "software",
            "skills": ["Python", "React"],
            "compensation": {"summary": "$45–$60/hr"},
            "workplace": {"value": "hybrid"},
            "visa": {"status": "no-sponsorship"},
        },
    }


class PublishTests(unittest.TestCase):
    def test_builds_stable_public_artifacts_from_open_jobs(self) -> None:
        payload = {
            "schema_version": 3,
            "jobs": [
                _job("visible", url="https://boards.greenhouse.io/example/jobs/1"),
                _job("withheld"),
                _job("closed", status="closed", url="https://example.com/closed"),
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            static = root / "static"
            static.mkdir()
            (static / "index.html").write_text(
                "<!doctype html><title>Keryx</title>", encoding="utf-8"
            )
            output = root / "output"
            health = {
                "schema_version": 1,
                "generated_at": "2026-08-03T12:30:00Z",
                "sources": {
                    "ats:greenhouse:example": {
                        "source_id": "ats:greenhouse:example",
                        "outcome": "complete",
                    }
                },
            }
            publish_public_artifacts(output, payload, static_root=static, source_health=health)
            first = {
                path.relative_to(output): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }
            publish_public_artifacts(output, payload, static_root=static, source_health=health)
            second = {
                path.relative_to(output): path.read_bytes()
                for path in output.rglob("*")
                if path.is_file()
            }

            self.assertEqual(first, second)
            self.assertIn(Path("index.html"), first)
            api = json.loads((output / "api/jobs.json").read_text(encoding="utf-8"))
            self.assertEqual(api["count"], 2)
            self.assertEqual(api["schema_version"], 3)
            self.assertEqual(api["dataset_timestamp"], "2026-08-03T12:15:00Z")
            self.assertEqual({job["id"] for job in api["jobs"]}, {"visible", "withheld"})
            self.assertNotIn("closed", (output / "api/jobs.json").read_text(encoding="utf-8"))
            published_health = json.loads(
                (output / "api/source-health.json").read_text(encoding="utf-8")
            )
            self.assertEqual(published_health, health)

    def test_csv_never_reconstructs_a_withheld_link(self) -> None:
        payload = {"jobs": [_job("withheld")]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            publish_public_artifacts(output, payload)
            rows = list(csv.DictReader(StringIO((output / "opportunities.csv").read_text())))
        self.assertEqual(rows[0]["apply_url"], "")
        self.assertEqual(rows[0]["skills"], "Python; React")
        self.assertEqual(rows[0]["graduation_requirement_level"], "required")
        self.assertEqual(rows[0]["current_source_count"], "1")
        self.assertEqual(rows[0]["historical_source_count"], "1")

    def test_rss_is_valid_xml_and_only_includes_clickable_roles(self) -> None:
        payload = {
            "jobs": [
                _job("visible", url="https://boards.greenhouse.io/example/jobs/1?a=1&b=2"),
                _job("withheld"),
            ]
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            publish_public_artifacts(output, payload)
            root = ET.fromstring((output / "feed.xml").read_text(encoding="utf-8"))
        items = root.findall("./channel/item")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].findtext("guid"), "visible")
        self.assertEqual(
            items[0].findtext("link"),
            "https://boards.greenhouse.io/example/jobs/1?a=1&b=2",
        )

    def test_stats_report_coverage_without_applicant_scoring(self) -> None:
        payload = {"jobs": [_job("visible", url="https://example.com/jobs/1"), _job("hidden")]}
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            publish_public_artifacts(output, payload)
            stats = json.loads((output / "api/stats.json").read_text(encoding="utf-8"))
        self.assertEqual(stats["open_total"], 2)
        self.assertEqual(stats["coverage"]["text_checked"], 2)
        self.assertEqual(stats["coverage"]["clickable_link"], 1)
        self.assertEqual(stats["visa"]["no-sponsorship"], 2)
        self.assertEqual(stats["source_observations"], {"ats": 2})


if __name__ == "__main__":
    unittest.main()
