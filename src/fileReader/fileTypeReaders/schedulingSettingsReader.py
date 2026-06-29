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
    #   <criterion> [ : desc ]
    ranking: min_mandatory_gap
    ranking: average_all_gap : desc

The parsed result is a small dataclass (``SchedulingSettingsBundle``) holding
two objects already used elsewhere in the codebase:

* ``SchedulingConstraintSettings`` (from ``constraint_settings.py``)
* ``RankingSettings`` (from ``ranking_settings.py``)

This keeps GUI and file-based flows interchangeable: SchedulingService can
consume either source identically.

Validation is delegated to the shared ``SchedulingSettingsValidator``
(SCRUM-143), the same service used by the GUI flow. This guarantees that a
settings file accepted here produces settings that are also accepted by the
GUI, and vice versa.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from application.settings_validator import SchedulingSettingsValidator
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

    Both objects are guaranteed to pass ``SchedulingSettingsValidator``
    (SCRUM-143): ``parse`` raises ``ValueError`` before returning a bundle
    that would fail validation. This is NOT guaranteed for the equivalent
    objects returned by ``CacheManager.get_constraint_settings()`` /
    ``get_ranking_settings()`` (SCRUM-144), which store whatever was last
    set without validating it. A caller treating both sources
    interchangeably must not assume "came from the cache" implies "already
    valid" — SchedulingService re-validates cache settings for this reason.
    """

    constraint_settings: SchedulingConstraintSettings
    ranking_settings: RankingSettings


# ---------------------------------------------------------------------------
# Default settings-file path (SCRUM-165)
#
# Mirrors the DEFAULT_COURSES_PATH / DEFAULT_EXAM_PERIODS_PATH /
# DEFAULT_PROGRAMS_PATH constants in application/schedulixApp.py. Unlike
# those three required inputs, the settings file is optional: SchedulixApp
# (SCRUM-166) is expected to fall back to this path, or to skip settings
# entirely (all-disabled constraints, no ranking), when the caller supplies
# neither a custom path nor this default.
# ---------------------------------------------------------------------------

# Resolved the same way as PROJECT_ROOT in schedulixApp.py: relative to this
# file's location, so PyCharm and terminal runs behave the same regardless
# of working directory.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_SETTINGS_PATH = (
    _PROJECT_ROOT
    / "data"
    / "examples"
    / "basic_course_example"
    / "settings.txt"
)


# ---------------------------------------------------------------------------
# Token tables (kept module-level for readability and easy extension)
# ---------------------------------------------------------------------------

# Truthy / falsy tokens accepted in the enabled column.
_TRUE_TOKENS = {"on", "true", "yes", "1", "enabled"}
_FALSE_TOKENS = {"off", "false", "no", "0", "disabled"}

# Ranking-direction tokens. Section 3 requires descending order.
_DESC_TOKENS = {"desc", "descending", "down", "-"}

_RANKING_PREFIX = "ranking:"


class SchedulingSettingsFileReader(
    BaseFileReader[SchedulingSettingsBundle]
):
    """Parses an optional Part 3 settings file into the shared model types.

    Validation is delegated to the shared ``SchedulingSettingsValidator``
    (SCRUM-143), so a settings file accepted here is guaranteed to be
    accepted by the GUI flow as well, and vice versa.
    """

    def __init__(
        self,
        validator: SchedulingSettingsValidator | None = None,
    ) -> None:
        """Create the reader.

        Args:
            validator: the shared SCRUM-143 validation service. A default
                instance is created when none is supplied so callers do not
                need to construct one themselves; tests can inject a fake.
        """
        self._validator = validator or SchedulingSettingsValidator()

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

        ranking_settings = RankingSettings(priority_list=ranking_preferences)

        # Delegate to the shared validator (SCRUM-143) so the file-based flow
        # enforces exactly the same rules as the GUI flow. Errors are
        # collected and re-raised as a single ValueError, matching the
        # line-level ValueError already raised for malformed lines above.
        validation_result = self._validator.validate(
            constraint_settings=constraint_settings,
            ranking_settings=ranking_settings,
        )
        if not validation_result.is_valid:
            raise ValueError(
                "Invalid scheduling settings:\n"
                + "\n".join(validation_result.error_messages)
            )

        return SchedulingSettingsBundle(
            constraint_settings=constraint_settings,
            ranking_settings=ranking_settings,
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
        """Parse a ``<criterion> [ : desc ]`` ranking line."""
        parts = [part.strip() for part in line.split(":")]
        if len(parts) not in (1, 2) or not parts[0]:
            raise ValueError(
                f"Line {line_number}: expected "
                f"'ranking: <criterion> [ : desc ]'."
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
        else:
            raise ValueError(
                f"Line {line_number}: ranking direction must be descending "
                f"per Section 3, got '{direction_token}'. Accepted: "
                f"{sorted(_DESC_TOKENS)}."
            )

        return RankingPreference(
            criterion=criterion,
            descending=descending,
        )


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
