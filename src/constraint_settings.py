from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ThresholdConstraintType(Enum):
    """
    Identifies each configurable threshold constraint in the scheduling engine.

    Each member corresponds to one numbered requirement from the design document:

    * mandatory_gap_days          – Req 2.1: minimum gap between two mandatory
                                    exams that share at least one (program, year).
    * any_course_gap_days         – Req 2.2: minimum gap between any two exams
                                    on the same day regardless of course type.
    * elective_conflicts_per_program – Req 2.3: maximum number of elective-exam
                                    conflicts allowed within a single program.
    * mandatory_span_days         – Req 2.4: maximum span (in days) over which
                                    mandatory exams for one program may be spread.
    * max_exams_per_day           – Req 2.5: maximum total exams allowed on a
                                    single calendar day across the whole schedule.
    """

    mandatory_gap_days = "mandatory_gap_days"
    any_course_gap_days = "any_course_gap_days"
    elective_conflicts_per_program = "elective_conflicts_per_program"
    mandatory_span_days = "mandatory_span_days"
    max_exams_per_day = "max_exams_per_day"


@dataclass
class ThresholdConstraintSetting:
    """
    Holds the on/off switch and integer threshold for one constraint type.

    Fields
    ------
    enabled : bool
        When False the scheduling engine ignores this constraint entirely.
    k : int
        The numeric threshold value whose meaning depends on the constraint
        type (e.g. number of days, number of conflicts, number of exams).

    Standard dataclass behaviour is preserved:
    * ``__eq__`` compares both fields by value.
    * ``__repr__`` is generated automatically for clean debugging output.
    * The instance is mutable so callers can adjust settings in place.
    """

    enabled: bool
    k: int


@dataclass
class SchedulingConstraintSettings:
    """
    Aggregates the per-constraint configuration used by the scheduling engine.

    Each ``ThresholdConstraintType`` maps to its own ``ThresholdConstraintSetting``
    so the engine can query both the enabled flag and the threshold value in a
    single attribute lookup.

    Use ``default_configuration()`` to obtain a ready-to-use instance where
    every constraint is disabled and the threshold is initialised to zero.

    Fields
    ------
    constraints : dict[ThresholdConstraintType, ThresholdConstraintSetting]
        The full mapping from constraint type to its current setting.
    """

    constraints: dict[ThresholdConstraintType, ThresholdConstraintSetting]

    @classmethod
    def default_configuration(cls) -> SchedulingConstraintSettings:
        """
        Return a ``SchedulingConstraintSettings`` with all five threshold
        constraints initialised to ``enabled=False`` and ``k=0``.

        This serves as the safe starting state for any consumer that builds
        its configuration incrementally: start from the default, then enable
        and tune only the constraints that are relevant to the current run.
        """
        return cls(
            constraints={
                constraint_type: ThresholdConstraintSetting(
                    enabled=False,
                    k=0,
                )
                for constraint_type in ThresholdConstraintType
            }
        )
