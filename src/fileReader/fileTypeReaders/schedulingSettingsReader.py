"""Reader for the optional Part 3 scheduling-settings file (SCRUM-165).

The Version 1.0 file-based flow accepts three input files (courses, dates,
programs). Part 3 introduces a fourth, optional, configuration file that
carries the user's threshold-constraint settings (Reqs 2.1-2.5) and the
ranking-criteria priority list (Reqs 3.1-3.5).

The format is a flat, line-oriented UTF-8 text format, kept intentionally
close to the existing Version 1.0 input files:

    # Comments start with '#'. Blank lines are ignored.
    #
    # Threshold constraints (Section 2).
    # Each line:  <constraint_type> = <enabled>, <k>
    mandatory_gap_days              = on, 3
    any_course_gap_days             = off, 0
    elective_conflicts_per_program  = off, 0
    mandatory_span_days             = off, 0
    max_exams_per_day               = on, 2
    #
    # Ranking criteria (Section 3), in priority order, one per line:
    #   <criterion> [ : <direction> ]
    ranking: min_mandatory_gap
    ranking: average_all_gap : asc

The parsed result is a small dataclass (``SchedulingSettingsBundle``) holding
two objects already used elsewhere in the codebase:

* ``SchedulingConstraintSettings`` (from ``constraint_settings.py``)
* ``RankingSettings`` (from ``ranking_settings.py``)

This keeps GUI and file-based flows interchangeable: SchedulingService can
consume either source identically.

A minimal validation layer (positive-integer / non-negative-integer ranges,
ranking-criterion uniqueness) is applied inline. When the shared
``SchedulingSettingsValidator`` from SCRUM-143 lands, it will replace
``_validate_bundle`` without changing the public interface.
"""
from __future__ import annotations

from dataclasses import dataclass

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from fileReader.baseFileReader import BaseFileReader
from ranking_settings import (
    RankingCriterion,
    RankingPreference,
    RankingSettings,
)


# ---------------------------------------------------------------------------
# Public bundle returned by the reader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SchedulingSettingsBundle:
    """
    Aggregates the two settings objects parsed from one settings file.

    Returned by ``SchedulingSettingsFileReader.parse`` so the caller receives
    the exact same model types used by the GUI flow (no parallel models).
    """

    constraint_settings: SchedulingConstraintSettings
    ranking_settings: RankingSettings


# ---------------------------------------------------------------------------
# Token tables (kept module-level for readability and easy extension)
# ---------------------------------------------------------------------------

# Truthy / falsy tokens accepted in the enabled column.
_TRUE_TOKENS = {"on", "true", "yes", "1", "enabled"}
_FALSE_TOKENS = {"off", "false", "no", "0", "disabled"}

# Ranking-direction tokens. Default is descending, matching ranking_settings.py.
_DESC_TOKENS = {"desc", "descending", "down", "-"}
_ASC_TOKENS = {"asc", "ascending", "up", "+"}

# Constraints whose k must be a strictly-positive integer per Reqs 2.1, 2.2,
# 2.4, 2.5. Req 2.3 (elective collisions) allows k = 0.
_POSITIVE_K_REQUIRED = {
    ThresholdConstraintType.mandatory_gap_days,
    ThresholdConstraintType.any_course_gap_days,
    ThresholdConstraintType.mandatory_span_days,
    ThresholdConstraintType.max_exams_per_day,
}

_RANKING_PREFIX = "ranking:"


