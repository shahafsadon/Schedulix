"""
test_async_operations.py
~~~~~~~~~~~~~~~~~~~~~~~~
Isolated unit tests for the async background operation infrastructure
(SCRUM-115).

Strategy
--------
* ``threading.Thread`` is **mocked** throughout so tests run in milliseconds
  without spawning real OS threads.  The mock immediately calls the target
  function (i.e. the worker) so callback assertions work without sleeps.
* No customtkinter or GUI dependencies — fully headless.
* The test for real-thread callback execution uses a ``threading.Event`` as a
  lightweight synchronisation primitive to avoid races without mocking.
"""

import sys
import threading
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_TESTS_ROOT = Path(__file__).resolve().parents[2]   # tests/
_SRC = _TESTS_ROOT.parent / "src"                   # src/

sys.path.insert(0, str(_SRC))

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from models import ExamPeriod
from scheduling.examDateHandler import ExamDateHandler
from application.async_runner import AsyncScheduleRunner, LoadingState
from gui.presenters.dateManagementPresenter import DateManagementPresenter


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_period(excluded: list[date] | None = None) -> ExamPeriod:
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 5),
        excluded_dates=list(excluded or []),
    )


def _make_mock_thread_class(run_immediately: bool = True):
    """
    Return a MagicMock that replaces ``threading.Thread``.

    When ``run_immediately=True`` the mock's ``start()`` immediately invokes
    ``target(*args)`` so callbacks fire synchronously inside the test.
    """
    mock_thread_instance = MagicMock()

    def _fake_start():
        if run_immediately:
            # Simulate the worker running to completion on the "background" thread.
            target = mock_thread_cls.call_args.kwargs.get(
                "target",
                mock_thread_cls.call_args.args[0] if mock_thread_cls.call_args.args else None,
            )
            args = mock_thread_cls.call_args.kwargs.get("args", ())
            if target:
                target(*args)

    mock_thread_instance.start.side_effect = _fake_start
    mock_thread_cls = MagicMock(return_value=mock_thread_instance)
    return mock_thread_cls, mock_thread_instance


# ---------------------------------------------------------------------------
# AsyncScheduleRunner — unit tests
# ---------------------------------------------------------------------------

class TestAsyncScheduleRunner(unittest.TestCase):
    """AsyncScheduleRunner correctly dispatches work and manages state."""

    # ------------------------------------------------------------------
    # Thread is dispatched
    # ------------------------------------------------------------------

    def test_run_creates_a_thread(self) -> None:
        """run() must construct a threading.Thread object."""
        mock_cls, _ = _make_mock_thread_class()
        runner = AsyncScheduleRunner()

        with patch("application.async_runner.threading.Thread", mock_cls):
            runner.run(task=lambda: None)

        mock_cls.assert_called_once()

    def test_run_starts_the_thread(self) -> None:
        """run() must call thread.start() to launch the worker."""
        mock_cls, mock_instance = _make_mock_thread_class(run_immediately=False)
        runner = AsyncScheduleRunner()

        with patch("application.async_runner.threading.Thread", mock_cls):
            runner.run(task=lambda: None)

        mock_instance.start.assert_called_once()

    def test_thread_is_daemon(self) -> None:
        """The background thread must be created as a daemon thread."""
        mock_cls, _ = _make_mock_thread_class(run_immediately=False)
        runner = AsyncScheduleRunner()

        with patch("application.async_runner.threading.Thread", mock_cls):
            runner.run(task=lambda: None)

        _, kwargs = mock_cls.call_args
        self.assertTrue(kwargs.get("daemon", False))

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def test_on_started_fires_before_thread_start(self) -> None:
        """on_started must be called before thread.start()."""
        call_order: list[str] = []
        mock_cls, mock_instance = _make_mock_thread_class(run_immediately=False)
        mock_instance.start.side_effect = lambda: call_order.append("start")

        def on_started():
            call_order.append("on_started")

        runner = AsyncScheduleRunner()
        with patch("application.async_runner.threading.Thread", mock_cls):
            runner.run(task=lambda: None, on_started=on_started)

        self.assertEqual(call_order, ["on_started", "start"])

    def test_on_complete_receives_task_result(self) -> None:
        """on_complete is called with the value returned by task()."""
        sentinel = object()
        received: list = []

        mock_cls, _ = _make_mock_thread_class(run_immediately=True)
        runner = AsyncScheduleRunner()

        with patch("application.async_runner.threading.Thread", mock_cls):
            runner.run(
                task=lambda: sentinel,
                on_complete=lambda r: received.append(r),
            )

        self.assertEqual(received, [sentinel])

    def test_on_error_receives_exception(self) -> None:
        """on_error is called when task() raises."""
        boom = RuntimeError("boom")
        errors: list = []

        mock_cls, _ = _make_mock_thread_class(run_immediately=True)
        runner = AsyncScheduleRunner()

        with patch("application.async_runner.threading.Thread", mock_cls):
            runner.run(
                task=lambda: (_ for _ in ()).throw(boom),
                on_error=lambda e: errors.append(e),
            )

        self.assertEqual(len(errors), 1)
        self.assertIs(errors[0], boom)

    def test_no_callback_on_error_does_not_crash(self) -> None:
        """If on_error is None and task raises, the runner must not propagate."""
        mock_cls, _ = _make_mock_thread_class(run_immediately=True)
        runner = AsyncScheduleRunner()

        with patch("application.async_runner.threading.Thread", mock_cls):
            # Should complete without raising.
            runner.run(task=lambda: 1 / 0)

    # ------------------------------------------------------------------
    # Debounce
    # ------------------------------------------------------------------

    def test_second_run_while_active_returns_false(self) -> None:
        """A second run() call while a task is running must be debounced."""
        # Use a real thread so _is_running is True during the second call.
        gate = threading.Event()    # keeps the worker blocked
        done = threading.Event()

        def slow_task():
            gate.wait(timeout=2)

        runner = AsyncScheduleRunner()
        first = runner.run(task=slow_task)
        second = runner.run(task=lambda: None)

        gate.set()  # release the worker so the test can finish
        self.assertTrue(first)
        self.assertFalse(second)

    def test_run_returns_true_on_dispatch(self) -> None:
        """run() returns True when the task is successfully dispatched."""
        mock_cls, _ = _make_mock_thread_class(run_immediately=False)
        runner = AsyncScheduleRunner()

        with patch("application.async_runner.threading.Thread", mock_cls):
            result = runner.run(task=lambda: None)

        self.assertTrue(result)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def test_loading_state_is_idle_initially(self) -> None:
        """A new runner must report IDLE before any task is dispatched."""
        runner = AsyncScheduleRunner()
        self.assertEqual(runner.loading_state, LoadingState.IDLE)
        self.assertFalse(runner.is_running)

    def test_loading_state_is_idle_after_task_completes(self) -> None:
        """Runner reports IDLE again after the task finishes."""
        mock_cls, _ = _make_mock_thread_class(run_immediately=True)
        runner = AsyncScheduleRunner()

        with patch("application.async_runner.threading.Thread", mock_cls):
            runner.run(task=lambda: None)

        self.assertEqual(runner.loading_state, LoadingState.IDLE)
        self.assertFalse(runner.is_running)


