import re
from datetime import date, datetime, timedelta

from fileReader.baseFileReader import BaseFileReader
from models import ExamPeriod

# Records in the dates file use the same separator convention as the courses file
SEPARATOR = "$$$$"

# All dates in the file follow DD-MM-YYYY — we keep this in one place
# so if the format ever changes, there's exactly one line to update
DATE_FORMAT = "%d-%m-%Y"

# Matches the period's date-range line, e.g.: "29-01-2026, 11-03-2026"
# We anchor with ^ and $ to avoid accidentally matching an excluded-date range.
_DATE_RANGE_RE = re.compile(
    r"^(\d{2}-\d{2}-\d{4})\s*,\s*(\d{2}-\d{2}-\d{4})$"
)

# Matches an excluded-date line. Two forms are supported:
#   Single date:  "- 31-01-2026 Shabat"        → captures group 1 only
#   Date range:   "- 02-03-2026, 04-03-2026 Purim" → captures groups 1 and 2
# The trailing label (e.g. "Shabat", "Purim") is optional and ignored —
# it's there for human readability in the file, not for the scheduler.
_EXCLUDED_RE = re.compile(
    r"^-\s+(\d{2}-\d{2}-\d{4})(?:\s*,\s*(\d{2}-\d{2}-\d{4}))?(?:\s+.+)?$"
)


def _parse_date(s: str) -> date:
    """Convert a 'DD-MM-YYYY' string to a date object."""
    return datetime.strptime(s.strip(), DATE_FORMAT).date()


def _expand_date_range(start_date: date, end_date: date) -> list[date]:
    """
    Return every date in a date range, including both edges.

    Excluded dates in the input file may be written as a range. The scheduler
    needs every blocked day, not only the first and last day, so the reader
    expands the range while parsing.
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
    Reads the exam periods input file and returns a list of ExamPeriod objects.

    The file uses $$$$ as a record separator. Each record looks like this:

        $$$$
        FALL, Aleph
        29-01-2026, 11-03-2026
        - 31-01-2026 Shabat
        - 02-03-2026, 04-03-2026  Purim

    Line structure within a record:
        1. Semester and moed:   "FALL, Aleph" or "FALL,Bet" (spacing is flexible)
        2. Date range:          "DD-MM-YYYY, DD-MM-YYYY"
        3..N. Excluded dates:   "- DD-MM-YYYY [optional label]"
                             or "- DD-MM-YYYY, DD-MM-YYYY [optional label]" for ranges

    On excluded date ranges: the full range is expanded into separate dates
    in `excluded_dates`, so later scheduling logic can remove blocked dates
    with a simple membership check.
    """

    def parse(self, content: str) -> list[ExamPeriod]:
        """Split the file into records and parse each one."""
        blocks = content.split(SEPARATOR)
        periods: list[ExamPeriod] = []

        for block in blocks:
            block = block.strip()
            if not block:
                # Discard the empty fragment before the first $$$$ marker
                continue
            periods.append(self._parse_block(block))

        return periods

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_block(self, block: str) -> ExamPeriod:
        """
        Parse a single exam period record (text between two $$$$ markers).

        We keep trailing whitespace on lines (via rstrip, not strip) because
        we want to preserve any spaces that are part of a date line, but we
        still need to skip lines that are entirely blank.
        """
        lines = [ln.rstrip() for ln in block.splitlines() if ln.strip()]

        if len(lines) < 2:
            raise ValueError(
                f"Malformed exam period block — expected at least 2 lines "
                f"(header + date range):\n{block}"
            )

        # Line 0 is always the "SEMESTER, Moed" header
        semester, moed = self._parse_header(lines[0])

        # Line 1 is always the start/end date range
        start_date, end_date = self._parse_date_range(lines[1])

        # All remaining lines are excluded dates (could be zero if no days are blocked)
        excluded: list[date] = []
        for ln in lines[2:]:
            # _parse_excluded returns a list because a single line can expand
            # to all blocked dates when it's written as a range (e.g. Purim)
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
        Parse "FALL, Aleph" or "FALL,Bet" into ("FALL", "Aleph") / ("FALL", "Bet").

        We strip each part individually so the format is forgiving of spacing
        around the comma — both "FALL, Aleph" and "FALL,Aleph" are valid.
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
        Parse "29-01-2026, 11-03-2026" into two date objects.

        Using a regex here (rather than a simple split) lets us validate
        the exact format and catch typos like missing leading zeros.
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
        Parse one excluded-date line into a list of dates.

        Returns a list (not a single date) because a range line like
        "- 02-03-2026, 04-03-2026 Purim" produces every date in that range.
        Single-date lines like "- 31-01-2026 Shabat" produce a list of one.

        The optional human-readable label at the end (Shabat, Purim, etc.)
        is matched by the regex but intentionally thrown away.
        """
        m = _EXCLUDED_RE.match(line.strip())
        if not m:
            raise ValueError(f"Malformed excluded-date line: '{line}'")

        start_date = _parse_date(m.group(1))

        # Group 2 is only present when the line is a date range
        if m.group(2):
            end_date = _parse_date(m.group(2))
            return _expand_date_range(start_date, end_date)

        return [start_date]
