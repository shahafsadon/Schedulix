"""
async_runner.py
~~~~~~~~~~~~~~~
Thread-safe background task runner for the Schedulix GUI layer (SCRUM-115).

``AsyncScheduleRunner`` offloads heavy computations to a daemon thread so the
main Tkinter event loop remains responsive.  The original ``run()`` API is kept
for existing screens and tests.  ``run_with_progress()`` adds cancellation and a
plain progress callback for progressive schedule-generation previews.

Thread-safety contract
----------------------
* The runner itself is thread-safe: ``_is_running`` is guarded by a
  ``threading.Lock`` so concurrent calls are correctly debounced.
* Callbacks are plain Python callables.  The runner does not import Tkinter and
  does not marshal calls onto the GUI thread.  Views must wrap callback bodies
  in ``widget.after(0, ...)`` when updating widgets.
"""

from __future__ import annotations

import inspect
import threading
from enum import Enum, auto
from typing import Any, Callable


class LoadingState(Enum):
    """Represents the two observable states of the async runner."""

    IDLE = auto()
    RUNNING = auto()


class CancellationToken:
    """Small thread-safe cancellation flag shared with background tasks."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """Request cooperative cancellation."""
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        """True after cancellation was requested."""
        return self._event.is_set()

    def throw_if_cancelled(self) -> None:
        """Raise RuntimeError when cancellation was requested."""
        if self.is_cancelled:
            raise RuntimeError("Operation cancelled.")


class AsyncScheduleRunner:
    """Dispatches one background worker thread and fires lifecycle callbacks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._is_running: bool = False
        self._current_token: CancellationToken | None = None

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

    def cancel_current(self) -> bool:
        """Request cancellation of the current progressive task.

        Returns ``True`` when a running task had a token to cancel.  Normal
        ``run()`` tasks do not receive a token, so they cannot be cancelled
        cooperatively through this method.
        """
        with self._lock:
            token = self._current_token
            if not self._is_running or token is None:
                return False
            token.cancel()
            return True

    def run(
        self,
        task: Callable[[], Any],
        on_started: Callable[[], None] | None = None,
        on_complete: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> bool:
        """Dispatch ``task`` to a daemon background thread.

        This is the original API.  It remains intentionally unchanged so older
        presenter/screen tests continue to use it.
        """
        with self._lock:
            if self._is_running:
                return False
            self._is_running = True
            self._current_token = None

        if on_started is not None:
            on_started()

        thread = threading.Thread(
            target=self._worker,
            args=(task, on_complete, on_error),
            daemon=True,
        )
        thread.start()
        return True

    def run_with_progress(
        self,
        task: Callable[..., Any],
        on_started: Callable[[], None] | None = None,
        on_progress: Callable[[Any], None] | None = None,
        on_complete: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> bool:
        """Dispatch a cancellable background task that may emit progress.

        ``task`` may accept either ``(token)`` or ``(token, on_progress)``.  The
        flexible signature keeps the runner useful for tests and for presenters
        that prefer to capture the progress callback in a closure.
        """
        token = CancellationToken()

        with self._lock:
            if self._is_running:
                return False
            self._is_running = True
            self._current_token = token

        if on_started is not None:
            on_started()

        thread = threading.Thread(
            target=self._worker_with_progress,
            args=(task, token, on_progress, on_complete, on_error),
            daemon=True,
        )
        thread.start()
        return True

    # ------------------------------------------------------------------
    # Private workers
    # ------------------------------------------------------------------

    def _worker(
        self,
        task: Callable[[], Any],
        on_complete: Callable[[Any], None] | None,
        on_error: Callable[[Exception], None] | None,
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
            self._finish_worker()

    def _worker_with_progress(
        self,
        task: Callable[..., Any],
        token: CancellationToken,
        on_progress: Callable[[Any], None] | None,
        on_complete: Callable[[Any], None] | None,
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        """Execute a cancellable task and route progress/final callbacks."""
        try:
            result = self._invoke_progress_task(
                task,
                token,
                on_progress,
            )
            if on_complete is not None:
                on_complete(result)
        except Exception as exc:  # noqa: BLE001
            if on_error is not None:
                on_error(exc)
        finally:
            self._finish_worker()

    @staticmethod
    def _invoke_progress_task(
        task: Callable[..., Any],
        token: CancellationToken,
        on_progress: Callable[[Any], None] | None,
    ) -> Any:
        """Call a progress task with the number of args it expects."""
        try:
            parameters = inspect.signature(task).parameters.values()
            positional_parameters = [
                parameter
                for parameter in parameters
                if parameter.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
            ]
            accepts_varargs = any(
                parameter.kind == inspect.Parameter.VAR_POSITIONAL
                for parameter in parameters
            )
        except (TypeError, ValueError):
            # Builtins/callables without an introspectable signature: use the
            # richer two-argument contract.
            return task(token, on_progress)

        if accepts_varargs or len(positional_parameters) >= 2:
            return task(token, on_progress)
        return task(token)

    def _finish_worker(self) -> None:
        """Release debounce state after any worker exits."""
        with self._lock:
            self._is_running = False
            self._current_token = None
