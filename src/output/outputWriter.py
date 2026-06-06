from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

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