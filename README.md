# Schedulix

Schedulix is an exam schedule generation and decision-support system. It
loads course, program, and exam-period data, generates valid exam schedules,
ranks alternatives, and helps users review and improve schedules through a
desktop GUI.

The project supports strict schedule generation, progressive ranked
alternatives, manual exam movement, snapshots, snapshot comparison, impact
analysis, output reports, and fallback compromise schedules when no fully valid
schedule exists.

## Key Features

| Area | What Schedulix Supports |
| --- | --- |
| Input workflow | File-based loading of courses, selected programs, exam periods, and optional settings |
| GUI workflow | Upload, program selection, settings, date management, generation, review, ranking, editing, and export |
| Strict generation | Generates all schedules that satisfy the selected hard and threshold constraints |
| Ranking | Progressive Top 50 preview while ranking continues, plus full ranked browsing after completion |
| Manual editing | Move one exam to another valid date and inspect the impact |
| Snapshots | Save/load named schedule versions |
| Comparison | Compare snapshots by quality, constraint penalty, and moved exams |
| Fallback | Show best-effort compromise schedules when strict generation returns zero valid schedules |
| CLI/service flow | Run the scheduler from the file-based application entry point |

## Part 3-4 Technical Reference

This section keeps the code-review details that matter most for the final
project version.

### Scheduling Constraints

Threshold constraints act as filters: a normal generated schedule is valid only
if it satisfies the enabled constraints.

| Constraint | Meaning |
| --- | --- |
| `mandatory_gap_days` | Requires a minimum gap between related mandatory exams |
| `any_course_gap_days` | Requires a minimum gap between any related course exams |
| `elective_conflicts_per_program` | Limits elective same-day conflicts per program |
| `mandatory_span_days` | Limits the total date span of mandatory exams |
| `max_exams_per_day` | Limits how many exams can be scheduled on the same day |

The settings model lives in `src/constraint_settings.py`; constraint evaluation
is handled under `src/scheduling/constraints.py`.

### Ranking Criteria

Ranking criteria are ordering preferences. They do not replace the valid
schedule universe; when ranking is requested, the Top 50 preview is derived
from all currently generated valid schedules.

| Ranking Criterion | Meaning |
| --- | --- |
| `min_mandatory_gap` | Prefer schedules with larger minimum mandatory gaps |
| `average_all_gap` | Prefer schedules with better average spacing |
| `elective_collision_count` | Prefer fewer elective collisions |
| `mandatory_span` | Prefer a better mandatory exam span |
| `max_exams_per_day` | Prefer a lower daily load |

Ranking settings live in `src/ranking_settings.py`. Metric calculation,
ordering, and orchestration are split across
`src/scheduling/scheduleMetricsCalculator.py`,
`src/scheduling/scheduleRanker.py`, and
`src/scheduling/scheduleRankingService.py`.

### Progressive Ranking Architecture

The progressive ranking flow avoids blocking the GUI while ranked alternatives
are computed:

```text
full valid schedules -> batches -> ranking -> Top-N preview -> GUI
```

Important implementation files:

- `src/scheduling/schedulingService.py`
- `src/scheduling/progressiveGeneration.py`
- `src/scheduling/rankedResultsBuffer.py`
- `src/scheduling/scheduleRankingService.py`
- `src/gui/presenters/scheduleNavigationPresenter.py`

The key design choice is separation between the authoritative full generated
schedule list and the derived ranked preview. This keeps normal generation
correct while still making ranking responsive.

### Snapshots, Manual Editing, and Comparison

Part 4 turns generated schedules into an interactive decision-support workflow:

- save named schedule snapshots;
- manually move one exam on a copied schedule;
- validate and analyze the move;
- compare `before` and `after` snapshots by quality, constraint penalty, and
  moved exams;
- export readable comparison reports.

Important implementation files:

- `src/scheduling/scheduleSnapshot.py`
- `src/scheduling/manualScheduleEditor.py`
- `src/scheduling/impactAnalysisService.py`
- `src/scheduling/scheduleDiffService.py`
- `src/output/diffReportWriter.py`

### File-Based Commands

The CLI flow can execute Part 4 commands from a command file. This is useful
for tests and reproducible review scenarios.

```text
SAVE_SNAPSHOT before
MOVE 83102 TO 08-01-2026
SAVE_SNAPSHOT after
COMPARE before after
```

`MOVE` changes one course date in the active schedule, `SAVE_SNAPSHOT` stores
the current schedule under a name, and `COMPARE` writes a diff report.

### Conflict Rule

Two exams are a critical conflict when they are on the same date, belong to the
same program and year, and are not both elective courses. This base rule works
together with the optional threshold constraints.

### Performance Notes

Schedulix keeps large scheduling runs usable through:

