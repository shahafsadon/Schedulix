import re
from datetime import date, datetime, timedelta

from fileReader.baseFileReader import BaseFileReader
from models import ExamPeriod


SEPARATOR = "$$$$"
DATE_FORMAT = "%d-%m-%Y"

VALID_SEMESTERS = {
    "FALL",
    "SPRI",
    "SUMM",
}

VALID_MOEDIM = {
    "Aleph",
    "Bet",
    "Gimel",
}

_DATE_RANGE_RE = re.compile(
    r"^(\d{2}-\d{2}-\d{4})\s*,\s*(\d{2}-\d{2}-\d{4})$"
)

_EXCLUDED_RE = re.compile(
    r"^(?:-\s*)?"
    r"(\d{2}-\d{2}-\d{4})"
    r"(?:\s*,\s*(\d{2}-\d{2}-\d{4}))?"
    r"(?:\s+.+)?$"
)


def _parse_date(
    text: str,
) -> date:
    """Parse one DD-MM-YYYY date."""
    return datetime.strptime(
        text.strip(),
        DATE_FORMAT,
    ).date()


def _expand_date_range(
    start_date: date,
    end_date: date,
) -> list[date]:
    """Return every date in an inclusive range."""
    if start_date > end_date:
        raise ValueError(
            "Date range start date cannot be after end date."
        )

    result: list[date] = []
    current = start_date

    while current <= end_date:
        result.append(current)
        current += timedelta(days=1)

    return result


class ExamPeriodsFileReader(BaseFileReader[list[ExamPeriod]]):
    """Parses exam-period records and validates logical edge cases."""

    def parse(
        self,
        content: str,
    ) -> list[ExamPeriod]:
        if not content.strip():
            raise ValueError(
                "Exam-periods file is empty."
            )

        if not content.lstrip().startswith(SEPARATOR):
            raise ValueError(
                "Exam-periods file must start each record with '$$$$'."
            )

        periods: list[ExamPeriod] = []
        seen_periods: set[tuple[str, str]] = set()

        for block in content.split(SEPARATOR):
            if not block.strip():
                continue

            period = self._parse_block(block)

            key = (
                period.semester,
                period.moed,
            )

            if key in seen_periods:
                raise ValueError(
                    "Duplicate exam period for semester "
                    f"'{period.semester}' and moed '{period.moed}'."
                )

            seen_periods.add(key)
            periods.append(period)

        if not periods:
            raise ValueError(
                "Exam-periods file does not contain any records."
            )

        return periods

    def _parse_block(
        self,
        block: str,
    ) -> ExamPeriod:
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip()
        ]

        if len(lines) < 2:
            raise ValueError(
                "Malformed exam-period block - expected header "
                f"and date range:\n{block}"
            )

        semester, moed = self._parse_header(
            lines[0]
        )

        start_date, end_date = self._parse_date_range(
            lines[1]
        )

        excluded: set[date] = set()

        for line in lines[2:]:
            for blocked_date in self._parse_excluded(line):
                if not start_date <= blocked_date <= end_date:
                    raise ValueError(
                        f"Excluded date "
                        f"'{blocked_date.strftime(DATE_FORMAT)}' "
                        "is outside its exam-period range."
                    )

                excluded.add(blocked_date)

        return ExamPeriod(
            semester=semester,
            moed=moed,
            start_date=start_date,
            end_date=end_date,
            excluded_dates=sorted(excluded),
        )

    @staticmethod
    def _parse_header(
        line: str,
    ) -> tuple[str, str]:
        parts = [
            part.strip()
            for part in line.split(",")
        ]

        if len(parts) != 2:
            raise ValueError(
                f"Malformed period header: '{line}'"
            )

        semester = parts[0]
        moed = parts[1]

        if semester not in VALID_SEMESTERS:
            raise ValueError(
                f"Invalid semester: '{semester}'"
            )

        if moed not in VALID_MOEDIM:
            raise ValueError(
                f"Invalid moed: '{moed}'"
            )

        return semester, moed

    @staticmethod
    def _parse_date_range(
        line: str,
    ) -> tuple[date, date]:
        match = _DATE_RANGE_RE.match(
            line.strip()
        )

        if not match:
            raise ValueError(
                f"Malformed date range: '{line}'"
            )

        start_date = _parse_date(
            match.group(1)
        )

        end_date = _parse_date(
            match.group(2)
        )

        # Appendix A explicitly requires Start Date < End Date.
        if start_date >= end_date:
            raise ValueError(
                "Exam-period start date must be before end date: "
                f"'{line}'"
            )

        return start_date, end_date

    @staticmethod
    def _parse_excluded(
        line: str,
    ) -> list[date]:
        match = _EXCLUDED_RE.match(
            line.strip()
        )

        if not match:
            raise ValueError(
                f"Malformed excluded-date line: '{line}'"
            )

        start_date = _parse_date(
            match.group(1)
        )

        end_text = match.group(2)

        if end_text is None:
            return [start_date]

        end_date = _parse_date(
            end_text
        )

        if end_date < start_date:
            raise ValueError(
                f"Excluded date range is backwards: '{line}'"
            )

        return _expand_date_range(
            start_date,
            end_date,
        )