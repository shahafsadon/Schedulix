"""
settings_validator.py
~~~~~~~~~~~~~~~~~~~~~
Scheduling Settings Validation Service (SCRUM-143).

Provides a single, UI-agnostic validation boundary for both
``SchedulingConstraintSettings`` and ``RankingSettings``.  The service is
intentionally free of any GUI dependencies (no customtkinter imports) so it
can be invoked identically from the GUI presenter layer and from a CLI or
batch runner.

Design overview
---------------
Validation is performed in two distinct phases, mirroring how the settings
objects are consumed downstream:

1. **Constraint validation** — checks every ``ThresholdConstraintSetting``
   that is enabled: verifies that the threshold value ``k`` satisfies the
   requirement-specific lower bound and that the settings dict contains
   entries for all known ``ThresholdConstraintType`` members.

2. **Ranking validation** — checks the ``RankingSettings.priority_list`` for
   duplicate criteria, unknown / None entries, and the Section 3 requirement
   that every ranking criterion is sorted descending.

Each individual problem is represented by a ``ValidationError`` value object
that pinpoints the exact field and explains the issue.  All errors are
collected before returning, so a single call surfaces every problem rather
than stopping at the first.

The top-level result is a ``ValidationResult`` that aggregates the error list
and exposes convenience helpers (``is_valid``, ``error_messages``).

Usage example
-------------
::

    from application.settings_validator import SchedulingSettingsValidator
    from constraint_settings import SchedulingConstraintSettings
    from ranking_settings import RankingSettings

    validator = SchedulingSettingsValidator()
    result = validator.validate(
        constraint_settings=my_constraint_settings,
        ranking_settings=my_ranking_settings,
    )

    if not result.is_valid:
        for message in result.error_messages:
            print(message)
    else:
        # Safe to pass settings to the generator.
        ...
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from constraint_settings import SchedulingConstraintSettings, ThresholdConstraintType
from ranking_settings import RankingCriterion, RankingSettings


# ---------------------------------------------------------------------------
# Minimum allowed threshold values for enabled constraints.
# Gap/span/day-count requirements use positive k values. Req 2.3 is different:
# it limits elective collisions, and the requirements define k as non-negative.
# ---------------------------------------------------------------------------
_DEFAULT_MIN_K: int = 1
_MIN_K_BY_CONSTRAINT: dict[ThresholdConstraintType, int] = {
    ThresholdConstraintType.elective_conflicts_per_program: 0,
}

# Human-readable labels for each ThresholdConstraintType used in error
# messages so the error text is immediately actionable.
_CONSTRAINT_LABELS: dict[ThresholdConstraintType, str] = {
    ThresholdConstraintType.mandatory_gap_days: "Mandatory Gap Days (Req 2.1)",
    ThresholdConstraintType.any_course_gap_days: "Any Course Gap Days (Req 2.2)",
    ThresholdConstraintType.elective_conflicts_per_program: "Elective Conflicts Per Program (Req 2.3)",
    ThresholdConstraintType.mandatory_span_days: "Mandatory Span Days (Req 2.4)",
    ThresholdConstraintType.max_exams_per_day: "Max Exams Per Day (Req 2.5)",
}


# ---------------------------------------------------------------------------
# Error severity
# ---------------------------------------------------------------------------

class ValidationSeverity(Enum):
    """Indicates how serious a validation problem is.

    * ``ERROR`` — the settings are definitively invalid and the engine must
      not be started.
    * ``WARNING`` — the settings are technically usable but may produce
      unexpected results (reserved for future use; none are emitted today).
    """

    ERROR = "error"
    WARNING = "warning"


# ---------------------------------------------------------------------------
# ValidationError value object
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationError:
    """Describes one specific validation problem.

    Each instance is immutable so it can be safely passed across layer
    boundaries without defensive copying.

    Fields
    ------
    field_path : str
        Dot-separated path that identifies the exact setting that failed,
        e.g. ``"constraint_settings.mandatory_gap_days.k"`` or
        ``"ranking_settings.priority_list[1].criterion"``.
    message : str
        Human-readable explanation of the problem that is safe to display
        in any UI or log output.
    severity : ValidationSeverity
        Indicates whether this is a hard error or a softer warning.
    """

    field_path: str
    message: str
    severity: ValidationSeverity = ValidationSeverity.ERROR

    def __str__(self) -> str:
        return f"[{self.severity.value.upper()}] {self.field_path}: {self.message}"


# ---------------------------------------------------------------------------
# ValidationResult value object
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationResult:
    """Aggregates every ``ValidationError`` found during one validation run.

    Constructing it with an empty ``errors`` list means the settings are
    valid; calling code should check ``is_valid`` rather than inspecting
    the list length directly.

    Fields
    ------
    errors : tuple[ValidationError, ...]
        All problems detected in this run, ordered by discovery.  An empty
        tuple means validation passed.
    """

    errors: tuple[ValidationError, ...] = field(default_factory=tuple)

    # ``dataclass(frozen=True)`` requires hashable default_factory values.
    # We use a plain tuple (immutable) instead of a list.

    @property
    def is_valid(self) -> bool:
        """``True`` when no errors of any severity were found."""
        return len(self.errors) == 0

    @property
    def has_errors(self) -> bool:
        """``True`` when at least one ERROR-severity problem was found."""
        return any(
            e.severity == ValidationSeverity.ERROR for e in self.errors
        )

    @property
    def error_messages(self) -> list[str]:
        """Return a plain list of human-readable error strings.

        Useful for logging or displaying in any UI without coupling the
        caller to the ``ValidationError`` type.
        """
        return [str(e) for e in self.errors]

    @classmethod
    def ok(cls) -> ValidationResult:
        """Factory for the trivially valid result."""
        return cls(errors=())

    @classmethod
    def from_errors(
        cls,
        errors: Sequence[ValidationError],
    ) -> ValidationResult:
        """Factory that wraps an error sequence into a frozen tuple."""
        return cls(errors=tuple(errors))


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class SchedulingSettingsValidator:
    """Validates ``SchedulingConstraintSettings`` and ``RankingSettings``.

    The validator is stateless: all context is supplied through method
    arguments.  A single instance can safely be shared across threads or
    reused between validation calls.

    Both ``validate_constraint_settings`` and ``validate_ranking_settings``
    are available as independent entry-points when only one half of the
    settings needs checking.  The combined ``validate`` method is the
    recommended entry-point for the main application flow.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(
        self,
        constraint_settings: SchedulingConstraintSettings | None = None,
        ranking_settings: RankingSettings | None = None,
    ) -> ValidationResult:
        """Run all applicable validation checks and return a combined result.

        Either argument may be ``None`` to skip that phase.  Passing both
        ``None`` returns a trivially valid result.

        Parameters
        ----------
        constraint_settings:
            The threshold-constraint configuration to validate.  Pass
            ``None`` to skip constraint validation.
        ranking_settings:
            The ranking priority profile to validate.  Pass ``None`` to
            skip ranking validation.

        Returns
        -------
        ValidationResult
            A frozen result aggregating every ``ValidationError`` found.
            ``result.is_valid`` is ``True`` when the combined error list
            is empty.
        """
        errors: list[ValidationError] = []

        if constraint_settings is not None:
            errors.extend(
                self._check_constraint_settings(constraint_settings)
            )

        if ranking_settings is not None:
            errors.extend(
                self._check_ranking_settings(ranking_settings)
            )

        if not errors:
            return ValidationResult.ok()

        return ValidationResult.from_errors(errors)

    def validate_constraint_settings(
        self,
        constraint_settings: SchedulingConstraintSettings,
    ) -> ValidationResult:
        """Validate only the constraint settings.

        Convenience wrapper around ``validate`` for callers that do not hold
        a ``RankingSettings`` object at the point of validation.
        """
        return self.validate(constraint_settings=constraint_settings)

    def validate_ranking_settings(
        self,
        ranking_settings: RankingSettings,
    ) -> ValidationResult:
        """Validate only the ranking settings.

        Convenience wrapper around ``validate`` for callers that do not hold
        a ``SchedulingConstraintSettings`` object at the point of validation.
        """
        return self.validate(ranking_settings=ranking_settings)

    # ------------------------------------------------------------------
    # Constraint-settings checks
    # ------------------------------------------------------------------

    def _check_constraint_settings(
        self,
        settings: SchedulingConstraintSettings,
    ) -> list[ValidationError]:
        """Return all errors found in ``settings``.

        Checks performed (in order):
        1. The ``constraints`` dict is not ``None``.
        2. Every ``ThresholdConstraintType`` member has a corresponding entry.
        3. For each enabled constraint the ``k`` value is an integer >= 1.
        """
        errors: list[ValidationError] = []

        # Guard: the constraints dict itself must not be None.
        if settings.constraints is None:
            errors.append(
                ValidationError(
                    field_path="constraint_settings.constraints",
                    message=(
                        "The constraints mapping is None. "
                        "Use SchedulingConstraintSettings.default_configuration() "
                        "to obtain a safe starting state."
                    ),
                )
            )
            # Cannot proceed with per-entry checks; return early.
            return errors

        # Check 1: ensure every known constraint type has a settings entry.
        for constraint_type in ThresholdConstraintType:
            if constraint_type not in settings.constraints:
                errors.append(
                    ValidationError(
                        field_path=(
                            f"constraint_settings.constraints"
                            f"[{constraint_type.value}]"
                        ),
                        message=(
                            f"Missing entry for constraint "
                            f"'{_CONSTRAINT_LABELS[constraint_type]}'. "
                            "All five ThresholdConstraintType members must be present."
                        ),
                    )
                )

        # Check 2: for each enabled constraint, validate the k value.
        for constraint_type, setting in settings.constraints.items():
            if setting is None:
                errors.append(
                    ValidationError(
                        field_path=(
                            f"constraint_settings.constraints"
                            f"[{constraint_type.value}]"
                        ),
                        message=(
                            f"Setting for '{_CONSTRAINT_LABELS.get(constraint_type, constraint_type.value)}' "
                            "is None; expected a ThresholdConstraintSetting instance."
                        ),
                    )
                )
                continue

            if not setting.enabled:
                # Disabled constraints are ignored by the engine; their k
                # value is irrelevant and is intentionally not validated.
                continue

            errors.extend(
                self._check_threshold_k(
                    constraint_type=constraint_type,
                    k=setting.k,
                )
            )

        return errors

    def _check_threshold_k(
        self,
        constraint_type: ThresholdConstraintType,
        k: object,
    ) -> list[ValidationError]:
        """Validate the ``k`` threshold for one enabled constraint."""
        errors: list[ValidationError] = []
        label = _CONSTRAINT_LABELS.get(constraint_type, constraint_type.value)
        field_path = (
            f"constraint_settings.constraints[{constraint_type.value}].k"
        )

        # Type check: k must be an int (bool is a subclass of int in Python;
        # we exclude it explicitly because True/False are not meaningful
        # scheduling thresholds).
        if not isinstance(k, int) or isinstance(k, bool):
            errors.append(
                ValidationError(
                    field_path=field_path,
                    message=(
                        f"Threshold k for '{label}' must be an integer, "
                        f"got {type(k).__name__!r} with value {k!r}."
                    ),
                )
            )
            return errors  # Range check is meaningless without a valid type.

        min_k = _MIN_K_BY_CONSTRAINT.get(constraint_type, _DEFAULT_MIN_K)

        # Range check: k must satisfy the requirement-specific lower bound.
        if k < min_k:
            errors.append(
                ValidationError(
                    field_path=field_path,
                    message=(
                        f"Threshold k for '{label}' must be >= {min_k} "
                        f"when the constraint is enabled, got {k}."
                    ),
                )
            )

        return errors

    # ------------------------------------------------------------------
    # Ranking-settings checks
    # ------------------------------------------------------------------

    def _check_ranking_settings(
        self,
        settings: RankingSettings,
    ) -> list[ValidationError]:
        """Return all errors found in ``settings``.

        Checks performed (in order):
        1. ``priority_list`` is not ``None``.
        2. Each entry in ``priority_list`` is not ``None``.
        3. Each entry's ``criterion`` is a valid ``RankingCriterion`` member.
        4. Each entry uses descending order.
        5. No ``RankingCriterion`` appears more than once (duplicate check).

        Note: ``RankingSettings.__post_init__`` already raises ``ValueError``
        on duplicates at construction time, but this validator deliberately
        re-checks the live object state so callers that mutate the list after
        construction are also protected.
        """
        errors: list[ValidationError] = []

        if settings.priority_list is None:
            errors.append(
                ValidationError(
                    field_path="ranking_settings.priority_list",
                    message=(
                        "priority_list is None. "
                        "Pass an empty list to represent zero active ranking criteria."
                    ),
                )
            )
            return errors

        seen_criteria: set[RankingCriterion] = set()

        for index, preference in enumerate(settings.priority_list):
            base_path = f"ranking_settings.priority_list[{index}]"

            # Entry-level None guard.
            if preference is None:
                errors.append(
                    ValidationError(
                        field_path=base_path,
                        message=(
                            f"Priority entry at position {index} is None; "
                            "each entry must be a RankingPreference instance."
                        ),
                    )
                )
                continue

            # Criterion must be a known RankingCriterion enum member.
            criterion = preference.criterion
            if not isinstance(criterion, RankingCriterion):
                errors.append(
                    ValidationError(
                        field_path=f"{base_path}.criterion",
                        message=(
                            f"criterion at position {index} is {criterion!r}, "
                            f"which is not a valid RankingCriterion member. "
                            f"Valid values: "
                            f"{[c.value for c in RankingCriterion]}."
                        ),
                    )
                )
                continue

            if getattr(preference, "descending", None) is not True:
                errors.append(
                    ValidationError(
                        field_path=f"{base_path}.descending",
                        message=(
                            "Ranking direction must be descending for every "
                            "criterion per Section 3."
                        ),
                    )
                )

            # Duplicate criterion check.
            if criterion in seen_criteria:
                errors.append(
                    ValidationError(
                        field_path=f"{base_path}.criterion",
                        message=(
                            f"Duplicate ranking criterion '{criterion.value}' "
                            f"at position {index}. "
                            "Each RankingCriterion may appear at most once."
                        ),
                    )
                )
            else:
                seen_criteria.add(criterion)

        return errors
