import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from fileReader.fileTypeReaders.examPeriodsReader import ExamPeriodsFileReader


class ExamPeriodsFileReaderTests(unittest.TestCase):
    """Unit tests for exam periods file parsing."""

    def test_reads_valid_exam_period(self) -> None:
        """A valid exam period should be parsed correctly."""
        content = """$$$$
FALL, Aleph
29-01-2026, 11-03-2026
- 31-01-2026 Shabat
- 02-03-2026, 04-03-2026 Purim
"""

        periods = ExamPeriodsFileReader().parse(content)

        self.assertEqual(len(periods), 1)
        self.assertEqual(periods[0].semester, "FALL")
        self.assertEqual(periods[0].moed, "Aleph")
        self.assertEqual(periods[0].start_date, date(2026, 1, 29))
        self.assertEqual(periods[0].end_date, date(2026, 3, 11))

    def test_expands_excluded_date_ranges(self) -> None:
        """Excluded date ranges should expand into all dates in the range."""
        content = """$$$$
FALL, Aleph
01-03-2026, 05-03-2026
- 02-03-2026, 04-03-2026 Purim
"""

        periods = ExamPeriodsFileReader().parse(content)

        self.assertEqual(
            periods[0].excluded_dates,
            [
                date(2026, 3, 2),
                date(2026, 3, 3),
                date(2026, 3, 4),
            ],
        )

    def test_accepts_excluded_dates_without_dash(self) -> None:
        """The appendix format does not require a leading dash."""
        content = """$$$$
FALL, Aleph
01-03-2026, 05-03-2026
02-03-2026 Maintenance
03-03-2026, 04-03-2026 Purim
"""

        periods = ExamPeriodsFileReader().parse(content)

        self.assertEqual(
            periods[0].excluded_dates,
            [
                date(2026, 3, 2),
                date(2026, 3, 3),
                date(2026, 3, 4),
            ],
        )

    def test_rejects_invalid_date_range(self) -> None:
        """Start date cannot be after end date."""
        content = """$$$$
FALL, Aleph
05-03-2026, 01-03-2026
"""

        with self.assertRaises(ValueError):
            ExamPeriodsFileReader().parse(content)

    def test_rejects_malformed_excluded_line(self) -> None:
        """Malformed excluded-date lines should raise ValueError."""
        content = """$$$$
FALL, Aleph
01-03-2026, 05-03-2026
Blocked date
"""

        with self.assertRaises(ValueError):
            ExamPeriodsFileReader().parse(content)

    def test_rejects_invalid_semester(self) -> None:
        """Semester must be FALL, SPRI, or SUMM."""
        content = """$$$$
WINTER, Aleph
01-03-2026, 05-03-2026
"""

        with self.assertRaises(ValueError):
            ExamPeriodsFileReader().parse(content)

    def test_rejects_invalid_moed(self) -> None:
        """Moed must be Aleph, Bet, or Gimel."""
        content = """$$$$
FALL, Dalet
01-03-2026, 05-03-2026
"""

        with self.assertRaises(ValueError):
            ExamPeriodsFileReader().parse(content)


if __name__ == "__main__":
    unittest.main()
