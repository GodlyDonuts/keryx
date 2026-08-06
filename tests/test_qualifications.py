from __future__ import annotations

import unittest

from scripts.models import Observation
from scripts.qualifications import (
    classify_academic_eligibility,
    extract_academic_eligibility,
)


def role(*, source: str = "ats:greenhouse:example", description: str = "") -> Observation:
    return Observation(
        source_id=source,
        source_label="Greenhouse direct" if source.startswith("ats:") else "Community",
        source_url="https://example.com/source",
        external_id="123",
        company="Example",
        title="Software Engineer Intern",
        location="Austin, TX",
        url="https://job-boards.greenhouse.io/example/jobs/123",
        program="internship",
        description=description,
    )


class QualificationTests(unittest.TestCase):
    def test_extracts_explicit_month_window(self) -> None:
        result = extract_academic_eligibility(
            "Candidates must have an expected graduation date between December 2026 and June 2027."
        )

        self.assertEqual(result["status"], "explicit-window")  # type: ignore[index]
        self.assertEqual(result["summary"], "Dec 2026–Jun 2027")  # type: ignore[index]
        self.assertEqual(result["graduation_start"], "2026-12")  # type: ignore[index]
        self.assertEqual(result["graduation_end"], "2027-06")  # type: ignore[index]
        self.assertEqual(result["requirement_level"], "required")  # type: ignore[index]

    def test_preserves_seasons_that_share_a_year(self) -> None:
        result = extract_academic_eligibility(
            "Applicants must be graduating in the spring of 2026 or summer of 2026."
        )

        self.assertEqual(result["status"], "explicit-window")  # type: ignore[index]
        self.assertEqual(result["summary"], "Spring–Summer 2026")  # type: ignore[index]
        self.assertEqual(result["graduation_years"], [2026])  # type: ignore[index]

    def test_preserves_three_seasons_with_one_shared_year(self) -> None:
        result = extract_academic_eligibility(
            "Candidates must be graduating in spring, summer, or fall of 2027."
        )

        self.assertEqual(result["status"], "explicit-window")  # type: ignore[index]
        self.assertEqual(result["summary"], "Spring–Fall 2027")  # type: ignore[index]

    def test_extracts_directional_graduation_bound(self) -> None:
        result = extract_academic_eligibility(
            "You must be graduating no earlier than May 2027 to qualify for this program."
        )

        self.assertEqual(result["status"], "explicit-lower-bound")  # type: ignore[index]
        self.assertEqual(result["summary"], "May 2027 or later")  # type: ignore[index]
        self.assertEqual(result["graduation_start"], "2027-05")  # type: ignore[index]

    def test_does_not_treat_program_year_as_start_of_graduation_window(self) -> None:
        result = extract_academic_eligibility(
            "The Summer 2027 program is designed for students with an expected graduation "
            "date of May 2028."
        )

        self.assertEqual(result["status"], "explicit-date")  # type: ignore[index]
        self.assertEqual(result["summary"], "Expected May 2028 graduation")  # type: ignore[index]
        self.assertEqual(result["graduation_start"], "2028-05")  # type: ignore[index]

    def test_extracts_enrollment_and_return_to_school_without_inventing_a_date(self) -> None:
        result = extract_academic_eligibility(
            "Applicants must be currently enrolled in a degree program and return to school "
            "after completing the internship."
        )

        self.assertEqual(result["status"], "student-status")  # type: ignore[index]
        self.assertTrue(result["currently_enrolled"])  # type: ignore[index]
        self.assertTrue(result["return_to_school"])  # type: ignore[index]
        self.assertEqual(result["currently_enrolled_level"], "required")  # type: ignore[index]
        self.assertEqual(result["return_to_school_level"], "required")  # type: ignore[index]
        self.assertNotIn("graduation_start", result or {})

    def test_detects_school_remaining_after_internship(self) -> None:
        result = extract_academic_eligibility(
            "Applicants must be enrolled and have at least one semester of school remaining "
            "after the internship."
        )

        self.assertTrue(result["return_to_school"])  # type: ignore[index]
        self.assertEqual(result["return_to_school_level"], "required")  # type: ignore[index]
        self.assertIn("semester of school remaining", result["return_to_school_evidence"])  # type: ignore[index]

    def test_evidence_always_contains_the_detected_condition(self) -> None:
        prefix = "qualification context " * 30
        result = extract_academic_eligibility(
            f"{prefix}Currently pursuing a bachelor's degree in computer science."
        )

        evidence = result["evidence"]  # type: ignore[index]
        self.assertLessEqual(len(evidence), 280)
        self.assertIn("Currently pursuing", evidence)
        self.assertTrue(evidence.startswith("…"))
        self.assertEqual(evidence, result["currently_enrolled_evidence"])  # type: ignore[index]

    def test_preferred_student_status_is_not_promoted_to_required(self) -> None:
        result = extract_academic_eligibility(
            "Preferred Qualifications. Currently pursuing a bachelor's degree in computer science."
        )

        self.assertEqual(result["currently_enrolled_level"], "preferred")  # type: ignore[index]
        self.assertNotEqual(result["currently_enrolled_level"], "required")  # type: ignore[index]

    def test_neutral_graduation_statement_remains_stated(self) -> None:
        result = extract_academic_eligibility("Expected graduation is May 2028.")

        self.assertEqual(result["requirement_level"], "stated")  # type: ignore[index]

    def test_minimum_qualification_heading_marks_condition_required(self) -> None:
        result = extract_academic_eligibility(
            "Minimum Qualifications. Currently enrolled in an accredited degree program."
        )

        self.assertEqual(result["currently_enrolled_level"], "required")  # type: ignore[index]

    def test_not_required_does_not_become_required(self) -> None:
        result = extract_academic_eligibility(
            "Current enrollment is preferred but not required for this opportunity."
        )

        self.assertEqual(result["currently_enrolled_level"], "preferred")  # type: ignore[index]

    def test_preference_for_degree_field_does_not_modify_graduation(self) -> None:
        result = extract_academic_eligibility(
            "Graduates in Winter 2026 or Spring 2027 with a bachelor's degree, "
            "ideally in Finance or Accounting."
        )

        self.assertEqual(result["requirement_level"], "stated")  # type: ignore[index]

    def test_preference_for_degree_level_does_not_modify_enrollment(self) -> None:
        result = extract_academic_eligibility(
            "Pursuing a Master's or PhD in Computer Science or a related field (PhD preferred)."
        )

        self.assertEqual(result["currently_enrolled_level"], "stated")  # type: ignore[index]

    def test_distinguishes_checked_text_from_unavailable_text(self) -> None:
        checked = classify_academic_eligibility(
            [role(description="Build reliable distributed systems with our engineering team.")]
        )
        unavailable = classify_academic_eligibility([role(description="")])

        self.assertEqual(checked["status"], "not-found")
        self.assertEqual(checked["confidence"], "direct-ats")
        self.assertEqual(unavailable["status"], "unavailable")
        self.assertEqual(unavailable["confidence"], "metadata-only")

    def test_direct_ats_requirement_wins_over_community_text(self) -> None:
        community = role(
            source="community",
            description="Applicants should graduate in 2026.",
        )
        direct = role(description="Expected graduation is May 2027.")

        result = classify_academic_eligibility([community, direct])

        self.assertEqual(result["summary"], "Expected May 2027 graduation")
        self.assertEqual(result["requirement_level"], "stated")
        self.assertEqual(result["source_id"], direct.source_id)


if __name__ == "__main__":
    unittest.main()
