"""
async_runner.py
~~~~~~~~~~~~~~~
Thread-safe background task runner for the Schedulix GUI layer (SCRUM-115).

Design overview
---------------
``AsyncScheduleRunner`` offloads heavy computations (schedule generation) to a
daemon thread so the main Tkinter event loop remains fully responsive.

Thread-safety contract
----------------------
* The runner itself is thread-safe: ``_is_running`` is guarded by a
  ``threading.Lock`` so concurrent calls to ``run()`` are correctly debounced.
* Callbacks (``on_started``, ``on_complete``, ``on_error``) are **plain Python
  callables**.  The runner fires them without knowing anything about the GUI.
  It is the **View's responsibility** to wrap callbacks in ``widget.after(0,
  cb)`` so that widget updates happen on the main Tkinter thread.

Usage example (in a ctk screen)
--------------------------------
::

    runner = AsyncScheduleRunner()

    def _on_complete(schedules):
        # Called from the background thread — use after() to reach the GUI.
        self.after(0, lambda: self._update_results(schedules))

    presenter.on_regenerate_async(
        runner=runner,
        on_started=lambda: self.after(0, self._show_spinner),
        on_complete=_on_complete,
        on_error=lambda e: self.after(0, lambda: self._show_error(e)),
    )

No Version 1.0 source files are modified by this module.
No customtkinter imports — this module is fully testable in headless CI.
"""

from __future__ import annotations

import threading
from enum import Enum, auto
from typing import Any, Callable


class LoadingState(Enum):
    """
    Represents the two observable states of the async runner.

    Views or loading indicators can query ``runner.loading_state`` to
    decide whether to show a spinner or an idle status indicator.
    """

    IDLE = auto()
    RUNNING = auto()


class AsyncScheduleRunner:
    """
    Dispatches a single background worker thread and fires lifecycle callbacks.

    Debouncing
    ----------
    Only one task may run at a time.  If ``run()`` is called while a previous
    task is still executing, it returns ``False`` immediately and discards the
    new request.  This prevents thread exhaustion from rapid repeated clicks.

    Thread model
    ------------
    The worker thread is always a **daemon thread** so the Python process can
    exit cleanly even if a long computation is in progress.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._is_running: bool = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """``True`` while a background task is active."""
        with self._lock:
            return self._is_running

    @property
    def loading_state(self) -> LoadingState:
        """Current ``LoadingState``, derived from ``is_running``."""
        return LoadingState.RUNNING if self.is_running else LoadingState.IDLE

    def run(
        self,
        task: Callable[[], Any],
        on_started:  Callable[[], None]          | None = None,
        on_complete: Callable[[Any], None]       | None = None,
        on_error:    Callable[[Exception], None] | None = None,
    ) -> bool:
        """
        Dispatch ``task`` to a daemon background thread.

        Parameters
        ----------
        task:
            A zero-argument callable that performs the heavy computation and
            returns a result.  It is executed entirely on a background thread.
        on_started:
            Optional callback fired **synchronously on the calling thread**
            (before the background thread starts) so a spinner can appear
            before any work begins.
        on_complete:
            Optional callback fired from the **background thread** with the
            value returned by ``task()``.  Wrap in ``widget.after(0, ...)``
            inside the View for GUI thread safety.
        on_error:
            Optional callback fired from the **background thread** when
            ``task()`` raises any exception.  Wrap in ``widget.after(0, ...)``
            inside the View for GUI thread safety.

        Returns
        -------
        bool
            ``True`` if the task was successfully dispatched.
            ``False`` if a task is already running (debounced — caller should
            ignore or show a "busy" indicator).
        """
        with self._lock:
            if self._is_running:
                return False
            self._is_running = True

        # Fire on_started synchronously so the View can show a spinner
        # before the background thread even begins.
        if on_started is not None:
            on_started()

        thread = threading.Thread(
            target=self._worker,
            args=(task, on_complete, on_error),
            daemon=True,
        )
        thread.start()
        return True

    # ------------------------------------------------------------------
    # Private worker
    # ------------------------------------------------------------------

    def _worker(
        self,
        task: Callable[[], Any],
        on_complete: Callable[[Any], None]       | None,
        on_error:    Callable[[Exception], None] | None,
    ) -> None:
        """Execute ``task`` and route the result to the appropriate callback."""
        try:
            result = task()
            if on_complete is not None:
                on_complete(result)
        except Exception as exc:  # noqa: BLE001
            if on_error is not None:
                on_error(exc)
        finally:
            # Always release the debounce lock so future calls can proceed.
            with self._lock:
                self._is_running = False
