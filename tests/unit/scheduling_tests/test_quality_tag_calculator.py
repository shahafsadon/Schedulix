"""Unit tests for QualityTagCalculator (SCRUM-191).

Coverage targets
----------------
* One test per tag: Excellent, Good, Needs Review (borderline), Risky.
* One test per MISSING_METRIC_VALUE field: verifies that a missing secondary
  metric does not degrade the tag when all other metrics are excellent.
* min_mandatory_gap == MISSING_METRIC_VALUE forces Needs Review regardless
  of every other metric.
* Determinism: identical inputs produce identical outputs across 100 calls.

All metric fixtures are constructed inline so tests are self-contained and
do not depend on the scheduling engine.
"""
from __future__ import annotations

import sys
from pathlib import Path

import unittest
import pytest

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from ranking_settings import MISSING_METRIC_VALUE, ScheduleMetrics
from scheduling.qualityTagCalculator import (
    QualityTagCalculator,
    ScheduleQualityTag,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def make_metrics(
    *,
    schedule_id: int = 1,
    min_mandatory_gap: int,
    average_all_gap: float = 5.0,
    elective_collision_count: int = 0,
    mandatory_span: int = 10,
    max_exams_per_day: int = 2,
) -> ScheduleMetrics:
    """Build a ScheduleMetrics with explicit mandatory gap; others default to
    values that satisfy the Excellent threshold so individual tests can vary
    only the field under test."""
    return ScheduleMetrics(
        schedule_id=schedule_id,
        min_mandatory_gap=min_mandatory_gap,
        average_all_gap=average_all_gap,
        elective_collision_count=elective_collision_count,
        mandatory_span=mandatory_span,
        max_exams_per_day=max_exams_per_day,
    )


# ---------------------------------------------------------------------------
# One test per tag
# ---------------------------------------------------------------------------

class TestExcellentTag:
    """The Excellent tag is assigned when all metrics clearly exceed benchmarks."""

    def test_excellent_metrics_return_excellent_tag(self) -> None:
        """All metrics above Excellent thresholds → tag is Excellent."""
        calc = QualityTagCalculator()
        metrics = make_metrics(
            min_mandatory_gap=8,      # >= _GAP_EXCELLENT (7)
            mandatory_span=15,        # <= _SPAN_EXCELLENT (20)
            elective_collision_count=0,
            max_exams_per_day=2,      # <= _MAX_PER_DAY_EXCELLENT (3)
        )
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.EXCELLENT

    def test_excellent_explanation_mentions_min_gap(self) -> None:
        """Explanation includes the actual min_mandatory_gap value."""
        calc = QualityTagCalculator()
        metrics = make_metrics(min_mandatory_gap=9, mandatory_span=10)
        result = calc.calculate(metrics)
        assert "9d" in result.explanation

    def test_excellent_at_gap_threshold_boundary(self) -> None:
        """min_mandatory_gap == _GAP_EXCELLENT (7) still earns Excellent."""
        calc = QualityTagCalculator()
        metrics = make_metrics(
            min_mandatory_gap=QualityTagCalculator._GAP_EXCELLENT,
            mandatory_span=QualityTagCalculator._SPAN_EXCELLENT,
        )
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.EXCELLENT


class TestGoodTag:
    """The Good tag is assigned when metrics satisfy requirements with margin."""

    def test_good_metrics_return_good_tag(self) -> None:
        """min_gap in [4, 6], span in range → tag is Good."""
        calc = QualityTagCalculator()
        metrics = make_metrics(
            min_mandatory_gap=5,      # >= _GAP_GOOD (4), < _GAP_EXCELLENT (7)
            mandatory_span=25,        # <= _SPAN_GOOD (35)
            elective_collision_count=1,
            max_exams_per_day=4,      # <= _MAX_PER_DAY_GOOD (5)
        )
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.GOOD

    def test_good_explanation_mentions_min_gap(self) -> None:
        """Explanation includes the actual min_mandatory_gap value."""
        calc = QualityTagCalculator()
        metrics = make_metrics(min_mandatory_gap=4, mandatory_span=30)
        result = calc.calculate(metrics)
        assert "4d" in result.explanation

    def test_good_at_gap_boundary(self) -> None:
        """min_mandatory_gap == _GAP_GOOD (4) with good span → Good."""
        calc = QualityTagCalculator()
        metrics = make_metrics(
            min_mandatory_gap=QualityTagCalculator._GAP_GOOD,
            mandatory_span=20,
            elective_collision_count=0,
        )
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.GOOD

    def test_gap_7_but_span_too_large_returns_good_not_excellent(self) -> None:
        """min_gap >= 7 but mandatory_span > _SPAN_EXCELLENT → falls to Good."""
        calc = QualityTagCalculator()
        metrics = make_metrics(
            min_mandatory_gap=7,
            mandatory_span=QualityTagCalculator._SPAN_EXCELLENT + 1,  # 21
            elective_collision_count=0,
            max_exams_per_day=2,
        )
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.GOOD


class TestRiskyTag(unittest.TestCase):
    """The Risky tag fires when at least one metric violates a hard threshold."""

    def test_min_gap_1_returns_risky(self) -> None:
        """min_mandatory_gap of 1 day violates Req 2.1 → Risky."""
        calc = QualityTagCalculator()
        metrics = make_metrics(min_mandatory_gap=1)
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.RISKY

    def test_min_gap_zero_returns_risky(self) -> None:
        """A gap of 0 days (same-day exams) is more severe than gap=1
        and must also be classified as Risky (gap < _GAP_RISKY)."""
        metrics = make_metrics(min_mandatory_gap=0)
        result = QualityTagCalculator().calculate(metrics)
        self.assertEqual(result.tag, ScheduleQualityTag.RISKY)

    def test_min_gap_2_returns_risky(self) -> None:
        """min_mandatory_gap of 2 days is still below the 3-day minimum."""
        calc = QualityTagCalculator()
        metrics = make_metrics(min_mandatory_gap=2)
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.RISKY

    def test_risky_explanation_mentions_gap_value(self) -> None:
        """Explanation includes the actual gap that caused Risky."""
        calc = QualityTagCalculator()
        result = calc.calculate(make_metrics(min_mandatory_gap=1))
        assert "1 day(s)" in result.explanation

    def test_high_collision_count_returns_risky(self) -> None:
        """elective_collision_count > _COLLISION_RISKY (5) → Risky."""
        calc = QualityTagCalculator()
        metrics = make_metrics(
            min_mandatory_gap=5,
            elective_collision_count=QualityTagCalculator._COLLISION_RISKY + 1,
        )
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.RISKY

    def test_high_max_per_day_returns_risky(self) -> None:
        """max_exams_per_day > _MAX_PER_DAY_RISKY (6) → Risky."""
        calc = QualityTagCalculator()
        metrics = make_metrics(
            min_mandatory_gap=5,
            max_exams_per_day=QualityTagCalculator._MAX_PER_DAY_RISKY + 1,
        )
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.RISKY


class TestNeedsReviewTag:
    """Needs Review is returned for borderline or unclassifiable metrics."""

    def test_min_gap_missing_returns_needs_review(self) -> None:
        """MISSING_METRIC_VALUE for min_mandatory_gap → Needs Review."""
        calc = QualityTagCalculator()
        metrics = make_metrics(min_mandatory_gap=MISSING_METRIC_VALUE)
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.NEEDS_REVIEW

    def test_min_gap_exactly_3_returns_needs_review(self) -> None:
        """min_mandatory_gap == 3 barely meets Req 2.1 → Needs Review."""
        calc = QualityTagCalculator()
        metrics = make_metrics(
            min_mandatory_gap=3,
            mandatory_span=10,
            elective_collision_count=0,
            max_exams_per_day=2,
        )
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.NEEDS_REVIEW

    def test_needs_review_explanation_mentions_gap_3(self) -> None:
        """Explanation names the 3-day barely-meets-minimum condition."""
        calc = QualityTagCalculator()
        result = calc.calculate(make_metrics(min_mandatory_gap=3))
        assert "3" in result.explanation

    def test_span_above_good_threshold_with_ok_gap_returns_needs_review(self) -> None:
        """min_gap >= 4 but mandatory_span > _SPAN_GOOD (35) → Needs Review."""
        calc = QualityTagCalculator()
        metrics = make_metrics(
            min_mandatory_gap=5,
            mandatory_span=QualityTagCalculator._SPAN_GOOD + 1,  # 36
            elective_collision_count=0,
            max_exams_per_day=2,
        )
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.NEEDS_REVIEW


# ---------------------------------------------------------------------------
# MISSING_METRIC_VALUE per secondary metric
# (secondary = every metric except min_mandatory_gap)
# ---------------------------------------------------------------------------

class TestMissingSecondaryMetricsDoNotDegrade:
    """A missing secondary metric must not lower the tag below what the
    present metrics justify — missing means 'not applicable', not 'worst'."""

    def _excellent_base(self, **overrides: int | float) -> ScheduleMetrics:
        """Metrics that would be Excellent when no secondary metric is missing."""
        defaults = dict(
            min_mandatory_gap=8,
            average_all_gap=10.0,
            elective_collision_count=0,
            mandatory_span=15,
            max_exams_per_day=2,
        )
        defaults.update(overrides)
        return ScheduleMetrics(schedule_id=1, **defaults)  # type: ignore[arg-type]

    def test_missing_average_all_gap_still_excellent(self) -> None:
        """average_all_gap missing → other metrics are enough for Excellent."""
        calc = QualityTagCalculator()
        metrics = self._excellent_base(average_all_gap=MISSING_METRIC_VALUE)
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.EXCELLENT

    def test_missing_elective_collision_count_still_excellent(self) -> None:
        """elective_collision_count missing → treated as not applicable."""
        calc = QualityTagCalculator()
        metrics = self._excellent_base(
            elective_collision_count=MISSING_METRIC_VALUE
        )
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.EXCELLENT

    def test_missing_mandatory_span_still_excellent(self) -> None:
        """mandatory_span missing → span condition is skipped (not penalised)."""
        calc = QualityTagCalculator()
        metrics = self._excellent_base(mandatory_span=MISSING_METRIC_VALUE)
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.EXCELLENT

    def test_missing_max_exams_per_day_still_excellent(self) -> None:
        """max_exams_per_day missing → day-load condition is skipped."""
        calc = QualityTagCalculator()
        metrics = self._excellent_base(max_exams_per_day=MISSING_METRIC_VALUE)
        result = calc.calculate(metrics)
        assert result.tag is ScheduleQualityTag.EXCELLENT

    def test_missing_elective_collision_does_not_trigger_risky(self) -> None:
        """MISSING_METRIC_VALUE for collisions must not fire the Risky rule."""
        calc = QualityTagCalculator()
        # Force min_gap to be in the Good range so only collision could cause Risky.
        metrics = make_metrics(
            min_mandatory_gap=5,
            elective_collision_count=MISSING_METRIC_VALUE,
            mandatory_span=20,
            max_exams_per_day=2,
        )
        result = calc.calculate(metrics)
        # Should be Excellent (collision missing == OK, gap 5 < 7 misses Excellent gap)
        # Actually gap 5 < _GAP_EXCELLENT (7), span 20 == _SPAN_EXCELLENT → Good
        assert result.tag in (
            ScheduleQualityTag.EXCELLENT,
            ScheduleQualityTag.GOOD,
        )

    def test_missing_max_per_day_does_not_trigger_risky(self) -> None:
        """MISSING_METRIC_VALUE for max_per_day must not fire the Risky rule."""
        calc = QualityTagCalculator()
        metrics = make_metrics(
            min_mandatory_gap=5,
            max_exams_per_day=MISSING_METRIC_VALUE,
            mandatory_span=20,
            elective_collision_count=0,
        )
        result = calc.calculate(metrics)
        assert result.tag not in (ScheduleQualityTag.RISKY,)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """The same ScheduleMetrics must always produce the same QualityTagResult."""

    @pytest.mark.parametrize("gap", [1, 2, 3, 4, 5, 7, 8, 10])
    def test_same_result_on_repeated_calls(self, gap: int) -> None:
        """100 repeated calls with identical inputs return the same tag."""
        calc = QualityTagCalculator()
        metrics = make_metrics(min_mandatory_gap=gap, mandatory_span=15)
        first = calc.calculate(metrics)
        for _ in range(99):
            repeated = calc.calculate(metrics)
            assert repeated.tag is first.tag
            assert repeated.explanation == first.explanation

    def test_different_instances_produce_same_result(self) -> None:
        """Two separate QualityTagCalculator instances give the same result."""
        metrics = make_metrics(min_mandatory_gap=5, mandatory_span=20)
        result_a = QualityTagCalculator().calculate(metrics)
        result_b = QualityTagCalculator().calculate(metrics)
        assert result_a.tag is result_b.tag
        assert result_a.explanation == result_b.explanation
