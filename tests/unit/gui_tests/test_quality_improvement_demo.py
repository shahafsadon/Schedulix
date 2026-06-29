from pathlib import Path

from application.cache_manager import CacheManager
from fileReader.fileTypeReaders.coursesReader import CoursesFileReader
from fileReader.fileTypeReaders.examPeriodsReader import ExamPeriodsFileReader
from fileReader.fileTypeReaders.programReader import ProgramsFileReader
from fileReader.fileTypeReaders.schedulingSettingsReader import (
    SchedulingSettingsFileReader,
)
from gui.presenters.schedulingPresenter import SchedulingPresenter
from gui.presenters.scheduleNavigationPresenter import ScheduleNavigationPresenter
from scheduling.qualityTagCalculator import ScheduleQualityTag
from scheduling.schedulingService import SchedulingService


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = (
    PROJECT_ROOT
    / "data"
    / "examples"
    / "quality_snapshot_demo"
)
FALLBACK_DEMO_DIR = (
    PROJECT_ROOT
    / "data"
    / "examples"
    / "fallback_compromise_demo"
)


class _MemoryCache(CacheManager):
    _PKL_PATH = PROJECT_ROOT / ".tmp_quality_improvement_demo_cache.pkl"

    def _persist(self):
        return None


def test_quality_improvement_demo_data_supports_snapshot_workflow():
    courses = CoursesFileReader().parse(
        (DEMO_DIR / "courses.txt").read_text(encoding="utf-8")
    )
    periods = ExamPeriodsFileReader().parse(
        (DEMO_DIR / "dates.txt").read_text(encoding="utf-8")
    )
    programs = ProgramsFileReader().parse(
        (DEMO_DIR / "programs.txt").read_text(encoding="utf-8")
    )
    settings = SchedulingSettingsFileReader().parse(
        (DEMO_DIR / "settings.txt").read_text(encoding="utf-8")
    )

    cache = _MemoryCache()
    cache.set_courses(courses)
    cache.set_exam_periods(periods)
    cache.set_selected_programs(programs)
    cache.set_constraint_settings(settings.constraint_settings)
    cache.set_ranking_settings(settings.ranking_settings)

    outcome = SchedulingService().run(cache, rank_results=False)
    assert outcome.schedule_count == 56

    presenter = ScheduleNavigationPresenter(
        cache.get_generated_schedules(),
        cache_manager=cache,
    )
    before_view = presenter.current_view()
    assert before_view.quality_tag is ScheduleQualityTag.RISKY
    assert presenter.save_snapshot("before").success

    data_structures = [
        option
        for option in presenter.manual_move_course_options()
        if option.startswith("83102")
    ][0]
    assert "02-01-2026" in data_structures

    move = presenter.apply_manual_move(data_structures, "08-01-2026")
    assert move.success

    after_view = presenter.current_view()
    assert after_view.quality_tag is ScheduleQualityTag.EXCELLENT
    assert presenter.save_snapshot("after").success

    comparison = presenter.compare_snapshots("before", "after")
    assert comparison.success
    assert comparison.comparison.first_quality == "Risky"
    assert comparison.comparison.second_quality == "Excellent"
    assert comparison.comparison.first_penalty == "0"
    assert comparison.comparison.second_penalty == "0"
    assert comparison.comparison.quality_change_label == (
        "Quality change: Risky \u2192 Excellent \u2014 improved"
    )
    assert comparison.comparison.penalty_delta_label == (
        "Constraint penalty: 0 \u2192 0 \u2014 unchanged"
    )
    assert len(comparison.comparison.changed_rows) == 1

    changed = comparison.comparison.changed_rows[0]
    assert changed.change_label == "Moved exam"
    assert changed.course_label == "83102 - Data Structures"
    assert changed.period_label == "FALL Aleph"
    assert changed.old_date == "02-01-2026"
    assert changed.new_date == "08-01-2026"


def test_fallback_compromise_demo_works_from_normal_gui_generation_path():
    courses = CoursesFileReader().parse(
        (FALLBACK_DEMO_DIR / "courses.txt").read_text(encoding="utf-8")
    )
    periods = ExamPeriodsFileReader().parse(
        (FALLBACK_DEMO_DIR / "dates.txt").read_text(encoding="utf-8")
    )
    programs = ProgramsFileReader().parse(
        (FALLBACK_DEMO_DIR / "programs.txt").read_text(encoding="utf-8")
    )
    settings = SchedulingSettingsFileReader().parse(
        (FALLBACK_DEMO_DIR / "settings.txt").read_text(encoding="utf-8")
    )

    cache = _MemoryCache()
    cache.set_courses(courses)
    cache.set_exam_periods(periods)
    cache.set_selected_programs(programs)
    cache.set_constraint_settings(settings.constraint_settings)
    cache.set_ranking_settings(settings.ranking_settings)

    result = SchedulingPresenter(cache=cache).generate()

    assert result.success
    assert result.is_fallback
    assert result.schedule_count == 1
    assert result.displayed_count == 1
    assert "Fallback schedule" in result.message

    generated = cache.get_generated_schedules()
    ranked = cache.get_ranked_schedules()
    assert len(generated) == 1
    assert len(ranked) == 1
    assert ranked[0].is_fallback
    assert ranked[0].penalty_score == 50
    assert any("Mandatory exams" in detail for detail in ranked[0].penalty_details)
