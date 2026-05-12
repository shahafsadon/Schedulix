from datetime import date, timedelta
from typing import Protocol


class ExamPeriodLike(Protocol):
    """Builds valid exam dates for an exam period."""
    start_date: date
    end_date: date
    excluded_dates: list[date]


class ExamDateHandler:
    """
    Builds the valid exam dates for one exam period.

    The class follows a small Domain Service style: it does not store state,
    and it has one responsibility - turning an exam period into a sorted list
    of dates that may be used for exams.
    """

    def get_valid_dates(self, exam_period: ExamPeriodLike) -> list[date]:
        """
        Return all dates inside the exam period except excluded dates.
        Dates are generated from start_date to end_date, including both edges.
        Excluded dates outside the period do not change the result.
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
        Generate sorted valid dates between start_date and end_date.
        Args:
            start_date: First possible exam date.
            end_date: Last possible exam date.
            excluded_dates: Dates that cannot be used for exams.
        Raises:
            ValueError: If start_date is after end_date.
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