- lazy schedule generation in `ExamScheduleGenerator`;
- batch processing for progressive ranking;
- bounded Top 50 preview storage in `RankedResultsBuffer`;
- full-result browsing only when explicitly requested after ranking completes;
- direct normal generation/export paths that are not limited to Top 50.

## Quick Start

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run the GUI:

```powershell
$env:PYTHONPATH = "src"
python -m gui.workflow.mainGui
```

Run the file-based example flow:

```powershell
.\.venv\Scripts\python.exe src\main.py
```

## Running Tests

Run the full suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Useful focused checks:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\gui_tests\test_quality_improvement_demo.py
.\.venv\Scripts\python.exe -m pytest tests\unit\gui_tests\test_upload_service.py
.\.venv\Scripts\python.exe -m pytest tests\unit\scheduling_tests\test_progressive_ranking_flow.py
```

## Official Demo Data

The presentation-ready demo data is under [data/examples](data/examples/README.md).

| Demo | Purpose | Detailed Guide |
| --- | --- | --- |
| `basic_course_example` | Normal generation over a large schedule universe and progressive ranking | [Guide](data/examples/basic_course_example/README.md) |
| `quality_snapshot_demo` | Manual move, snapshots, and Risky to Excellent comparison | [Guide](data/examples/quality_snapshot_demo/README.md) |
| `fallback_compromise_demo` | No strict solution, compromise prompt, and penalty explanation | [Guide](data/examples/fallback_compromise_demo/README.md) |

Each demo folder contains `programs.txt`, `courses.txt`, `dates.txt`,
`settings.txt`, and its own `README.md`. When the three input files are chosen
from the same folder, the GUI preloads the colocated `settings.txt`
automatically before the scheduling settings screen. The user can still edit
settings manually afterward.

## Live Demo Flows

### 1. Basic Generation

Use `data/examples/basic_course_example/` to show the normal scheduling flow.
The expected result is about `76,032` valid schedules. In normal mode,
Schedulix exposes all generated schedules; Top 50 is used only when ranking is
explicitly started.

![Basic generation showing 76032 schedules](images/basic-generated-76032-schedules.png)

### 2. Progressive Ranking

From the generated basic example, add ranking criteria. Schedulix shows a
temporary Top 50 preview while ranking continues, then lets the user show the
full ranked result.

![Live Top 50 ranking preview](images/ranking-top-50-live-preview.png)

### 3. Snapshot Quality Improvement

Use `data/examples/quality_snapshot_demo/` to show manual schedule editing:
save `before`, move `83102 - Data Structures` from `02-01-2026` to
`08-01-2026`, save `after`, and compare. The quality improves from
`Risky` to `Excellent`.

![Snapshot comparison showing quality improvement](images/snapshot-comparison-quality-improved.png)

### 4. Fallback Compromise Schedule

Use `data/examples/fallback_compromise_demo/` to show the fallback path. Strict
generation finds no fully valid schedule because the mandatory gap requirement
is impossible. The GUI offers compromise schedules that still respect hard
constraints and explains the soft-constraint penalty.

![Fallback compromise schedule with penalty details](images/fallback-compromise-output-penalty.png)

## Project Structure

```text
Schedulix/
|-- src/
|   |-- application/       # App orchestration, cache, validation, commands
|   |-- fileReader/        # Input file readers and settings parser
|   |-- gui/               # Screens, presenters, services, workflow shell
|   |-- output/            # Schedule export and diff report writers
|   |-- scheduling/        # Generation, constraints, ranking, snapshots, edits
|   |-- constraint_settings.py
|   |-- ranking_settings.py
|   |-- models.py
|   `-- main.py
|-- tests/
|   |-- unit/
|   |-- integration/
|   `-- system/
|-- data/
|   |-- examples/          # Three official demo datasets
|   `-- outputs/           # Generated schedule/report output
|-- images/                # README screenshots
`-- requirements.txt
```

## Architecture Notes

Schedulix follows a layered structure:

```text
GUI Screens -> Presenters -> Services -> Scheduling Domain -> File/Output Layer
```

- GUI screens focus on layout and widget events.
- Presenters coordinate view state and user actions.
- `SchedulingService` coordinates filtering, generation, ranking, fallback,
  and cache updates.
- Constraint, ranking, snapshot, manual-edit, and comparison logic live under
  `src/scheduling`.
- File parsing stays under `src/fileReader`; output formatting stays under
  `src/output`.

## Notes and Limitations

- Screenshots and example data are optimized for the official live demo flows.
- Fallback schedules are compromise schedules: they respect hard constraints
  but relax enabled soft threshold constraints and show a penalty explanation.
- `settings.txt` auto-preload works when `programs.txt`, `courses.txt`, and
  `dates.txt` are selected from the same demo folder.
- Detailed demo instructions live in the three demo README files linked above.
