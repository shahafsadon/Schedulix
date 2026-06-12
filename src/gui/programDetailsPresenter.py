"""Backward-compatible import path for program-details presenter classes."""

from gui.presenters.programDetailsPresenter import (
    CourseDetail,
    ProgramDetails,
    ProgramDetailsPresenter,
    SemesterGroup,
)


__all__ = [
    "CourseDetail",
    "ProgramDetails",
    "ProgramDetailsPresenter",
    "SemesterGroup",
]
