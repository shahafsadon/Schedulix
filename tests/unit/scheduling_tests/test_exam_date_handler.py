import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
FILE_READER = SRC / "fileReader"

sys.path.insert(0, str(SRC))
sys.path.insert(0, str(FILE_READER))

from models import ExamPeriod
from scheduling.examDateHandler import ExamDateHandler
from fileReader.fileTypeReaders.examPeriodsReader import ExamPeriodsFileReader


class ExamDateHandlerTests(unittest.TestCase):
    """Tests for valid exam date generation."""

    def test_generates_sorted_dates_and_removes_excluded_dates(self) -> None:
        """Valid dates should include the period edges and skip blocked dates."""
        period = ExamPeriod(
            semester="FALL",
            moed="Aleph",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 5),
            excluded_dates=[date(2026, 1, 3), date(2025, 12, 31)],
        )

        result = ExamDateHandler().get_valid_dates(period)

        self.assertEqual(
            result,
            [
                date(2026, 1, 1),
                date(2026, 1, 2),
                date(2026, 1, 4),
                date(2026, 1, 5),
            ],
        )

    def test_rejects_invalid_date_range(self) -> None:
        """A period cannot start after it ends."""
        with self.assertRaises(ValueError):
            ExamDateHandler().generate_dates(
                start_date=date(2026, 1, 5),
                end_date=date(2026, 1, 1),
            )


class ExamPeriodsReaderExcludedDatesTests(unittest.TestCase):
    """Tests for parsing excluded dates before scheduling uses them."""

    def test_expands_excluded_date_ranges(self) -> None:
        """A blocked range should become every blocked day in that range."""
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


if __name__ == "__main__":
    unittest.main()
