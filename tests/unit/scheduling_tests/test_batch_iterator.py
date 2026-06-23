from __future__ import annotations

import pytest

from scheduling.batchIterator import (
    GeneratedScheduleBatch,
    iter_exam_system_batches,
    iter_fixed_size_batches,
)
from scheduling.examScheduleGenerator import ExamSystem


def test_fixed_size_batches_are_lazy_and_do_not_materialize_the_iterable() -> None:
    consumed: list[int] = []

    def source():
        for item in range(10):
            consumed.append(item)
            yield item

    batches = iter_fixed_size_batches(source(), batch_size=3)

    assert consumed == []
    assert next(batches) == [0, 1, 2]
    assert consumed == [0, 1, 2]
    assert next(batches) == [3, 4, 5]
    assert consumed == [0, 1, 2, 3, 4, 5]


def test_fixed_size_batches_yield_final_partial_batch() -> None:
    assert list(iter_fixed_size_batches([1, 2, 3, 4, 5], batch_size=2)) == [
        [1, 2],
        [3, 4],
        [5],
    ]


@pytest.mark.parametrize("batch_size", [0, -1])
def test_fixed_size_batches_reject_invalid_batch_size(batch_size: int) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        list(iter_fixed_size_batches([1], batch_size=batch_size))


def test_stop_callback_prevents_consuming_another_item_after_cancellation() -> None:
    consumed: list[int] = []
    cancelled = False

    def source():
        for item in range(10):
            consumed.append(item)
            yield item

    def should_stop() -> bool:
        return cancelled

    batches = iter_fixed_size_batches(
        source(),
        batch_size=2,
        should_stop=should_stop,
    )

    assert next(batches) == [0, 1]
    cancelled = True

    assert list(batches) == []
    assert consumed == [0, 1]


def test_stop_callback_flushes_collected_partial_batch_without_reading_more() -> None:
    consumed: list[int] = []
    checks = 0

    def source():
        for item in range(10):
            consumed.append(item)
            yield item

    def should_stop() -> bool:
        nonlocal checks
        checks += 1
        return checks == 3

    assert list(
        iter_fixed_size_batches(
            source(),
            batch_size=5,
            should_stop=should_stop,
        )
    ) == [[0, 1]]
    assert consumed == [0, 1]


def test_exam_system_batches_have_stable_global_numbering() -> None:
    systems = [ExamSystem(period_schedules=[]) for _ in range(5)]

    batches = list(
        iter_exam_system_batches(
            systems,
            batch_size=2,
            starting_schedule_id=10,
        )
    )

    assert [batch.batch_number for batch in batches] == [1, 2, 3]
    assert [batch.starting_schedule_id for batch in batches] == [10, 12, 14]
    assert [batch.ending_schedule_id for batch in batches] == [11, 13, 14]
    assert [batch.size for batch in batches] == [2, 2, 1]


def test_exam_system_batches_reject_invalid_starting_schedule_id() -> None:
    with pytest.raises(ValueError, match="starting_schedule_id"):
        list(
            iter_exam_system_batches(
                [ExamSystem(period_schedules=[])],
                batch_size=1,
                starting_schedule_id=0,
            )
        )


def test_generated_schedule_batch_reports_empty_defensive_batches() -> None:
    batch = GeneratedScheduleBatch(
        batch_number=1,
        starting_schedule_id=5,
        schedules=[],
    )

    assert batch.size == 0
    assert batch.is_empty
    assert batch.ending_schedule_id == 4
