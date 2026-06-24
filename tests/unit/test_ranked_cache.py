from __future__ import annotations

import pickle
from pathlib import Path

from application.cache_manager import CacheManager, _CacheState
from ranking_settings import RankedExamSystem, ScheduleMetrics
from scheduling.examScheduleGenerator import ExamSystem


def _ranked(key: int) -> RankedExamSystem:
    return RankedExamSystem(
        exam_system=ExamSystem(period_schedules=[]),
        metrics=ScheduleMetrics(
            schedule_id=key,
            min_mandatory_gap=key,
            average_all_gap=float(key),
            elective_collision_count=0,
            mandatory_span=key,
            max_exams_per_day=1,
        ),
        key=key,
    )


def _cache(
    tmp_path: Path,
    monkeypatch,
) -> CacheManager:
    monkeypatch.setattr(
        CacheManager,
        "_PKL_PATH",
        tmp_path / "internal_data.pkl",
    )
    return CacheManager()


def test_ranked_schedules_round_trip_through_pickle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Calculated metrics and ranking wrappers must be cacheable."""
    cache = _cache(
        tmp_path,
        monkeypatch,
    )

    cache.set_ranked_schedules([_ranked(1), _ranked(2)])

    restored = CacheManager()

    assert restored.get_ranked_schedules() == [_ranked(1), _ranked(2)]
    assert restored.get_result_mode() == "final_ranked"


def test_setting_generated_schedules_clears_stale_ranked_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """New generator output invalidates metrics from the previous output."""
    cache = _cache(
        tmp_path,
        monkeypatch,
    )
    cache.set_ranked_schedules([_ranked(1)])

    cache.set_generated_schedules([ExamSystem(period_schedules=[])])

    assert cache.get_ranked_schedules() == []
    assert cache.get_result_mode() == "unranked_generated"


def test_invalidating_generated_schedules_also_clears_ranked_schedules(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The display order cannot survive after the raw schedules are removed."""
    cache = _cache(
        tmp_path,
        monkeypatch,
    )
    cache.set_generated_schedules([ExamSystem(period_schedules=[])])
    cache.set_ranked_schedules([_ranked(1)])

    cache.invalidate_generated_schedules()

    assert cache.get_generated_schedules() == []
    assert cache.get_ranked_schedules() == []
    assert cache.get_result_mode() == "unranked_generated"


def test_old_cache_payload_without_ranked_field_loads_safely(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Older Version 2.0 pickle files should receive a safe default field."""
    pkl_path = tmp_path / "internal_data.pkl"
    old_state = _CacheState()
    delattr(old_state, "ranked_schedules")

    with pkl_path.open("wb") as file:
        pickle.dump(old_state, file)

    monkeypatch.setattr(
        CacheManager,
        "_PKL_PATH",
        pkl_path,
    )

    restored = CacheManager()

    assert restored.get_ranked_schedules() == []


def test_old_cache_payload_without_result_mode_does_not_masquerade_as_final_ranked(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Missing mode defaults to generated output even if ranked data exists."""
    pkl_path = tmp_path / "internal_data.pkl"
    old_state = _CacheState()
    old_state.generated_schedules = [ExamSystem(period_schedules=[])]
    old_state.ranked_schedules = [_ranked(1)]
    delattr(old_state, "result_mode")

    with pkl_path.open("wb") as file:
        pickle.dump(old_state, file)

    monkeypatch.setattr(
        CacheManager,
        "_PKL_PATH",
        pkl_path,
    )

    restored = CacheManager()

    assert restored.get_ranked_schedules() == [_ranked(1)]
    assert restored.get_result_mode() == "unranked_generated"
