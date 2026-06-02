"""Presenter for triggering schedule generation (SCRUM-125).

This presenter sits between the "Schedule" action in the GUI and the
SchedulingService. Following the MVP pattern it contains no customTkinter code:
the View calls generate() when the user clicks the button, and the presenter
returns a small, display-ready result (or an error message) for the View to show.

The presenter is intentionally thin. The real work — filtering courses and
generating exam systems from the cached data — lives in SchedulingService, which
reuses the Version 1.0 engine. Keeping that logic out of the presenter means it
can be swapped or run on a background thread later (SCRUM-115) without touching
this class.
"""
from __future__ import annotations

from dataclasses import dataclass

from application.cache_manager import CacheManager
from scheduling.schedulingService import SchedulingService


@dataclass(frozen=True)
class GenerationResult:
    """Display-ready outcome of a generation attempt.

    The View shows `message` directly. On success `schedule_count` drives the
    "X systems generated" text and whether navigation to the output screen is
    offered; on failure `success` is False and `message` holds the reason.
    """

    success: bool
    message: str
    schedule_count: int = 0


class SchedulingPresenter:
    """Drives the schedule-generation step of the wizard."""

    def __init__(
        self,
        cache: CacheManager,
        service: SchedulingService | None = None,
    ) -> None:
        """Create the presenter with the shared cache and a scheduling service.

        Args:
            cache: the single application CacheManager holding the loaded data
                and receiving the generated schedules (Dependency Injection).
            service: the scheduling service to run; a default is created when
                none is supplied, while tests can inject a fake.
        """
        self._cache = cache
        # Default to the real service so application code stays simple.
        self._service = service or SchedulingService()

    def generate(self) -> GenerationResult:
        """Run scheduling on the cached data and report a display-ready result.

        Translates the service outcome into user-facing text. Missing inputs
        (raised as ValueError by the service) become a friendly failure result
        rather than an exception, so the View can simply show the message.
        """
        try:
            outcome = self._service.run(self._cache)
        except ValueError as error:
            # Expected, user-facing problem (e.g. a wizard step was skipped):
            # the message is already meaningful, so show it as-is.
            return GenerationResult(success=False, message=str(error))
        except Exception as error:  # noqa: BLE001 - last-resort UI guard
            # Unexpected failure (e.g. the generator running out of memory on a
            # huge dataset). We must not let it crash the GUI, so we surface a
            # generic message while still including the error type for debugging.
            # A proper background-thread error channel will arrive with SCRUM-115.
            return GenerationResult(
                success=False,
                message=f"Schedule generation failed unexpectedly: "
                        f"{type(error).__name__}.",
            )

        # A valid run that yields zero systems is not an error, but the reason
        # matters for the advice we give the user:
        if outcome.schedule_count == 0:
            if outcome.relevant_course_count == 0:
                # The selected programs simply have no Exam courses to schedule;
                # excluding fewer dates would not help here.
                message = (
                    "No exam courses found for the selected programs. "
                    "Try selecting different programs."
                )
            else:
                # There are courses, but no conflict-free arrangement fits the
                # available dates, so suggest loosening the date constraints.
                message = (
                    "No valid exam systems could be generated for the current "
                    "selection. Try excluding fewer dates or changing programs."
                )
            return GenerationResult(
                success=True,
                message=message,
                schedule_count=0,
            )

        return GenerationResult(
            success=True,
            message=f"{outcome.schedule_count} exam system(s) generated.",
            schedule_count=outcome.schedule_count,
        )