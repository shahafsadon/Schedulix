"""Application entry point for the file-based Version 1.0-style CLI flow,
extended to support Part 3 threshold-constraint and ranking settings
(SCRUM-166).

Reads the three required input files (courses, exam periods, programs) plus
an optional fourth settings file (SCRUM-165), runs the shared
SchedulingService (SCRUM-164) so the CLI flow applies exactly the same
validation, constraint-evaluation, and ranking logic as the GUI flow, and
writes the ranked results to a readable text file via
OutputWriter.write_ranked_with_count (SCRUM-166).

Note on the lazy-generation optimization (see the Schedulix Algorithm
Optimization document): the pre-Part-3 flow used
ExamScheduleGenerator.iter_exam_systems() so the Cartesian product of exam
systems was never fully materialized in memory. SchedulingService.run()
(SCRUM-164) instead uses generate_exam_systems() (a list) because ranking
requires the complete set of systems before sorting. This is an intentional
trade-off for the Part 3 flow: ranking is inherently non-lazy. Callers who
do not need ranking or Part 3 constraints and are concerned about very large
course sets can still use ExamScheduleGenerator.iter_exam_systems() and
OutputWriter.write_with_count() directly, as this module did before
SCRUM-166.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from fileReader.fileTypeReaders.commandsFileReader import CommandType, ParsedCommand
from output.diffReportWriter import DiffReportWriter
from scheduling.manualScheduleEditor import ManualScheduleEditor
from scheduling.scheduleDiffService import ScheduleDiffService
from scheduling.scheduleSnapshot import SnapshotManager

from application.cache_manager import CacheManager
from application.settings_validator import SchedulingSettingsValidator
from constraint_settings import SchedulingConstraintSettings
from fileReader.baseFileReader import (
    FileReaderFactory,
    FileReaderType,
)
from output.outputWriter import (
    DEFAULT_OUTPUT_PATH,
    OutputWriter,
)
from ranking_settings import RankingSettings
from scheduling.courseFilter import CourseFilter
from scheduling.examScheduleGenerator import ExamScheduleGenerator
from scheduling.qualityTagCalculator import QualityTagCalculator
from scheduling.schedulingService import SchedulingService


# Project root is resolved from this file so PyCharm and terminal runs behave
# the same even when their working directories are different.
PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

# Default input files for the simple Version 1.0 flow.
DEFAULT_COURSES_PATH = (
    PROJECT_ROOT
    / "data"
    / "examples"
    / "basic_course_example"
    / "courses.txt"
)

DEFAULT_EXAM_PERIODS_PATH = (
    PROJECT_ROOT
    / "data"
    / "examples"
    / "basic_course_example"
    / "dates.txt"
)

DEFAULT_PROGRAMS_PATH = (
    PROJECT_ROOT
    / "data"
    / "examples"
    / "basic_course_example"
    / "programs.txt"
)

DEFAULT_APP_OUTPUT_PATH = (
    PROJECT_ROOT
    / DEFAULT_OUTPUT_PATH
)

DEFAULT_DIFF_REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "outputs"
    / "diff_report.txt"
)


class _IsolatedCacheManager(CacheManager):
    """A CacheManager whose pickle file is private to one SchedulixApp.run()
    call (SCRUM-166).

    SchedulingService.run(cache) (SCRUM-164) requires a CacheManager, but
    SchedulixApp is a file-in/file-out CLI flow with no concept of a
    persistent session. The base CacheManager._PKL_PATH points at
    internal_data.pkl, the same file used by the GUI flow's persisted
    session; reusing it here would let a CLI run silently overwrite or be
    overwritten by GUI state.

    This subclass gets its own _PKL_PATH class attribute (CacheManager reads
    self.__class__._PKL_PATH in _load_from_disk/_persist, so subclassing is
    sufficient for isolation — see cache_manager.py). SchedulixApp.run()
    points it at a fresh temporary file for the duration of one run and lets
    the temporary directory's cleanup remove it afterwards. The shared
    CacheManager._PKL_PATH (and therefore the GUI's internal_data.pkl) is
    never read or written by the CLI flow.
    """

    _PKL_PATH: Path = Path(tempfile.gettempdir()) / "schedulix_cli_cache.pkl"


@dataclass(frozen=True)
class ApplicationResult:
    """Stores a short summary of one completed application run.

    `schedule_count` and `valid_system_count` are always equal; both are
    kept so existing callers reading `schedule_count` (pre-SCRUM-166)
    continue to work unchanged, while `valid_system_count` is the
    SCRUM-166-introduced name matching the ticket's "valid-system count"
    wording.

    `active_constraints` lists the enabled threshold-constraint names (in
    ThresholdConstraintType declaration order), and `active_ranking` lists
    the active ranking criteria in priority order. Both are empty lists when
    no settings file is supplied (or the supplied settings have nothing
    enabled).
    """

    selected_program_count: int
    total_course_count: int
    relevant_course_count: int
    exam_period_count: int
    schedule_count: int
    output_path: Path
    valid_system_count: int
    active_constraints: list[str]
    active_ranking: list[str]
    command_errors: list[str] = field(default_factory=list)
    diff_report_path: Path | None = None
    commands_executed: int = 0


class SchedulixApp:
    """Runs the complete file-based Version 1.0-style application flow,
    including the optional Part 3 settings file (SCRUM-166)."""

    def __init__(
        self,
        output_writer: OutputWriter | None = None,
        scheduling_service: SchedulingService | None = None,
    ) -> None:
        """Create the application with its collaborators.

        Args:
            output_writer: writes the ranked results to a text file; a
                default is created when none is supplied.
            scheduling_service: the shared SCRUM-164 service that filters,
                validates settings, generates, and ranks exam systems; a
                default is created when none is supplied. Tests can inject a
                fake to isolate SchedulixApp from the real generation engine.

        Note: course_filter and schedule_generator were removed from this
        constructor in SCRUM-166. SchedulingService owns its own CourseFilter
        and builds its own ExamScheduleGenerator (configured with the active
        constraint settings) on each run() call, so SchedulixApp no longer
        needs — and must not hold — a second copy of either.
        """
        self.output_writer = (
            output_writer
            or OutputWriter()
        )

        self._service_was_injected = scheduling_service is not None
        self._service = (
            scheduling_service
            or SchedulingService()
        )
        self._course_filter = CourseFilter()
        self._settings_validator = SchedulingSettingsValidator()

    def run(
        self,
        courses_path: str | Path = DEFAULT_COURSES_PATH,
        exam_periods_path: str | Path = DEFAULT_EXAM_PERIODS_PATH,
        programs_path: str | Path = DEFAULT_PROGRAMS_PATH,
        output_path: str | Path = DEFAULT_APP_OUTPUT_PATH,
        settings_path: str | Path | None = None,
        commands_path: str | Path | None = None,
    ) -> ApplicationResult:
        """
        Read input files (plus optional settings), generate and rank exam
        systems via the shared SchedulingService, and write the ranked
        output.

        Args:
            courses_path, exam_periods_path, programs_path: the three
                required Version 1.0 input files (unchanged from before
                SCRUM-166).
            output_path: where the ranked, formatted output is written.
            settings_path: optional path to a Part 3 settings file
                (SCRUM-165 format). When None, no settings file is read and
                generation proceeds with SchedulingConstraintSettings
                .default_configuration() (all constraints disabled) and
                RankingSettings([]) (no ranking, generation order
                preserved) — i.e. exactly the pre-Part-3 behavior. This
                matches the SCRUM-166 acceptance criterion that callers
                supplying only the original three files still work
                unchanged.

        Returns:
            An ApplicationResult summarizing the run, including the active
            constraint/ranking settings actually used.
        """
        # --- Step 1: read the three required input files (unchanged). ---
        programs_reader = FileReaderFactory.get_reader(FileReaderType.PROGRAMS)
        selected_programs = programs_reader.read(programs_path)

        courses_reader = FileReaderFactory.get_reader(FileReaderType.COURSES)
        courses = courses_reader.read(courses_path)

        periods_reader = FileReaderFactory.get_reader(FileReaderType.EXAM_PERIODS)
        exam_periods = periods_reader.read(exam_periods_path)

        # --- Step 2: load Part 3 settings, or fall back to pre-Part-3 defaults. ---
        if settings_path is None:
            # No settings file supplied: preserve pre-Part-3 behavior exactly
            # (all constraints disabled, no ranking, generation order kept).
            constraint_settings = SchedulingConstraintSettings.default_configuration()
            ranking_settings = RankingSettings([])
        else:
            settings_reader = FileReaderFactory.get_reader(
                FileReaderType.SCHEDULING_SETTINGS
            )
            bundle = settings_reader.read(settings_path)
            constraint_settings = bundle.constraint_settings
            ranking_settings = bundle.ranking_settings

        active_constraints = [
            constraint_type.value
            for constraint_type, setting in constraint_settings.constraints.items()
            if setting.enabled
        ]
        active_ranking = [
            preference.criterion.value
            for preference in ranking_settings.priority_list
        ]

        # Fast path: when no ranking criteria are active, do not send the CLI
        # through SchedulingService. The service is correct for the GUI, but it
        # materializes every system, calculates all metrics, stores cache state,
        # and then writes ranked output. That is the performance regression.
        # With no ranking, the correct production path is the optimized lazy
        # iterator + streaming writer.
        if not ranking_settings.priority_list and not self._service_was_injected:
            validation_result = self._settings_validator.validate(
                constraint_settings=constraint_settings,
                ranking_settings=ranking_settings,
            )
            if not validation_result.is_valid:
                raise ValueError(
                    "Invalid scheduling settings:\n"
                    + "\n".join(validation_result.error_messages)
                )

            relevant_courses = self._course_filter.filter_relevant_courses(
                courses,
                selected_programs,
            )
            generator = ExamScheduleGenerator(
                constraint_settings=constraint_settings,
            )
            schedules = generator.iter_exam_systems(
                relevant_courses,
                exam_periods,
            )

            initial_schedule = None
            if commands_path is not None:
                import itertools
                s1, s2 = itertools.tee(schedules, 2)
                initial_schedule = next(s1, None)
                if initial_schedule is None:
                    raise ValueError("No schedules were generated. Commands cannot be executed.")
                schedules_to_write = s2
            else:
                schedules_to_write = schedules

            created_output_path, written_count = self.output_writer.write_with_count(
                schedules_to_write,
                output_path,
                constraint_settings=constraint_settings,
                ranking_settings=ranking_settings,
                metrics_line="Metrics: not calculated (no ranking criteria active)",
                include_valid_systems_footer=True,
            )

            command_errors: list[str] = []
            diff_report_path: Path | None = None
            commands_executed = 0

            if commands_path is not None and initial_schedule is not None:
                snapshot_manager = SnapshotManager()
                commands_reader = FileReaderFactory.get_reader(FileReaderType.COMMANDS)
                commands = commands_reader.read(commands_path)
                default_diff_path = Path(output_path).parent / "diff_report.txt"

                _, command_errors, diff_report_path, commands_executed = self._execute_commands(
                    commands=commands,
                    initial_schedule=initial_schedule,
                    snapshot_manager=snapshot_manager,
                    diff_report_path=default_diff_path,
                    constraint_settings=constraint_settings,
                )

            return ApplicationResult(
                selected_program_count=len(selected_programs),
                total_course_count=len(courses),
                relevant_course_count=len(relevant_courses),
                exam_period_count=len(exam_periods),
                schedule_count=written_count,
                output_path=created_output_path,
                valid_system_count=written_count,
                active_constraints=active_constraints,
                active_ranking=active_ranking,
                command_errors=command_errors,
                diff_report_path=diff_report_path,
                commands_executed=commands_executed,
            )

        # --- Step 3: run the shared scheduling service in an isolated cache. ---
        #
        # tempfile.TemporaryDirectory() guarantees the cache file is removed
        # after this block, regardless of success or failure.
        #
        # KNOWN LIMITATION: _IsolatedCacheManager._PKL_PATH is a *class*
        # attribute (inherited from CacheManager, which reads
        # self.__class__._PKL_PATH). The line below mutates that shared
        # class attribute, so two run() calls executing concurrently on
        # different threads within the same process can race and end up
        # both pointing at the same temporary path. This is NOT an issue
        # for separate processes (e.g. pytest-xdist) or for sequential CLI
        # usage, which is the only supported usage today. Fixing this
        # properly means making the pickle path an instance attribute on
        # CacheManager itself (SCRUM-144, already merged) — out of scope
        # for SCRUM-166, but tracked as a follow-up if SchedulixApp ever
        # needs concurrent run() support.
        with tempfile.TemporaryDirectory() as tmp_dir:
            _IsolatedCacheManager._PKL_PATH = Path(tmp_dir) / "cli_cache.pkl"
            cache = _IsolatedCacheManager()
            cache.clear()

            # Settings are written before the data they would invalidate, so
            # that the invalidation triggered by set_constraint_settings /
            # set_ranking_settings (CacheManager, SCRUM-144) has no
            # generated/ranked schedules to clear yet — there simply are none
            # in a fresh cache. Order is defensive but not load-bearing here.
            cache.set_constraint_settings(constraint_settings)
            cache.set_ranking_settings(ranking_settings)

            cache.set_courses(courses)
            cache.set_exam_periods(exam_periods)
            cache.set_selected_programs(selected_programs)

            outcome = self._service.run(cache)

        # --- Step 4: write the ranked output. ---
        # QualityTagCalculator is instantiated once per run so it can be
        # reused across all ranked schedules without repeated allocation.
        created_output_path, written_count = (
            self.output_writer.write_ranked_with_count(
                outcome.ranked_schedules,
                output_path,
                constraint_settings=constraint_settings,
                ranking_settings=ranking_settings,
                quality_tag_calculator=QualityTagCalculator(),
            )
        )

        command_errors = []
        diff_report_path = None
        commands_executed = 0

        if commands_path is not None:
            if not outcome.ranked_schedules:
                raise ValueError("No schedules were generated. Commands cannot be executed.")
            
            initial_schedule = outcome.ranked_schedules[0].exam_system
            snapshot_manager = SnapshotManager()
            commands_reader = FileReaderFactory.get_reader(FileReaderType.COMMANDS)
            commands = commands_reader.read(commands_path)
            default_diff_path = Path(output_path).parent / "diff_report.txt"

            _, command_errors, diff_report_path, commands_executed = self._execute_commands(
                commands=commands,
                initial_schedule=initial_schedule,
                snapshot_manager=snapshot_manager,
                diff_report_path=default_diff_path,
                constraint_settings=constraint_settings,
            )

        # --- Step 5: return a run summary. ---
        return ApplicationResult(
            selected_program_count=len(selected_programs),
            total_course_count=len(courses),
            relevant_course_count=outcome.relevant_course_count,
            exam_period_count=len(exam_periods),
            schedule_count=outcome.schedule_count,
            output_path=created_output_path,
            valid_system_count=outcome.schedule_count,
            active_constraints=active_constraints,
            active_ranking=active_ranking,
            command_errors=command_errors,
            diff_report_path=diff_report_path,
            commands_executed=commands_executed,
        )

    def _execute_commands(
        self,
        commands: list[ParsedCommand],
        initial_schedule: ExamSystem,
        snapshot_manager: SnapshotManager,
        diff_report_path: Path,
        constraint_settings: SchedulingConstraintSettings | None = None,
    ) -> tuple[ExamSystem, list[str], Path | None, int]:
        """Execute a sequence of snapshot and move commands on a schedule.

        Individual command errors are recorded in the error list and do not stop
        execution of subsequent commands.

        Args:
            commands: List of ParsedCommand objects.
            initial_schedule: The starting active schedule.
            snapshot_manager: Manager storing snapshots for the run.
            diff_report_path: Destination path for comparison reports.
            constraint_settings: Optional constraints to validate moves.

        Returns:
            A tuple of (active_schedule, command_errors, diff_report_path, commands_executed).
        """
        active_schedule = initial_schedule
        command_errors: list[str] = []
        active_diff_report_path: Path | None = None
        commands_executed = 0

        for cmd in commands:
            commands_executed += 1
            if cmd.command_type == CommandType.MOVE:
                course_id = cmd.parameters["course_id"]
                new_date = cmd.parameters["new_date"]
                editor = ManualScheduleEditor()
                result = editor.move_exam(
                    active_schedule,
                    course_id,
                    new_date,
                    constraint_settings=constraint_settings,
                )
                if result.success and result.schedule is not None:
                    active_schedule = result.schedule
                else:
                    command_errors.append(f"Line {cmd.line_number}: {result.message}")

            elif cmd.command_type == CommandType.SAVE_SNAPSHOT:
                name = cmd.parameters["name"]
                try:
                    snapshot_manager.set_active_schedule(active_schedule)
                    snapshot_manager.save_current(name)
                except Exception as error:
                    command_errors.append(f"Line {cmd.line_number}: {str(error)}")

            elif cmd.command_type == CommandType.LOAD_SNAPSHOT:
                name = cmd.parameters["name"]
                try:
                    snapshot = snapshot_manager.load(name)
                    active_schedule = snapshot.schedule
                except Exception as error:
                    msg = error.args[0] if isinstance(error, KeyError) and error.args else str(error)
                    command_errors.append(f"Line {cmd.line_number}: {msg}")

            elif cmd.command_type == CommandType.COMPARE:
                name_a = cmd.parameters["name_a"]
                name_b = cmd.parameters["name_b"]
                try:
                    snapshots = {s.name: s for s in snapshot_manager.list_snapshots()}
                    if name_a not in snapshots:
                        raise KeyError(f"Snapshot was not found: {name_a}.")
                    if name_b not in snapshots:
                        raise KeyError(f"Snapshot was not found: {name_b}.")

                    diff_service = ScheduleDiffService()
                    result = diff_service.compare(snapshots[name_a], snapshots[name_b])

                    writer = DiffReportWriter()
                    writer.write_file(
                        result,
                        diff_report_path,
                        first_snapshot=snapshots[name_a],
                        second_snapshot=snapshots[name_b],
                    )
                    active_diff_report_path = diff_report_path
                except Exception as error:
                    msg = error.args[0] if isinstance(error, KeyError) and error.args else str(error)
                    command_errors.append(f"Line {cmd.line_number}: {msg}")

        return active_schedule, command_errors, active_diff_report_path, commands_executed
