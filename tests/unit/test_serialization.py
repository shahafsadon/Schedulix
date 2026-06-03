"""Focused serialization tests for the Version 2.0 cache layer."""

from __future__ import annotations

import pickle
from datetime import date
from pathlib import Path

from application.cache_manager import CacheManager
from models import Course, ExamPeriod, ProgramEnrollment


def _course() -> Course:
    return Course(
        name="Physics 1",
        course_number="83102",
        instructor="Prof. Test",
        programs=[ProgramEnrollment("83101", 1, "FALL", "Obligatory")],
        evaluation_type="Exam",
    )


def _period() -> ExamPeriod:
    return ExamPeriod(
        semester="FALL",
        moed="Aleph",
        start_date=date(2026, 1, 20),
        end_date=date(2026, 2, 10),
        excluded_dates=[date(2026, 1, 24)],
    )


def test_cache_round_trip_restores_nested_models(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Pickle persistence must restore nested dataclass content, not only list sizes."""
    monkeypatch.setattr(
        CacheManager,
        "_PKL_PATH",
        tmp_path / "internal_data.pkl",
    )

    first = CacheManager()
    first.set_courses([_course()])
    first.set_exam_periods([_period()])
    first.set_selected_programs(["83101"])

    restored = CacheManager()

    assert restored.get_courses() == [_course()]
    assert restored.get_exam_periods() == [_period()]
    assert restored.get_selected_programs() == ["83101"]


def test_corrupted_pickle_falls_back_to_empty_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A damaged persistence file must not crash application startup."""
    pkl_path = tmp_path / "internal_data.pkl"
    pkl_path.write_bytes(b"not-a-valid-pickle")

    monkeypatch.setattr(CacheManager, "_PKL_PATH", pkl_path)

    restored = CacheManager()

    assert restored.get_courses() == []
    assert restored.get_exam_periods() == []
    assert restored.get_selected_programs() == []
    assert restored.get_generated_schedules() == []


def test_incompatible_pickle_payload_falls_back_to_empty_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A valid pickle from an incompatible source must be rejected safely."""
    pkl_path = tmp_path / "internal_data.pkl"

    with pkl_path.open("wb") as file:
        pickle.dump({"sentinel": "wrong-version"}, file)

    monkeypatch.setattr(CacheManager, "_PKL_PATH", pkl_path)

    restored = CacheManager()

    assert restored.get_courses() == []
    assert restored.get_exam_periods() == []
    assert restored.get_selected_programs() == []
    assert restored.get_generated_schedules() == []