from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintType,
)
from ranking_settings import (
    MISSING_METRIC_VALUE,
    RankedExamSystem,
    RankingSettings,
)
from scheduling.examScheduleGenerator import (
    ExamSchedule,
    ExamSystem,
)


DEFAULT_OUTPUT_PATH = (
    Path("data")
    / "outputs"
    / "exam_schedules.txt"
)

DATE_FORMAT = "%d-%m-%Y"

TITLE_LINE = (
    "========================================"
)

# Display placeholder for ScheduleMetrics fields whose real value is
# MISSING_METRIC_VALUE (-1, see ranking_settings.py). Showing "n/a" is more
# readable in a text report than a raw -1.
MISSING_METRIC_DISPLAY = "n/a"

SEMESTER_ORDER = {
    "FALL": 0,
    "SPRI": 1,
    "SUMM": 2,
}

MOED_ORDER = {
    "Aleph": 0,
    "Bet": 1,
    "Gimel": 2,
}


class OutputWriter:
    """Formats and streams generated exam systems to a UTF-8 text file."""

    def write(
        self,
        schedules: Iterable[ExamSystem],
        output_path: str | Path = DEFAULT_OUTPUT_PATH,
    ) -> Path:
        """Compatibility wrapper that writes schedules and returns the path."""
        path, _ = self.write_with_count(
            schedules,
            output_path,
        )

        return path

    def write_with_count(
        self,
        schedules: Iterable[ExamSystem],
        output_path: str | Path = DEFAULT_OUTPUT_PATH,
    ) -> tuple[
        Path,
        int,
    ]:
        """
        Stream systems directly to disk and return (path, written_count).

        The formatter caches repeated period blocks. In a Cartesian product,
        the same period option appears in many complete systems, so repeatedly
        sorting and formatting it is wasted work.

        Output is flushed in chunks to avoid both one enormous string and
        hundreds of thousands of tiny Python-level writes.
        """
        path = Path(
            output_path
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        period_cache: dict[
            int,
            str,
        ] = {}

        order_cache: dict[
            tuple[
                tuple[
                    str,
                    str,
                ],
                ...,
            ],
            tuple[
                int,
                ...,
            ],
        ] = {}

        schedule_count = 0

        pending: list[
            str
        ] = [
            "Schedulix Exam Schedules\n",
            f"{TITLE_LINE}\n",
        ]

        pending_size = sum(
            map(
                len,
                pending,
            )
        )

        flush_threshold = (
            1024
            * 1024
        )

        with path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as output_file:
            for (
                schedule_count,
                schedule,
            ) in enumerate(
                schedules,
                start=1,
            ):
                schedule_parts = [
                    (
                        f"\nSchedule {schedule_count}\n"
                        f"{TITLE_LINE}\n"
                    )
                ]

                current_semester: str | None = None

                for period_schedule in self._ordered_period_schedules(
                    schedule.period_schedules,
                    order_cache,
                ):
                    if (
                        period_schedule.semester
                        != current_semester
                    ):
                        schedule_parts.append(
                            (
                                "Semester: "
                                f"{period_schedule.semester}\n"
                            )
                        )

                        current_semester = (
                            period_schedule.semester
                        )

                    schedule_parts.append(
                        self._format_period(
                            period_schedule,
                            period_cache,
                        )
                    )

                schedule_text = "".join(
                    schedule_parts
                )

                pending.append(
                    schedule_text
                )

                pending_size += len(
                    schedule_text
                )

                if (
                    pending_size
                    >= flush_threshold
                ):
                    output_file.write(
                        "".join(
                            pending
                        )
                    )

                    pending.clear()

                    pending_size = 0

            if pending:
                output_file.write(
                    "".join(
                        pending
                    )
                )

        return (
            path,
            schedule_count,
        )

    def format_schedules(
        self,
        schedules: Iterable[ExamSystem],
    ) -> str:
        """
        Return formatted text for tests and genuinely small outputs.

        Large application output should use write_with_count().
        """
        return "".join(
            self.iter_chunks(
                schedules
            )
        )

    def iter_chunks(
        self,
        schedules: Iterable[ExamSystem],
    ) -> Iterator[str]:
        """Yield formatted output chunks lazily."""
        yield "Schedulix Exam Schedules\n"

        yield f"{TITLE_LINE}\n"

        period_cache: dict[
            int,
            str,
        ] = {}

        order_cache: dict[
            tuple[
                tuple[
                    str,
                    str,
                ],
                ...,
            ],
            tuple[
                int,
                ...,
            ],
        ] = {}

        for (
            index,
            schedule,
        ) in enumerate(
            schedules,
            start=1,
        ):
            yield (
                f"\nSchedule {index}\n"
                f"{TITLE_LINE}\n"
            )

            current_semester: str | None = None

            for period_schedule in self._ordered_period_schedules(
                schedule.period_schedules,
                order_cache,
            ):
                if (
                    period_schedule.semester
                    != current_semester
                ):
                    yield (
                        "Semester: "
                        f"{period_schedule.semester}\n"
                    )

                    current_semester = (
                        period_schedule.semester
                    )

                yield self._format_period(
                    period_schedule,
                    period_cache,
                )

    @staticmethod
    def _format_period(
        schedule: ExamSchedule,
        cache: dict[
            int,
            str,
        ],
    ) -> str:
        """Format one reusable period option and cache it by object identity."""
        cache_key = id(
            schedule
        )

        cached = cache.get(
            cache_key
        )

        if cached is not None:
            return cached

        lines = [
            f"Moed: {schedule.moed}"
        ]

        for exam in sorted(
            schedule.scheduled_exams,
            key=lambda item: (
                item.exam_date,
                item.course.course_number,
            ),
        ):
            lines.append(
                (
                    f"{exam.exam_date.strftime(DATE_FORMAT)} | "
                    f"{exam.course.name} | "
                    f"{exam.course.instructor}"
                )
            )

        formatted = (
            "\n".join(
                lines
            )
            + "\n"
        )

        cache[
            cache_key
        ] = formatted

        return formatted

    @classmethod
    def _ordered_period_schedules(
        cls,
        schedules: list[
            ExamSchedule
        ],
        cache: dict[
            tuple[
                tuple[
                    str,
                    str,
                ],
                ...,
            ],
            tuple[
                int,
                ...,
            ],
        ],
    ) -> Iterator[ExamSchedule]:
        """
        Reuse the same section order for systems with the same period shape.
        """
        signature = tuple(
            (
                item.semester,
                item.moed,
            )
            for item in schedules
        )

        order = cache.get(
            signature
        )

        if order is None:
            order = tuple(
                sorted(
                    range(
                        len(
                            schedules
                        )
                    ),
                    key=lambda index: (
                        cls._period_sort_key(
                            schedules[
                                index
                            ]
                        )
                    ),
                )
            )

            cache[
                signature
            ] = order

        for index in order:
            yield schedules[
                index
            ]

    @staticmethod
    def _period_sort_key(
        schedule: ExamSchedule,
    ) -> tuple[
        int,
        int,
        str,
        str,
    ]:
        """Sort output sections by semester and moed."""
        return (
            SEMESTER_ORDER.get(
                schedule.semester,
                len(
                    SEMESTER_ORDER
                ),
            ),
            MOED_ORDER.get(
                schedule.moed,
                len(
                    MOED_ORDER
                ),
            ),
            schedule.semester,
            schedule.moed,
        )
    
    # ------------------------------------------------------------------
    # Ranked output (SCRUM-166)
    # ------------------------------------------------------------------

    def write_ranked_with_count(
        self,
        ranked_schedules: list[RankedExamSystem],
        output_path: str | Path = DEFAULT_OUTPUT_PATH,
        constraint_settings: SchedulingConstraintSettings | None = None,
        ranking_settings: RankingSettings | None = None,
    ) -> tuple[Path, int]:
        """
        Write ranked exam systems to disk, preserving their given order.

        Unlike write_with_count(), this method takes a *list* of
        RankedExamSystem (the output of ScheduleRankingService /
        SchedulingService) rather than a lazy Iterable[ExamSystem]. The list
        is written in the order it is given — it is NOT re-sorted here, so
        the caller's ranking order (ScheduleRanker) is preserved exactly
        (SCRUM-166 acceptance criterion: "CLI output preserves the selected
        ranking order").

        Each schedule section gains a "Metrics:" line summarizing its
        ScheduleMetrics (SCRUM-164/142). If constraint_settings and/or
        ranking_settings are supplied, an optional "Settings:" summary line
        is added to the file header; passing None for both omits it,
        matching the pre-Part-3 header exactly.

        The exam-line format itself (date | course name | instructor),
        Semester/Moed grouping, and period-section ordering are unchanged:
        this method reuses _ordered_period_schedules and _format_period, the
        same helpers used by write_with_count().

        Unlike write_with_count(), this method builds the entire output text
        in memory before writing it in one call (no chunked flushing). This
        is consistent with SchedulingService.run() (SCRUM-164) already
        materializing the full ranked_schedules list — see the SCRUM-166
        module docstring in schedulixApp.py for the lazy-vs-materialized
        trade-off this implies.

        Returns (path, written_count), where written_count is the number of
        ranked systems written (== len(ranked_schedules)).
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        period_cache: dict[int, str] = {}
        order_cache: dict[
            tuple[tuple[str, str], ...],
            tuple[int, ...],
        ] = {}

        lines: list[str] = [
            "Schedulix Exam Schedules\n",
            f"{TITLE_LINE}\n",
        ]

        settings_summary = self._format_settings_summary(
            constraint_settings,
            ranking_settings,
        )
        if settings_summary is not None:
            lines.append(f"{settings_summary}\n")

        lines.append(f"Valid systems: {len(ranked_schedules)}\n")
        lines.append(f"{TITLE_LINE}\n")

        for index, ranked in enumerate(ranked_schedules, start=1):
            lines.append(f"\nSchedule {index}\n")
            lines.append(f"{TITLE_LINE}\n")
            lines.append(f"{self._format_metrics_line(ranked)}\n")

            current_semester: str | None = None

            for period_schedule in self._ordered_period_schedules(
                ranked.exam_system.period_schedules,
                order_cache,
            ):
                if period_schedule.semester != current_semester:
                    lines.append(f"Semester: {period_schedule.semester}\n")
                    current_semester = period_schedule.semester

                lines.append(
                    self._format_period(period_schedule, period_cache)
                )

        with path.open("w", encoding="utf-8", newline="\n") as output_file:
            output_file.write("".join(lines))

        return path, len(ranked_schedules)

    @staticmethod
    def _format_metrics_line(ranked: RankedExamSystem) -> str:
        """Format one compact "Metrics:" line from a RankedExamSystem.

        Mirrors the five ScheduleMetrics fields (ranking_settings.py). Any
        field equal to MISSING_METRIC_VALUE (-1) is shown as
        MISSING_METRIC_DISPLAY ("n/a") instead of a raw -1, since -1 is an
        internal sentinel, not a meaningful day count.
        """
        metrics = ranked.metrics

        def display(value: int | float) -> str:
            return (
                MISSING_METRIC_DISPLAY
                if value == MISSING_METRIC_VALUE
                else str(value)
            )

        return (
            "Metrics: "
            f"min_gap={display(metrics.min_mandatory_gap)} | "
            f"avg_gap={display(metrics.average_all_gap)} | "
            f"elective_collisions={display(metrics.elective_collision_count)} | "
            f"mand_span={display(metrics.mandatory_span)} | "
            f"max_per_day={display(metrics.max_exams_per_day)}"
        )

    @staticmethod
    def _format_settings_summary(
        constraint_settings: SchedulingConstraintSettings | None,
        ranking_settings: RankingSettings | None,
    ) -> str | None:
        """Format the optional "Settings:" header line.

        Returns None when both arguments are None, so callers that do not
        pass settings (or pre-Part-3 callers of write_with_count, which never
        call this at all) get exactly the pre-Part-3 header with no extra
        line.

        When at least one argument is given, enabled threshold constraints
        and active ranking criteria are summarized on a single line. An
        empty summary (no enabled constraints and no ranking criteria) is
        rendered as "Settings: none (all constraints disabled, no ranking)"
        rather than an empty/confusing line.
        """
        if constraint_settings is None and ranking_settings is None:
            return None

        constraint_parts: list[str] = []
        if constraint_settings is not None:
            for constraint_type in ThresholdConstraintType:
                setting = constraint_settings.constraints.get(constraint_type)
                if setting is not None and setting.enabled:
                    constraint_parts.append(
                        f"{constraint_type.value}={setting.k}"
                    )

        ranking_parts: list[str] = []
        if ranking_settings is not None:
            for preference in ranking_settings.priority_list:
                direction = "desc" if preference.descending else "asc"
                ranking_parts.append(
                    f"{preference.criterion.value} {direction}"
                )

        if not constraint_parts and not ranking_parts:
            return "Settings: none (all constraints disabled, no ranking)"

        segments: list[str] = []
        if constraint_parts:
            segments.append(f"constraints[{', '.join(constraint_parts)}]")
        if ranking_parts:
            segments.append(f"ranking[{', '.join(ranking_parts)}]")

        return "Settings: " + " | ".join(segments)