class SchedulingSettingsFileReader(
    BaseFileReader[SchedulingSettingsBundle]
):
    """Parses an optional Part 3 settings file into the shared model types."""

    def parse(
        self,
        content: str,
    ) -> SchedulingSettingsBundle:
        """
        Convert raw file content into a ``SchedulingSettingsBundle``.

        Lines beginning with ``#`` and blank lines are ignored. Constraint
        lines and ranking lines may appear in any order; only one entry per
        constraint type and per ranking criterion is allowed.
        """
        # Start from "every constraint disabled" — the default that preserves
        # Version 2.0 generation behaviour when the file omits a constraint.
        constraint_settings = (
            SchedulingConstraintSettings.default_configuration()
        )

        ranking_preferences: list[RankingPreference] = []
        seen_ranking: set[RankingCriterion] = set()
        seen_constraints: set[ThresholdConstraintType] = set()

        for line_number, raw_line in enumerate(
            content.splitlines(),
            start=1,
        ):
            line = self._strip_comment(raw_line).strip()
            if not line:
                continue

            if line.lower().startswith(_RANKING_PREFIX):
                preference = self._parse_ranking_line(
                    line[len(_RANKING_PREFIX):].strip(),
                    line_number,
                )
                if preference.criterion in seen_ranking:
                    raise ValueError(
                        f"Line {line_number}: ranking criterion "
                        f"'{preference.criterion.value}' is declared twice."
                    )
                seen_ranking.add(preference.criterion)
                ranking_preferences.append(preference)
                continue

            constraint_type, setting = self._parse_constraint_line(
                line,
                line_number,
            )
            if constraint_type in seen_constraints:
                raise ValueError(
                    f"Line {line_number}: constraint "
                    f"'{constraint_type.value}' is declared twice."
                )
            seen_constraints.add(constraint_type)
            constraint_settings.constraints[constraint_type] = setting

        # Minimal validation. Will be replaced by SchedulingSettingsValidator
        # from SCRUM-143 once that ticket lands.
        self._validate_bundle(constraint_settings, ranking_preferences)

        return SchedulingSettingsBundle(
            constraint_settings=constraint_settings,
            ranking_settings=RankingSettings(
                priority_list=ranking_preferences,
            ),
        )

    # ------------------------------------------------------------------
    # Line-level parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_comment(raw_line: str) -> str:
        """Drop any trailing ``#`` comment from a single line."""
        comment_index = raw_line.find("#")
        if comment_index == -1:
            return raw_line
        return raw_line[:comment_index]

    @staticmethod
    def _parse_constraint_line(
        line: str,
        line_number: int,
    ) -> tuple[ThresholdConstraintType, ThresholdConstraintSetting]:
        """Parse a ``name = enabled, k`` constraint line."""
        if "=" not in line:
            raise ValueError(
                f"Line {line_number}: expected 'name = enabled, k' "
                f"or 'ranking: <criterion>', got: {line!r}"
            )

        name_part, value_part = line.split("=", 1)
        constraint_name = name_part.strip().lower()

        try:
            constraint_type = ThresholdConstraintType(constraint_name)
        except ValueError:
            raise ValueError(
                f"Line {line_number}: unknown constraint name "
                f"'{constraint_name}'. Accepted: "
                f"{[t.value for t in ThresholdConstraintType]}."
            ) from None

        parts = [part.strip() for part in value_part.split(",")]
        if len(parts) != 2:
            raise ValueError(
                f"Line {line_number}: expected '<enabled>, <k>' "
                f"after '=', got: {value_part!r}"
            )

        enabled_token, k_token = parts
        enabled = _parse_bool(enabled_token, line_number)
        k = _parse_int(k_token, line_number)

        return constraint_type, ThresholdConstraintSetting(
            enabled=enabled,
            k=k,
        )

    @staticmethod
    def _parse_ranking_line(
        line: str,
        line_number: int,
    ) -> RankingPreference:
        """Parse a ``<criterion> [ : <direction> ]`` ranking line."""
        parts = [part.strip() for part in line.split(":")]
        if len(parts) not in (1, 2) or not parts[0]:
            raise ValueError(
                f"Line {line_number}: expected "
                f"'ranking: <criterion> [ : <direction> ]'."
            )

        criterion_token = parts[0].lower()
        try:
            criterion = RankingCriterion(criterion_token)
        except ValueError:
            raise ValueError(
                f"Line {line_number}: unknown ranking criterion "
                f"'{criterion_token}'. Accepted: "
                f"{[c.value for c in RankingCriterion]}."
            ) from None

        if len(parts) == 1:
            return RankingPreference(criterion=criterion)

        direction_token = parts[1].lower()
        if direction_token in _DESC_TOKENS:
            descending = True
        elif direction_token in _ASC_TOKENS:
            descending = False
        else:
            raise ValueError(
                f"Line {line_number}: unknown ranking direction "
                f"'{direction_token}'. Accepted: "
                f"{sorted(_DESC_TOKENS | _ASC_TOKENS)}."
            )

        return RankingPreference(
            criterion=criterion,
            descending=descending,
        )

    # ------------------------------------------------------------------
    # Minimal validation (to be replaced by SCRUM-143)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_bundle(
        constraint_settings: SchedulingConstraintSettings,
        ranking_preferences: list[RankingPreference],
    ) -> None:
        """
        Reject invalid combinations before generation can see them.

        This is intentionally a small subset of the rules that the shared
        ``SchedulingSettingsValidator`` (SCRUM-143) will enforce; it lives
        here only so the reader does not pass obviously invalid data into
        the engine while SCRUM-143 is still pending.
        """
        for constraint_type, setting in constraint_settings.constraints.items():
            if not setting.enabled:
                continue

            if setting.k < 0:
                raise ValueError(
                    f"Constraint '{constraint_type.value}' requires k >= 0, "
                    f"got {setting.k}."
                )

            if (
                constraint_type in _POSITIVE_K_REQUIRED
                and setting.k <= 0
            ):
                raise ValueError(
                    f"Constraint '{constraint_type.value}' requires k > 0 "
                    f"when enabled, got {setting.k}."
                )

        # RankingSettings.__post_init__ already rejects duplicates, so this
        # is a belt-and-braces guard for clearer file-line error messages
        # which the reader emits during parsing.
        seen: set[RankingCriterion] = set()
        for preference in ranking_preferences:
            if preference.criterion in seen:
                raise ValueError(
                    "Duplicate ranking criterion in settings file: "
                    f"'{preference.criterion.value}'."
                )
            seen.add(preference.criterion)


# ---------------------------------------------------------------------------
# Small parsing helpers (module-private)
# ---------------------------------------------------------------------------


def _parse_bool(
    token: str,
    line_number: int,
) -> bool:
    """Convert one enabled/disabled token to a Python bool."""
    lowered = token.strip().lower()
    if lowered in _TRUE_TOKENS:
        return True
    if lowered in _FALSE_TOKENS:
        return False
    raise ValueError(
        f"Line {line_number}: expected on/off (or true/false, yes/no, 1/0), "
        f"got {token!r}."
    )


def _parse_int(
    token: str,
    line_number: int,
) -> int:
    """Convert one numeric token to an int, rejecting non-numeric input."""
    stripped = token.strip()
    try:
        return int(stripped)
    except ValueError:
        raise ValueError(
            f"Line {line_number}: expected an integer value, "
            f"got {token!r}."
        ) from None
