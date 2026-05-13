from datetime import date, timedelta
from typing import Protocol


class ExamPeriodLike(Protocol):
    """Defines the fields needed for building valid exam dates."""
    start_date: date
    end_date: date
    excluded_dates: list[date]


class ExamDateHandler:
    """
    Builds the list of dates that can be used for exams.

    The class does not keep state. It receives an exam period or a date range
    and returns all dates that are inside the range and not blocked.
    """

    def get_valid_dates(self, exam_period: ExamPeriodLike) -> list[date]:
        """
        Return all valid dates for the given exam period.

        The start and end dates are included. Dates listed in excluded_dates are
        removed from the result.
        """
        return self.generate_dates(
            exam_period.start_date,
            exam_period.end_date,
            exam_period.excluded_dates,
        )

    def generate_dates(
            self,
            start_date: date,
            end_date: date,
            excluded_dates: list[date] | None = None,
    ) -> list[date]:
        """
        Generate all usable dates between start_date and end_date.

        Raises ValueError if the date range is invalid.
        """
        if start_date > end_date:
            raise ValueError("Exam period start date cannot be after end date.")
        blocked_dates = set(excluded_dates or [])
        valid_dates: list[date] = []
        current_date = start_date

        while current_date <= end_date:
            if current_date not in blocked_dates:
                valid_dates.append(current_date)
            current_date += timedelta(days=1)
        return valid_dates