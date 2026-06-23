from ranking_settings import ScheduleMetrics
from scheduling.qualityTagCalculator import QualityTagCalculator


def test_quality_tag_uses_penalty_score_when_available() -> None:
    result = QualityTagCalculator().calculate(penalty_score=60)

    assert result.tag == "weak"
    assert result.penalty_score == 60


def test_quality_tag_can_be_calculated_from_metrics() -> None:
    metrics = ScheduleMetrics(
        schedule_id=1,
        min_mandatory_gap=5,
        average_all_gap=7.0,
        elective_collision_count=2,
        mandatory_span=10,
        max_exams_per_day=3,
    )

    result = QualityTagCalculator().calculate(metrics)

    assert result.tag == "acceptable"
    assert result.penalty_score == 30
