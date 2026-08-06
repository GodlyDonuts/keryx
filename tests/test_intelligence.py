from __future__ import annotations

import unittest

from scripts.intelligence import (
    build_job_intelligence,
    classify_category,
    classify_visa,
    classify_workplace,
    extract_compensation,
    extract_skills,
    visa_compatibility_value,
)
from scripts.models import Observation


def observation(
    *,
    source_id: str = "ats:greenhouse:example",
    description: str = "",
    sponsorship: str | None = None,
    metadata: dict[str, object] | None = None,
) -> Observation:
    return Observation(
        source_id=source_id,
        source_label="Greenhouse direct" if source_id.startswith("ats:") else "Public index",
        source_url="https://example.com/source",
        external_id="123",
        company="Example",
        title="Machine Learning Software Engineer Intern",
        location="New York, NY",
        url="https://job-boards.greenhouse.io/example/jobs/123",
        program="internship",
        description=description,
        sponsorship=sponsorship,
        metadata=metadata or {},
    )


class IntelligenceTests(unittest.TestCase):
    def test_skills_are_bounded_ranked_and_avoid_ordinary_word_collisions(self) -> None:
        skills = extract_skills(
            "Goals include reducing rust and reacting quickly. Use CUDA, PyTorch, Python, and C++.",
            title="C++ / CUDA Intern",
        )

        self.assertEqual(skills[:2], ["C++", "CUDA"])
        self.assertIn("Python", skills)
        self.assertIn("PyTorch", skills)
        self.assertNotIn("Go", skills)
        self.assertNotIn("Rust", skills)
        self.assertNotIn("React", skills)

    def test_title_drives_category_before_broad_description_terms(self) -> None:
        self.assertEqual(
            classify_category(
                "Quantitative Developer Intern",
                "Build software and machine learning infrastructure.",
            ),
            "quant",
        )
        self.assertEqual(classify_category("Firmware Engineering Intern"), "hardware")

    def test_compensation_requires_explicit_plausible_usd_period(self) -> None:
        hourly = extract_compensation("The pay range is $42.50 to $58 per hour.")
        between = extract_compensation("Pay is expected to be between $45 and $65/hour.")
        annual = extract_compensation("Annual compensation is $120,000–$150,000 per year.")

        self.assertEqual(hourly["summary"], "$42.5–$58/hr")  # type: ignore[index]
        self.assertEqual(hourly["period"], "hour")  # type: ignore[index]
        self.assertEqual(between["summary"], "$45–$65/hr")  # type: ignore[index]
        self.assertEqual(annual["summary"], "$120k–$150k/yr")  # type: ignore[index]
        self.assertIsNone(extract_compensation("A $5 lunch credit is provided."))

    def test_visa_classifier_uses_strictest_statement_and_retains_evidence(self) -> None:
        citizenship = classify_visa(
            "We can sponsor some applicants. U.S. citizenship is required for this role."
        )
        no_sponsorship = classify_visa(
            "Visa sponsorship is available elsewhere, but we will not provide sponsorship "
            "for this position."
        )

        self.assertEqual(citizenship["status"], "citizenship-required")
        self.assertIn("citizenship", citizenship["evidence"].casefold())
        self.assertEqual(no_sponsorship["status"], "no-sponsorship")

    def test_workplace_does_not_treat_remote_sensing_as_remote_work(self) -> None:
        self.assertEqual(
            classify_workplace("Remote Sensing Intern", "Pasadena, CA")["value"],
            "unspecified",
        )
        self.assertEqual(
            classify_workplace("Software Intern", "Remote, United States")["value"],
            "remote",
        )

    def test_direct_text_wins_and_public_metadata_fills_remaining_fields(self) -> None:
        direct = observation(
            description=(
                "Build CUDA and PyTorch systems. Compensation is $45-$60/hr. "
                "We cannot sponsor work visas for this role. This is a hybrid position."
            )
        )
        public = observation(
            source_id="intern-engine",
            sponsorship="offers",
            metadata={
                "category": "Data & ML/AI",
                "skills": ["Python", "TensorFlow"],
                "remote": True,
                "h1b_approvals": 31,
                "h1b_window": "FY2022–FY2023",
            },
        )

        result = build_job_intelligence([direct, public], checked_at="2026-08-03")

        self.assertEqual(result["text_status"], "checked")
        self.assertEqual(result["visa"]["status"], "no-sponsorship")
        self.assertEqual(result["workplace"]["value"], "hybrid")
        self.assertEqual(result["compensation"]["summary"], "$45–$60/hr")
        self.assertIn("TensorFlow", result["skills"])
        self.assertEqual(result["h1b_history"]["approvals"], 31)
        self.assertEqual(visa_compatibility_value(result), "no-sponsorship")

    def test_metadata_only_classification_is_visibly_lower_confidence(self) -> None:
        public = observation(
            source_id="intern-engine",
            sponsorship="offers",
            metadata={"category": "Software", "skills": ["Python"], "remote": True},
        )

        result = build_job_intelligence([public], checked_at="2026-08-03")

        self.assertEqual(result["text_status"], "metadata-only")
        self.assertNotIn("checked_at", result)
        self.assertEqual(result["visa"]["status"], "sponsorship-available")
        self.assertEqual(result["visa"]["confidence"], "source-metadata")


if __name__ == "__main__":
    unittest.main()
