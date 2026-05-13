import re
from datetime import date, datetime, timedelta

from fileReader.baseFileReader import BaseFileReader
from models import ExamPeriod

# Separator used between exam period records.
SEPARATOR = "$$$$"

# Expected date format in all input files.
DATE_FORMAT = "%d-%m-%Y"

# Matches a regular date range line.
# Example:
#   29-01-2026, 11-03-2026
_DATE_RANGE_RE = re.compile(
    r"^(\d{2}-\d{2}-\d{4})\s*,\s*(\d{2}-\d{2}-\d{4})$"
)

# Matches excluded date lines.
# Supported formats:
#   - 31-01-2026 Shabat
#   - 02-03-2026, 04-03-2026 Purim
_EXCLUDED_RE = re.compile(
    r"^-\s+(\d{2}-\d{2}-\d{4})(?:\s*,\s*(\d{2}-\d{2}-\d{4}))?(?:\s+.+)?$"
)


def _parse_date(s: str) -> date:
    """Convert a DD-MM-YYYY string into a date object."""
    return datetime.strptime(s.strip(), DATE_FORMAT).date()


def _expand_date_range(start_date: date, end_date: date) -> list[date]:
    """
    Expand a date range into a list containing all dates in the range.
    """
    if start_date > end_date:
        raise ValueError("Date range start date cannot be after end date.")

    dates: list[date] = []
    current_date = start_date

    while current_date <= end_date:
        dates.append(current_date)
        current_date += timedelta(days=1)

    return dates


class ExamPeriodsFileReader(BaseFileReader[list[ExamPeriod]]):
    """
    Reads the exam periods input file and converts it into ExamPeriod objects.

    Each block describes:
    - Semester and moed
    - Allowed scheduling range
    - Excluded dates inside the range
    """

    def parse(self, content: str) -> list[ExamPeriod]:
        """
        Split the file into blocks and parse each exam period separately.
        """
        blocks = content.split(SEPARATOR)
        periods: list[ExamPeriod] = []

        for block in blocks:
            block = block.strip()

            # Skip the empty section before the first separator.
            if not block:
                continue

            periods.append(self._parse_block(block))

        return periods

    def _parse_block(self, block: str) -> ExamPeriod:
        """
        Parse a single exam period block.
        """
        # Remove empty lines while keeping the line content itself unchanged.
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]

        if len(lines) < 2:
            raise ValueError(
                f"Malformed exam period block — expected at least 2 lines "
                f"(header + date range):\n{block}"
            )

        # First line contains semester and moed.
        semester, moed = self._parse_header(lines[0])

        # Second line contains the scheduling range.
        start_date, end_date = self._parse_date_range(lines[1])

        # Remaining lines describe blocked dates.
        excluded: list[date] = []

        for ln in lines[2:]:
            excluded.extend(self._parse_excluded(ln))

        return ExamPeriod(
            semester=semester,
            moed=moed,
            start_date=start_date,
            end_date=end_date,
            excluded_dates=excluded,
        )

    @staticmethod
    def _parse_header(line: str) -> tuple[str, str]:
        """
        Parse the semester/moed header line.

        Example:
            FALL, Aleph
        """
        parts = [p.strip() for p in line.split(",")]

        if len(parts) != 2:
            raise ValueError(
                f"Malformed period header — expected 'SEMESTER, Moed': '{line}'"
            )

        return parts[0], parts[1]

    @staticmethod
    def _parse_date_range(line: str) -> tuple[date, date]:
        """
        Parse a scheduling range into start and end dates.
        """
        m = _DATE_RANGE_RE.match(line.strip())

        if not m:
            raise ValueError(
                f"Malformed date range — expected 'DD-MM-YYYY, DD-MM-YYYY': '{line}'"
            )

        start_date = _parse_date(m.group(1))
        end_date = _parse_date(m.group(2))

        if start_date > end_date:
            raise ValueError(
                f"Date range start date cannot be after end date: '{line}'"
            )

        return start_date, end_date

    @staticmethod
    def _parse_excluded(line: str) -> list[date]:
        """
        Parse one excluded-date line.

        A single date returns a list with one value.
        A date range returns all dates inside the range.
        """
        m = _EXCLUDED_RE.match(line.strip())

        if not m:
            raise ValueError(f"Malformed excluded-date line: '{line}'")

        start_date = _parse_date(m.group(1))

        # Group 2 exists only when the excluded line contains a range.
        if m.group(2):
            end_date = _parse_date(m.group(2))
            return _expand_date_range(start_date, end_date)

        return [start_date]