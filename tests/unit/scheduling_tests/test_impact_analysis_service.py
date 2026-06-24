from datetime import date

from scheduling.impactAnalysisService import ImpactAnalysisService

from ._part4_helpers import make_exam, make_system, max_exams_settings


def test_resolved_issue_is_reported_after_conflict_is_fixed() -> None:
    before = make_system(
        make_exam("83001", date(2026, 1, 1)),
        make_exam("83002", date(2026, 1, 1)),
    )
    after = make_system(
        make_exam("83001", date(2026, 1, 1)),
        make_exam("83002", date(2026, 1, 3)),
    )

    result = ImpactAnalysisService().analyze(before, after)

    assert len(result.resolved_issues) == 1
    assert result.resolved_issues[0].requirement_id == "V2.0-critical-conflict-rule"
    assert result.new_issues == []


def test_new_issue_is_reported_after_move_creates_overloaded_day() -> None:
    before = make_system(
        make_exam("83001", date(2026, 1, 1), program="83101"),
        make_exam("83002", date(2026, 1, 2), program="83102"),
    )
    after = make_system(
        make_exam("83001", date(2026, 1, 1), program="83101"),
        make_exam("83002", date(2026, 1, 1), program="83102"),
    )

    result = ImpactAnalysisService().analyze(before, after, max_exams_settings(1))

    assert len(result.new_issues) == 1
    assert result.new_issues[0].requirement_id == "Req 2.5"


def test_unchanged_issue_remains_visible_when_relevant() -> None:
    schedule = make_system(
        make_exam("83001", date(2026, 1, 1), program="83101"),
        make_exam("83002", date(2026, 1, 1), program="83102"),
    )

    result = ImpactAnalysisService().analyze(
        schedule,
        schedule,
        max_exams_settings(1),
    )

    assert result.resolved_issues == []
    assert result.new_issues == []
    assert len(result.unchanged_issues) == 1
    assert result.unchanged_issues[0].requirement_id == "Req 2.5"
