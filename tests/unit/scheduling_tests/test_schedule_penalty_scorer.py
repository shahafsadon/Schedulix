from __future__ import annotations

from datetime import date

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from scheduling.schedulePenaltyScorer import SchedulePenaltyScorer
from tests.unit.scheduling_tests._part4_helpers import make_exam, make_system


def settings_with(**enabled_thresholds: int) -> SchedulingConstraintSettings:
    """Build settings with only the requested soft constraints enabled."""
    settings = SchedulingConstraintSettings.default_configuration()
    for name, k in enabled_thresholds.items():
        settings.constraints[ThresholdConstraintType[name]] = (
            ThresholdConstraintSetting(enabled=True, k=k)
        )
    return settings


def score(system, settings: SchedulingConstraintSettings):
    """Return the penalty score result for compact assertions."""
    return SchedulePenaltyScorer().score(system, settings)


def test_mandatory_gap_violation_has_penalty_50() -> None:
    system = make_system(
        make_exam("83102", date(2026, 1, 1)),
        make_exam("83103", date(2026, 1, 2)),
    )

    result = score(system, settings_with(mandatory_gap_days=10))

    assert result.total_score == 50
    assert len(result.violations) == 1
    assert result.violations[0].requirement_id == "Req 2.1"
    assert result.violations[0].penalty == 50
    assert "required minimum is 10" in result.details[0]


def test_mandatory_span_violation_has_penalty_50() -> None:
    system = make_system(
        make_exam("83102", date(2026, 1, 1)),
        make_exam("83103", date(2026, 1, 2)),
    )

    result = score(system, settings_with(mandatory_span_days=10))

    assert result.total_score == 50
    assert len(result.violations) == 1
    assert result.violations[0].requirement_id == "Req 2.4"
    assert result.violations[0].penalty == 50
    assert "required minimum is 10" in result.details[0]


def test_max_exams_per_day_violation_has_penalty_50() -> None:
    system = make_system(
        make_exam("83102", date(2026, 1, 1), program="83101"),
        make_exam("83103", date(2026, 1, 1), program="83102"),
    )

    result = score(system, settings_with(max_exams_per_day=1))

    assert result.total_score == 50
    assert len(result.violations) == 1
    assert result.violations[0].requirement_id == "Req 2.5"
    assert result.violations[0].penalty == 50
    assert "maximum allowed is 1" in result.details[0]


def test_any_course_gap_violation_has_penalty_10() -> None:
    system = make_system(
        make_exam("83102", date(2026, 1, 1)),
        make_exam("83103", date(2026, 1, 2), status="Elective"),
    )

    result = score(system, settings_with(any_course_gap_days=10))

    assert result.total_score == 10
    assert len(result.violations) == 1
    assert result.violations[0].requirement_id == "Req 2.2"
    assert result.violations[0].penalty == 10
    assert "required minimum is 10" in result.details[0]


def test_elective_conflicts_per_program_violation_has_penalty_10() -> None:
    system = make_system(
        make_exam("83102", date(2026, 1, 1), status="Elective"),
        make_exam("83103", date(2026, 1, 1), status="Elective"),
    )

    result = score(system, settings_with(elective_conflicts_per_program=0))

    assert result.total_score == 10
    assert len(result.violations) == 1
    assert result.violations[0].requirement_id == "Req 2.3"
    assert result.violations[0].penalty == 10
    assert "maximum allowed is 0" in result.details[0]


def test_multiple_simultaneous_violations_sum_all_penalties() -> None:
    system = make_system(
        make_exam("83102", date(2026, 1, 1)),
        make_exam("83103", date(2026, 1, 1)),
        make_exam("83104", date(2026, 1, 1), status="Elective"),
        make_exam("83105", date(2026, 1, 1), status="Elective"),
    )
    settings = settings_with(
        mandatory_gap_days=10,
        mandatory_span_days=10,
        max_exams_per_day=3,
        any_course_gap_days=10,
        elective_conflicts_per_program=0,
    )

    result = score(system, settings)

    assert result.total_score == 170
    assert [violation.penalty for violation in result.violations] == [
        50,
        10,
        10,
        50,
        50,
    ]
    assert {violation.requirement_id for violation in result.violations} == {
        "Req 2.1",
        "Req 2.2",
        "Req 2.3",
        "Req 2.4",
        "Req 2.5",
    }


def test_no_violations_returns_zero_score_and_empty_details() -> None:
    system = make_system(
        make_exam("83102", date(2026, 1, 1)),
        make_exam("83103", date(2026, 1, 11)),
        make_exam("83104", date(2026, 1, 25), status="Elective"),
    )
    settings = settings_with(
        mandatory_gap_days=10,
        mandatory_span_days=10,
        max_exams_per_day=2,
        any_course_gap_days=10,
        elective_conflicts_per_program=0,
    )

    result = score(system, settings)

    assert result.total_score == 0
    assert result.violations == ()
    assert result.details == ()
