import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from scheduling.batchIterator import (
    GeneratedScheduleBatch,
    iter_fixed_size_batches,
    iter_exam_system_batches,
)
from scheduling.examScheduleGenerator import ExamSystem


def _mock_exam_systems(count: int) -> list[ExamSystem]:
    return [ExamSystem(period_schedules=[]) for _ in range(count)]


class BatchIteratorTests(unittest.TestCase):
    def test_iter_fixed_size_batches_empty(self) -> None:
        batches = list(iter_fixed_size_batches([], batch_size=5))
        self.assertEqual(batches, [])

    def test_iter_fixed_size_batches_exact_multiple(self) -> None:
        items = list(range(10))
        batches = list(iter_fixed_size_batches(items, batch_size=5))
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0], [0, 1, 2, 3, 4])
        self.assertEqual(batches[1], [5, 6, 7, 8, 9])

    def test_iter_fixed_size_batches_partial_final_batch(self) -> None:
        items = list(range(7))
        batches = list(iter_fixed_size_batches(items, batch_size=5))
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0], [0, 1, 2, 3, 4])
        self.assertEqual(batches[1], [5, 6])

    def test_iter_fixed_size_batches_zero_size_raises(self) -> None:
        with self.assertRaises(ValueError):
            list(iter_fixed_size_batches([1, 2, 3], batch_size=0))

    def test_should_stop_aborts_iteration_early(self) -> None:
        def stop_after_three() -> bool:
            stop_after_three.calls += 1
            return stop_after_three.calls > 3
        
        stop_after_three.calls = 0

        items = list(range(10))
        batches = list(
            iter_fixed_size_batches(items, batch_size=5, should_stop=stop_after_three)
        )
        # It checked should_stop 4 times. 1, 2, 3 returned False, 4 returned True.
        # So only 3 items made it into the batch before it aborted.
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0], [0, 1, 2])

    def test_iter_exam_system_batches_assigns_ids_correctly(self) -> None:
        systems = _mock_exam_systems(7)
        batches = list(iter_exam_system_batches(systems, batch_size=3))

        self.assertEqual(len(batches), 3)

        b1 = batches[0]
        self.assertEqual(b1.batch_number, 1)
        self.assertEqual(b1.starting_schedule_id, 1)
        self.assertEqual(b1.ending_schedule_id, 3)
        self.assertEqual(b1.size, 3)

        b2 = batches[1]
        self.assertEqual(b2.batch_number, 2)
        self.assertEqual(b2.starting_schedule_id, 4)
        self.assertEqual(b2.ending_schedule_id, 6)
        self.assertEqual(b2.size, 3)

        b3 = batches[2]
        self.assertEqual(b3.batch_number, 3)
        self.assertEqual(b3.starting_schedule_id, 7)
        self.assertEqual(b3.ending_schedule_id, 7)
        self.assertEqual(b3.size, 1)
        
    def test_iter_exam_system_batches_zero_starting_id_raises(self) -> None:
        with self.assertRaises(ValueError):
            list(iter_exam_system_batches([], batch_size=5, starting_schedule_id=0))

if __name__ == "__main__":
    unittest.main()
