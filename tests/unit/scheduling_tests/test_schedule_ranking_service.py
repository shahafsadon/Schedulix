from __future__ import annotations

from ranking_settings import RankedExamSystem, RankingSettings, ScheduleMetrics
from scheduling.examScheduleGenerator import ExamSystem
from scheduling.scheduleRankingService import ScheduleRankingService


def _ranked(key: int) -> RankedExamSystem:
    return RankedExamSystem(
        exam_system=ExamSystem(period_schedules=[]),
        metrics=ScheduleMetrics(
            schedule_id=key,
            min_mandatory_gap=0,
            average_all_gap=0,
            elective_collision_count=0,
            mandatory_span=0,
            max_exams_per_day=0,
        ),
        key=key,
    )


def test_rerank_reports_elapsed_seconds_without_recalculating_metrics() -> None:
    """Ranking-only changes should return a measured response time."""
    times = iter([10.0, 10.125])
    service = ScheduleRankingService(clock=lambda: next(times))
    existing = [_ranked(1), _ranked(2)]

    outcome = service.rerank(
        existing,
        RankingSettings([]),
    )

    assert outcome.ranked_schedules == existing
    assert outcome.elapsed_seconds == 0.125
