import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from application.schedulixApp import SchedulixApp


class SchedulixAppTests(unittest.TestCase):
    """Tests for the full application flow."""
    def test_runs_full_flow_and_writes_output_file(self) -> None:
        """The app should read files, generate schedules, and write output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "exam_schedules.txt"
            result = SchedulixApp().run(
                courses_path=ROOT / "data" / "examples" / "CourseExample.txt",
                exam_periods_path=ROOT / "data" / "examples" / "DatesExample.txt",
                programs_path=ROOT / "data" / "examples" / "ProgramsExample.txt",
                output_path=output_path,
            )
            self.assertEqual(result.selected_program_count, 3)
            self.assertEqual(result.total_course_count, 3)
            self.assertEqual(result.relevant_course_count, 2)
            self.assertEqual(result.exam_period_count, 3)
            self.assertGreater(result.schedule_count, 0)
            self.assertTrue(output_path.exists())
            output_text = output_path.read_text(encoding="utf-8")
            self.assertIn("Schedulix Exam Schedules", output_text)
            self.assertIn("Schedule 1", output_text)
            self.assertIn("Semester: FALL", output_text)
            self.assertIn("Moed: Aleph", output_text)

if __name__ == "__main__":
    unittest.main()
