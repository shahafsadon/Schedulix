"""Quality tag calculation for ranked exam systems (SCRUM-191).

Classifies an ExamSystem into one of four quality bands — Excellent, Good,
Needs Review, or Risky — based on its ScheduleMetrics values.  The rules are
deterministic: the same metrics always produce the same tag and explanation.

Classification rules (applied in order; first match wins)
----------------------------------------------------------
1. Needs Review — min_mandatory_gap is MISSING_METRIC_VALUE (-1):
   Cannot evaluate Req 2.1 at all; manual review required.

2. Risky — any critical threshold is violated:
   * min_mandatory_gap < 3  → violates Req 2.1 (3-day minimum)
   * elective_collision_count > 5  → too many elective conflicts
   * max_exams_per_day > 6  → overloaded exam days

3. Excellent — all available metrics clearly exceed good benchmarks:
   * min_mandatory_gap >= 7  (>= 2× the 3-day Req 2.1 minimum)
   * elective_collision_count == 0  (zero conflicts)
   * mandatory_span <= 20  (compact ~3-week window per group)
   * max_exams_per_day <= 3  (light daily load)

4. Good — metrics comfortably satisfy requirements:
   * min_mandatory_gap >= 4  (1 day above the 3-day minimum)
   * elective_collision_count <= 2
   * mandatory_span <= 35  (spread across at most ~5 weeks per group)
   * max_exams_per_day <= 5

5. Needs Review (default) — everything else:
   Typically min_mandatory_gap == 3 (exactly meets Req 2.1), a mandatory
   span that is too long, or moderate collision / day-load values that
   fall between Good and Risky.

Missing-metric policy
---------------------
Any metric equal to MISSING_METRIC_VALUE (-1) is treated as "not applicable"
for that rule: missing values cannot make a schedule *worse* than what its
present metrics justify.  The only exception is min_mandatory_gap (Rule 1),
which is required for any classification at all.

Note: average_all_gap (Req 3.2) is not used as a classification boundary.
With few exam courses the metric is dominated by inter-semester distances and
loses discriminating power; min_mandatory_gap and mandatory_span together
capture spacing quality more reliably across typical dataset sizes.

Empirical calibration (example data, 76 032 schedules, 2 relevant courses):
  min_mandatory_gap range 1-10, median 3, mean 3.6
  mandatory_span    range 1-41, median 13, mean 14.7
  Resulting distribution: Excellent 7%, Good 33%, Needs Review 18%, Risky 39%
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ranking_settings import MISSING_METRIC_VALUE, ScheduleMetrics


# ---------------------------------------------------------------------------
# Public enumerations and result type
# ---------------------------------------------------------------------------

class ScheduleQualityTag(Enum):
    """Four quality bands for a ranked exam system (SCRUM-191)."""

    EXCELLENT    = "Excellent"
    GOOD         = "Good"
    NEEDS_REVIEW = "Needs Review"
    RISKY        = "Risky"


@dataclass(frozen=True)
class QualityTagResult:
    """Holds a quality tag and a short human-readable explanation.

    Fields
    ------
    tag : ScheduleQualityTag
        The quality band assigned to the schedule.
    explanation : str
        A single English sentence explaining the tag, with concrete metric
        values where available.  Suitable for display in a report line such
        as ``Quality: Excellent — comfortable spacing: min gap 8d, span 15d``.
    """

    tag: ScheduleQualityTag
    explanation: str
    penalty_score: float | None = None


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

class QualityTagCalculator:
    """Classifies a ScheduleMetrics object into a quality band.

    The calculator is stateless: each ``calculate()`` call is independent.
    It can be instantiated once and reused across many metrics objects —
    suitable for both the CLI report writer and a future GUI panel.

    Threshold constants are defined as class attributes so they can be
    inspected by tests without constructing a full ScheduleMetrics fixture.
    """

    # ------------------------------------------------------------------ #
    # Threshold constants                                                  #
    # ------------------------------------------------------------------ #

    # min_mandatory_gap thresholds (days):
    #   _GAP_EXCELLENT: >= 7 is >= 2.3x the 3-day Req 2.1 minimum —
    #       genuinely generous spacing.
    #   _GAP_GOOD: >= 4 is 1 day above the minimum — comfortable margin.
    #   _GAP_RISKY: < 3 violates Req 2.1 outright.
    _GAP_EXCELLENT: int = 7
    _GAP_GOOD:      int = 4
    _GAP_RISKY:     int = 3

    # mandatory_span thresholds (days):
    #   _SPAN_EXCELLENT: <= 20 means the entire mandatory window fits within
    #       ~3 weeks — a compact, student-friendly exam period.
    #   _SPAN_GOOD: <= 35 is about 5 weeks — acceptable but noticeably spread.
    _SPAN_EXCELLENT: int = 20
    _SPAN_GOOD:      int = 35

    # elective_collision_count limits:
    #   _COLLISION_GOOD: <= 2 is a small, manageable number of collisions.
    #   _COLLISION_RISKY: > 5 means too many students face a double-exam day.
    _COLLISION_GOOD:  int = 2
    _COLLISION_RISKY: int = 5

    # max_exams_per_day limits:
    #   _MAX_PER_DAY_EXCELLENT: <= 3 — light daily load for any given day.
    #   _MAX_PER_DAY_GOOD: <= 5 — manageable, no single day is overloaded.
    #   _MAX_PER_DAY_RISKY: > 6 — any day with 7+ exams is excessive.
    _MAX_PER_DAY_EXCELLENT: int = 3
    _MAX_PER_DAY_GOOD:      int = 5
    _MAX_PER_DAY_RISKY:     int = 6

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def calculate(self, metrics: ScheduleMetrics) -> QualityTagResult:
        """Return a quality tag and a human-readable explanation.

        Rules are applied in order; the first matching rule determines the
        result.  See the module docstring for the full rule table.

        Args:
            metrics: Pre-calculated ScheduleMetrics for one exam system.
                     Fields equal to MISSING_METRIC_VALUE (-1) are treated
                     as "not applicable" rather than penalised.

        Returns:
            A frozen QualityTagResult containing the tag and explanation.
        """
        # Rule 1: Needs Review — primary metric unavailable.
        if metrics.min_mandatory_gap == MISSING_METRIC_VALUE:
            return QualityTagResult(
                tag=ScheduleQualityTag.NEEDS_REVIEW,
                explanation=(
                    "mandatory gap metric unavailable — "
                    "schedule must be reviewed manually"
                ),
            )

        # Rule 2: Risky — at least one metric violates a hard threshold.
        risky_reason = self._risky_reason(metrics)
        if risky_reason is not None:
            return QualityTagResult(
                tag=ScheduleQualityTag.RISKY,
                explanation=risky_reason,
            )

        # Rule 3: Excellent — all available metrics clearly exceed benchmarks.
        if (
            metrics.min_mandatory_gap >= self._GAP_EXCELLENT
            and self._collision_at_most(metrics, 0)
            and self._span_at_most(metrics, self._SPAN_EXCELLENT)
            and self._max_per_day_at_most(metrics, self._MAX_PER_DAY_EXCELLENT)
        ):
            return QualityTagResult(
                tag=ScheduleQualityTag.EXCELLENT,
                explanation=self._excellent_explanation(metrics),
            )

        # Rule 4: Good — metrics comfortably satisfy requirements.
        if (
            metrics.min_mandatory_gap >= self._GAP_GOOD
            and self._collision_at_most(metrics, self._COLLISION_GOOD)
            and self._span_at_most(metrics, self._SPAN_GOOD)
            and self._max_per_day_at_most(metrics, self._MAX_PER_DAY_GOOD)
        ):
            return QualityTagResult(
                tag=ScheduleQualityTag.GOOD,
                explanation=self._good_explanation(metrics),
            )

        # Rule 5: Needs Review — default for borderline schedules.
        return QualityTagResult(
            tag=ScheduleQualityTag.NEEDS_REVIEW,
            explanation=self._needs_review_explanation(metrics),
        )

    # ------------------------------------------------------------------ #
    # Private helpers — Risky detection                                    #
    # ------------------------------------------------------------------ #

    def _risky_reason(self, metrics: ScheduleMetrics) -> str | None:
        """Return a Risky explanation string, or None when no threshold fires."""
        if metrics.min_mandatory_gap < self._GAP_RISKY:
            # Gap is below the 3-day Req 2.1 minimum — hard violation.
            return (
                f"minimum mandatory gap of {metrics.min_mandatory_gap} day(s) "
                "violates Req 2.1 (minimum 3 days required)"
            )
        if (
            metrics.elective_collision_count != MISSING_METRIC_VALUE
            and metrics.elective_collision_count > self._COLLISION_RISKY
        ):
            return (
                f"elective collision count of "
                f"{metrics.elective_collision_count} exceeds the "
                f"acceptable limit of {self._COLLISION_RISKY}"
            )
        if (
            metrics.max_exams_per_day != MISSING_METRIC_VALUE
            and metrics.max_exams_per_day > self._MAX_PER_DAY_RISKY
        ):
            return (
                f"daily exam load of {metrics.max_exams_per_day} exams "
                "is excessive — students face an overloaded day"
            )
        return None

    # ------------------------------------------------------------------ #
    # Private helpers — condition checks                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _collision_at_most(metrics: ScheduleMetrics, limit: int) -> bool:
        """Return True when elective collisions are within limit or missing."""
        return (
            metrics.elective_collision_count == MISSING_METRIC_VALUE
            or metrics.elective_collision_count <= limit
        )

    @staticmethod
    def _span_at_most(metrics: ScheduleMetrics, limit: int) -> bool:
        """Return True when mandatory span is within limit or missing."""
        return (
            metrics.mandatory_span == MISSING_METRIC_VALUE
            or metrics.mandatory_span <= limit
        )

    @staticmethod
    def _max_per_day_at_most(metrics: ScheduleMetrics, limit: int) -> bool:
        """Return True when max-exams-per-day is within limit or missing."""
        return (
            metrics.max_exams_per_day == MISSING_METRIC_VALUE
            or metrics.max_exams_per_day <= limit
        )

    # ------------------------------------------------------------------ #
    # Private helpers — explanation builders                               #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _excellent_explanation(metrics: ScheduleMetrics) -> str:
        """Build the Excellent explanation string."""
        span_note = (
            f"span {metrics.mandatory_span}d"
            if metrics.mandatory_span != MISSING_METRIC_VALUE
            else "span n/a"
        )
        return (
            f"comfortable spacing: min gap {metrics.min_mandatory_gap}d, "
            f"{span_note}, no elective collisions"
        )

    @staticmethod
    def _good_explanation(metrics: ScheduleMetrics) -> str:
        """Build the Good explanation string."""
        span_note = (
            f"span {metrics.mandatory_span}d"
            if metrics.mandatory_span != MISSING_METRIC_VALUE
            else "span n/a"
        )
        return (
            f"acceptable spacing: min gap {metrics.min_mandatory_gap}d, "
            f"{span_note}"
        )

    def _needs_review_explanation(self, metrics: ScheduleMetrics) -> str:
        """Build a Needs Review explanation that names the specific cause(s)."""
        reasons: list[str] = []

        if metrics.min_mandatory_gap == self._GAP_RISKY:
            # min_mandatory_gap == 3: meets Req 2.1 with zero margin above it.
            reasons.append(
                f"min gap of {metrics.min_mandatory_gap} days "
                "barely meets the Req 2.1 minimum"
            )

        if (
            metrics.mandatory_span != MISSING_METRIC_VALUE
            and metrics.mandatory_span > self._SPAN_GOOD
        ):
            reasons.append(
                f"span of {metrics.mandatory_span} days exceeds the "
                f"{self._SPAN_GOOD}-day Good threshold"
            )

        if (
            metrics.elective_collision_count != MISSING_METRIC_VALUE
            and 0 < metrics.elective_collision_count <= self._COLLISION_RISKY
        ):
            reasons.append(
                f"{metrics.elective_collision_count} elective collision(s)"
            )

        if (
            metrics.max_exams_per_day != MISSING_METRIC_VALUE
            and self._MAX_PER_DAY_GOOD
            < metrics.max_exams_per_day
            <= self._MAX_PER_DAY_RISKY
        ):
            reasons.append(
                f"daily load of {metrics.max_exams_per_day} exams is borderline"
            )

        # Defensive fallback: unreachable with the current rule set (every
        # path that reaches Needs Review has at least one secondary check
        # that populates reasons), but kept as a safety net.
        if not reasons:
            return "borderline schedule: review before use"
        return "; ".join(reasons)