# ---------------------------------------------------------------------------
# DateManagementPresenter — async integration tests
# ---------------------------------------------------------------------------

class TestDateManagementPresenterAsync(unittest.TestCase):
    """DateManagementPresenter.on_regenerate_async wires correctly to the runner."""

    def _make_presenter(self, generator=None, courses=None, periods=None):
        period = _make_period()
        cache = MagicMock()
        presenter = DateManagementPresenter(
            exam_period=period,
            date_handler=ExamDateHandler(),
            cache_manager=cache,
            schedule_generator=generator,
            courses=courses or [],
            exam_periods=periods or [],
        )
        return presenter, period, cache

    def _make_runner(self, run_immediately: bool = True):
        """Return a runner backed by a mocked Thread."""
        mock_cls, mock_instance = _make_mock_thread_class(run_immediately=run_immediately)
        runner = AsyncScheduleRunner()
        return runner, mock_cls

    # ------------------------------------------------------------------

    def test_on_regenerate_async_calls_runner_run(self) -> None:
        """on_regenerate_async must delegate to runner.run()."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = True
        generator = MagicMock()
        generator.generate_exam_systems.return_value = []
        presenter, _, _ = self._make_presenter(generator=generator)

        presenter.on_regenerate_async(runner=mock_runner)

        mock_runner.run.assert_called_once()

    def test_on_regenerate_async_task_writes_to_cache(self) -> None:
        """The task closure writes generated schedules to the cache."""
        schedules = [MagicMock(), MagicMock()]
        generator = MagicMock()
        generator.generate_exam_systems.return_value = schedules
        presenter, _, cache = self._make_presenter(generator=generator)

        runner, mock_cls = self._make_runner(run_immediately=True)
        with patch("application.async_runner.threading.Thread", mock_cls):
            presenter.on_regenerate_async(runner=runner)

        cache.set_generated_schedules.assert_called_once_with(schedules)

    def test_on_regenerate_async_on_complete_receives_schedules(self) -> None:
        """on_complete callback receives the generated schedules list."""
        schedules = [MagicMock()]
        generator = MagicMock()
        generator.generate_exam_systems.return_value = schedules
        presenter, _, _ = self._make_presenter(generator=generator)

        received: list = []
        runner, mock_cls = self._make_runner(run_immediately=True)
        with patch("application.async_runner.threading.Thread", mock_cls):
            presenter.on_regenerate_async(
                runner=runner,
                on_complete=lambda s: received.append(s),
            )

        self.assertEqual(received, [schedules])

    def test_on_regenerate_async_without_generator_returns_false(self) -> None:
        """on_regenerate_async returns False when no generator was injected."""
        presenter, _, _ = self._make_presenter(generator=None)
        runner = MagicMock()

        result = presenter.on_regenerate_async(runner=runner)

        self.assertFalse(result)
        runner.run.assert_not_called()

    def test_on_regenerate_async_without_generator_fires_on_error(self) -> None:
        """on_regenerate_async calls on_error when no generator is available."""
        presenter, _, _ = self._make_presenter(generator=None)
        errors: list = []

        presenter.on_regenerate_async(
            runner=MagicMock(),
            on_error=lambda e: errors.append(e),
        )

        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RuntimeError)

    def test_on_regenerate_async_debounce_passthrough(self) -> None:
        """A second on_regenerate_async call while running returns False."""
        gate = threading.Event()
        generator = MagicMock()
        generator.generate_exam_systems.side_effect = lambda *_: gate.wait(timeout=2) or []
        presenter, _, _ = self._make_presenter(generator=generator)

        runner = AsyncScheduleRunner()
        first = presenter.on_regenerate_async(runner=runner)
        second = presenter.on_regenerate_async(runner=runner)

        gate.set()
        self.assertTrue(first)
        self.assertFalse(second)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
