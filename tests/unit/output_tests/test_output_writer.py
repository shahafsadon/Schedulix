import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from models import Course, ProgramEnrollment
from output.outputWriter import OutputWriter
from ranking_settings import (
    MISSING_METRIC_VALUE,
    RankedExamSystem,
    RankingCriterion,
    RankingPreference,
    RankingSettings,
    ScheduleMetrics,
)
from scheduling.examConflictDetector import ScheduledExam
from scheduling.examScheduleGenerator import ExamSchedule, ExamSystem


def make_exam(course_name: str, course_number: str, exam_date: date) -> ScheduledExam:
    """Create a scheduled exam for output writer tests."""
    course = Course(
        name=course_name,
        course_number=course_number,
        instructor="Test Instructor",
        programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )
    return ScheduledExam(course=course, exam_date=exam_date)


class OutputWriterTests(unittest.TestCase):
    """Tests for writing readable schedule output files."""

    def test_formats_schedule_with_semester_moed_and_sorted_exams(self) -> None:
        """The text should follow the required readable output structure."""
        schedule = ExamSystem(
            period_schedules=[
                ExamSchedule(
                    semester="FALL",
                    moed="Aleph",
                    scheduled_exams=[
                        make_exam("Calculus 1", "83112", date(2026, 2, 1)),
                        make_exam("Physics 1", "83102", date(2026, 1, 29)),
                    ],
                ),
                ExamSchedule(
                    semester="FALL",
                    moed="Bet",
                    scheduled_exams=[
                        make_exam("Calculus 1", "83112", date(2026, 4, 10)),
                    ],
                ),
            ],
        )

        result = OutputWriter().format_schedules([schedule])

        self.assertIn("Schedulix Exam Schedules", result)
        self.assertIn("Schedule 1", result)
        self.assertIn("Semester: FALL", result)
        self.assertIn("Moed: Aleph", result)
        self.assertIn("Moed: Bet", result)
        self.assertLess(
            result.index("29-01-2026 | Physics 1 | Test Instructor"),
            result.index("01-02-2026 | Calculus 1 | Test Instructor"),
        )

    def test_writes_output_file_to_given_path(self) -> None:
        """The writer should create the output file and its directory."""
        schedule = ExamSystem(
            period_schedules=[
                ExamSchedule(
                    semester="SPRI",
                    moed="Bet",
                    scheduled_exams=[
                        make_exam("Algorithms 1", "83120", date(2026, 7, 3)),
                    ],
                ),
            ],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "data" / "outputs" / "exam_schedules.txt"

            created_path = OutputWriter().write([schedule], output_path)

            self.assertEqual(created_path, output_path)
            self.assertTrue(output_path.exists())
            self.assertIn("Semester: SPRI", output_path.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------
    # write_ranked_with_count (SCRUM-166)
    # ------------------------------------------------------------------

    def test_ranked_output_preserves_given_order(self) -> None:
        """Ranked schedules are written in list order, not re-sorted.

        The second schedule (key=2) is placed first in the input list to
        simulate a ranking order different from creation order; the output
        must show "Schedule 1" containing that second schedule's content.
        """
        first_schedule = ExamSystem(
            period_schedules=[
                ExamSchedule(
                    semester="FALL",
                    moed="Aleph",
                    scheduled_exams=[
                        make_exam("Physics 1", "83102", date(2026, 1, 29)),
                    ],
                ),
            ],
        )
        second_schedule = ExamSystem(
            period_schedules=[
                ExamSchedule(
                    semester="FALL",
                    moed="Aleph",
                    scheduled_exams=[
                        make_exam("Calculus 1", "83112", date(2026, 2, 1)),
                    ],
                ),
            ],
        )

        ranked = [
            RankedExamSystem(
                exam_system=second_schedule,
                metrics=ScheduleMetrics(
                    schedule_id=2,
                    min_mandatory_gap=5,
                    average_all_gap=5.0,
                    elective_collision_count=0,
                    mandatory_span=0,
                    max_exams_per_day=1,
                ),
                key=2,
            ),
            RankedExamSystem(
                exam_system=first_schedule,
                metrics=ScheduleMetrics(
                    schedule_id=1,
                    min_mandatory_gap=3,
                    average_all_gap=3.0,
                    elective_collision_count=0,
                    mandatory_span=0,
                    max_exams_per_day=1,
                ),
                key=1,
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "ranked.txt"

            path, count = OutputWriter().write_ranked_with_count(
                ranked,
                output_path,
            )

            self.assertEqual(count, 2)
            text = path.read_text(encoding="utf-8")

        # "Schedule 1" in the output must be the second_schedule (Calculus),
        # since ranked[0] is second_schedule.
        schedule_1_index = text.index("Schedule 1")
        calculus_index = text.index("Calculus 1")
        physics_index = text.index("Physics 1")
        self.assertLess(schedule_1_index, calculus_index)
        self.assertLess(calculus_index, physics_index)

    def test_ranked_output_includes_metrics_line_with_n_a_for_missing(self) -> None:
        """Each schedule section includes a Metrics: line; missing values
        (MISSING_METRIC_VALUE == -1) are shown as 'n/a'."""
        schedule = ExamSystem(
            period_schedules=[
                ExamSchedule(
                    semester="FALL",
                    moed="Aleph",
                    scheduled_exams=[
                        make_exam("Physics 1", "83102", date(2026, 1, 29)),
                    ],
                ),
            ],
        )
        ranked = [
            RankedExamSystem(
                exam_system=schedule,
                metrics=ScheduleMetrics(
                    schedule_id=1,
                    min_mandatory_gap=MISSING_METRIC_VALUE,
                    average_all_gap=MISSING_METRIC_VALUE,
                    elective_collision_count=0,
                    mandatory_span=0,
                    max_exams_per_day=1,
                ),
                key=1,
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "ranked.txt"

            OutputWriter().write_ranked_with_count(ranked, output_path)
            text = output_path.read_text(encoding="utf-8")

        self.assertIn("Metrics:", text)
        self.assertIn("min_gap=n/a", text)
        self.assertIn("avg_gap=n/a", text)
        self.assertIn("elective_collisions=0", text)
        self.assertIn("max_per_day=1", text)

    def test_ranked_output_without_settings_has_no_settings_line(self) -> None:
        """Omitting constraint_settings and ranking_settings omits the
        Settings: header line entirely (pre-Part-3 header shape)."""
        schedule = ExamSystem(
            period_schedules=[
                ExamSchedule(
                    semester="FALL",
                    moed="Aleph",
                    scheduled_exams=[
                        make_exam("Physics 1", "83102", date(2026, 1, 29)),
                    ],
                ),
            ],
        )
        ranked = [
            RankedExamSystem(
                exam_system=schedule,
                metrics=ScheduleMetrics(
                    schedule_id=1,
                    min_mandatory_gap=0,
                    average_all_gap=0.0,
                    elective_collision_count=0,
                    mandatory_span=0,
                    max_exams_per_day=1,
                ),
                key=1,
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "ranked.txt"

            OutputWriter().write_ranked_with_count(ranked, output_path)
            text = output_path.read_text(encoding="utf-8")

        self.assertNotIn("Settings:", text)
        self.assertIn("Valid systems: 1", text)

    def test_ranked_output_with_settings_summarizes_enabled_constraints_and_ranking(
        self,
    ) -> None:
        """When constraint/ranking settings are supplied, the header
        summarizes only enabled constraints and the active ranking order."""
        schedule = ExamSystem(
            period_schedules=[
                ExamSchedule(
                    semester="FALL",
                    moed="Aleph",
                    scheduled_exams=[
                        make_exam("Physics 1", "83102", date(2026, 1, 29)),
                    ],
                ),
            ],
        )
        ranked = [
            RankedExamSystem(
                exam_system=schedule,
                metrics=ScheduleMetrics(
                    schedule_id=1,
                    min_mandatory_gap=3,
                    average_all_gap=3.0,
                    elective_collision_count=0,
                    mandatory_span=0,
                    max_exams_per_day=1,
                ),
                key=1,
            ),
        ]

        constraints = SchedulingConstraintSettings.default_configuration()
        constraints.constraints[ThresholdConstraintType.mandatory_gap_days] = (
            ThresholdConstraintSetting(enabled=True, k=3)
        )
        ranking = RankingSettings(
            priority_list=[
                RankingPreference(criterion=RankingCriterion.min_mandatory_gap),
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "ranked.txt"

            OutputWriter().write_ranked_with_count(
                ranked,
                output_path,
                constraint_settings=constraints,
                ranking_settings=ranking,
            )
            text = output_path.read_text(encoding="utf-8")

        self.assertIn("Settings:", text)
        self.assertIn("mandatory_gap_days=3", text)
        self.assertIn("min_mandatory_gap desc", text)
        # Disabled constraints must not appear in the summary.
        self.assertNotIn("any_course_gap_days", text)

    def test_ranked_output_with_no_active_settings_shows_none_message(self) -> None:
        """Passing default (all-disabled / empty) settings shows the
        explicit 'none' message rather than an empty Settings: line."""
        schedule = ExamSystem(
            period_schedules=[
                ExamSchedule(
                    semester="FALL",
                    moed="Aleph",
                    scheduled_exams=[
                        make_exam("Physics 1", "83102", date(2026, 1, 29)),
                    ],
                ),
            ],
        )
        ranked = [
            RankedExamSystem(
                exam_system=schedule,
                metrics=ScheduleMetrics(
                    schedule_id=1,
                    min_mandatory_gap=3,
                    average_all_gap=3.0,
                    elective_collision_count=0,
                    mandatory_span=0,
                    max_exams_per_day=1,
                ),
                key=1,
            ),
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "ranked.txt"

            OutputWriter().write_ranked_with_count(
                ranked,
                output_path,
                constraint_settings=SchedulingConstraintSettings.default_configuration(),
                ranking_settings=RankingSettings(priority_list=[]),
            )
            text = output_path.read_text(encoding="utf-8")

        self.assertIn(
            "Settings: none (all constraints disabled, no ranking)",
            text,
        )


if __name__ == "__main__":
    unittest.main()
