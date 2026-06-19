"""Lazy batch utilities for generated exam systems.

The scheduling generator already yields valid ``ExamSystem`` objects lazily.
This module provides the small batching layer that sits above that iterator:
it groups generated systems into fixed-size lists without materializing the full
result set.

The utilities are deliberately GUI-free. They belong to the scheduling/service
core and can be reused by tests, presenters, or future export flows.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import TypeVar

from scheduling.examScheduleGenerator import ExamSystem


T = TypeVar("T")


@dataclass(frozen=True)
class GeneratedScheduleBatch:
    """One lazily consumed batch of generated exam systems.

    Attributes
    ----------
    batch_number:
        1-based batch index in the current progressive run.
    starting_schedule_id:
        Stable 1-based global schedule id assigned to the first system in this
        batch. It lets metric/ranking code keep deterministic ids when ranking
        batch-by-batch.
    schedules:
        The generated systems in this batch. This list is bounded by the caller's
        batch size, except possibly the final smaller batch.
    """

    batch_number: int
    starting_schedule_id: int
    schedules: list[ExamSystem]

    @property
    def size(self) -> int:
        """Number of schedules in the batch."""
        return len(self.schedules)

    @property
    def ending_schedule_id(self) -> int:
        """Stable id assigned to the last schedule in the batch."""
        return self.starting_schedule_id + self.size - 1

    @property
    def is_empty(self) -> bool:
        """Return True only for defensive/test-created empty batches."""
        return self.size == 0


def iter_fixed_size_batches(
    items: Iterable[T],
    batch_size: int,
    *,
    should_stop: Callable[[], bool] | None = None,
) -> Iterator[list[T]]:
    """Yield ``items`` in fixed-size lazy batches.

    The function consumes only enough input to produce the next batch. It never
    converts the whole iterable to a list, so a generator can keep producing more
    results after each yielded batch is processed.

    If ``should_stop`` is provided and returns True, no more input is consumed.
    Any already collected partial batch is yielded once before iteration stops.
    """
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero.")

    batch: list[T] = []

    for item in items:
        if should_stop is not None and should_stop():
            break

        batch.append(item)
        if len(batch) == batch_size:
            yield batch
            batch = []

    if batch:
        yield batch


def iter_exam_system_batches(
    exam_systems: Iterable[ExamSystem],
    batch_size: int,
    *,
    starting_schedule_id: int = 1,
    should_stop: Callable[[], bool] | None = None,
) -> Iterator[GeneratedScheduleBatch]:
    """Yield lazily generated exam systems as numbered schedule batches.

    ``starting_schedule_id`` is the first stable schedule id for this run. The
    default of 1 matches the existing full-materialization flow.
    """
    if starting_schedule_id <= 0:
        raise ValueError("starting_schedule_id must be greater than zero.")

    next_schedule_id = starting_schedule_id
    batch_number = 1

    for schedules in iter_fixed_size_batches(
        exam_systems,
        batch_size,
        should_stop=should_stop,
    ):
        schedule_batch = GeneratedScheduleBatch(
            batch_number=batch_number,
            starting_schedule_id=next_schedule_id,
            schedules=schedules,
        )
        yield schedule_batch

        next_schedule_id += schedule_batch.size
        batch_number += 1


# Backwards-friendly aliases for tests/callers that use generic names.
iter_batches = iter_fixed_size_batches
batch_exam_systems = iter_exam_system_batches
