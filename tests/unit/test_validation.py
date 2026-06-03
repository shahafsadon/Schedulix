"""Focused validation tests for malformed Version 2.0 input data."""

from __future__ import annotations

import pytest

from fileReader.fileTypeReaders.coursesReader import CoursesFileReader
from fileReader.fileTypeReaders.examPeriodsReader import ExamPeriodsFileReader
from fileReader.fileTypeReaders.programReader import ProgramsFileReader


def test_courses_reader_rejects_non_integer_year() -> None:
    content = """$$$$
Bad Course
83199
Dr. Test
83101,first,FALL,Obligatory
Exam
"""

    with pytest.raises(ValueError, match="Non-integer year"):
        CoursesFileReader().parse(content)


def test_courses_reader_rejects_incomplete_block() -> None:
    content = """$$$$
Bad Course
83199
Dr. Test
"""

    with pytest.raises(ValueError, match="Malformed course block"):
        CoursesFileReader().parse(content)


def test_exam_period_reader_rejects_malformed_header() -> None:
    content = """$$$$
FALL Aleph
01-03-2026, 05-03-2026
"""

    with pytest.raises(ValueError, match="Malformed period header"):
        ExamPeriodsFileReader().parse(content)


def test_exam_period_reader_rejects_malformed_date_range() -> None:
    content = """$$$$
FALL, Aleph
01/03/2026 - 05/03/2026
"""

    with pytest.raises(ValueError, match="Malformed date range"):
        ExamPeriodsFileReader().parse(content)


def test_exam_period_reader_rejects_backwards_excluded_range() -> None:
    content = """$$$$
FALL, Aleph
01-03-2026, 10-03-2026
- 05-03-2026, 03-03-2026 Invalid holiday range
"""

    with pytest.raises(ValueError, match="Excluded date range is backwards"):
        ExamPeriodsFileReader().parse(content)


def test_program_reader_rejects_more_than_five_programs() -> None:
    with pytest.raises(ValueError, match="maximum allowed is 5"):
        ProgramsFileReader().parse(
            "83101,83102,83103,83104,83105,83107"
        )