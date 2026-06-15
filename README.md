# Schedulix

Schedulix is a Python exam-scheduling system for the Software Engineering
project. It reads course data, exam-period data, and selected study programs
from text files, then generates valid exam-system options that avoid the
critical conflicts defined for the project.

The project supports two flows:

- **Version 1.0 file flow**: run from `src/main.py`, read the default example
  files, generate schedules, and write all schedule options to a text file.
- **Version 2.0 GUI flow**: run the customTkinter application, upload/preview
  data, select up to five programs, edit exam dates in a calendar, generate
  schedules, browse them with previous/next, and export the chosen schedule.

## Version 2.0 GUI Workflow

The Version 2.0 desktop app guides the user through the complete scheduling
process:

```text
Upload Files -> Select Programs -> Manage Exam Dates -> Generate Schedules -> Review Results
```

Generated schedules are created on a background worker so the GUI remains
responsive during heavier scheduling runs.

### 1. Upload Files

![File upload and data preview](images/file-upload-preview-screen.png)

The first screen loads the three required inputs: courses, study programs, and
exam periods. The user can replace or append each dataset, export the currently
loaded data, and confirm that the uploaded data is ready before continuing.
The preview panel summarizes the cached data so the user can verify the input
state before moving to program selection.

![Loaded files control center](images/input-control-center-loaded-files.png)

This focused view shows the input control center after all required files have
been loaded successfully. Once the status is ready, the user continues to choose
which study programs should participate in scheduling.

### 2. Select Programs

![Program selection and course details](images/program-selection-details-screen.png)

The program selection screen lets the user choose up to five study programs and
inspect the courses attached to each selected program. Expanding a program shows
courses grouped by year and semester, including requirement type and evaluation
method. After selecting the relevant programs, the user continues to review and
edit exam dates.

### 3. Manage Exam Dates

![Date management and direct generation](images/date-management-generate-screen.png)

Date Management is the final review step before schedule generation. The user
can switch between exam periods, edit start/end dates, exclude unavailable days,
re-enable dates, and undo the latest edit. The summary cards show the current
period count, window length, active days, excluded days, and hidden exclusions.
When the calendar is ready, the user clicks **Generate Exam Schedules** directly
from this screen.

### 4. Generate Schedules

The generation action runs asynchronously from the Date Management screen. While
generation is running, calendar editing controls are disabled to prevent
conflicting changes or duplicate generation requests. If generation succeeds,
the generated schedule systems are saved in the GUI cache and the app opens the
results screen automatically. If generation fails, the user stays on Date
Management and receives a clear error message.

### 5. Review Results

![Generated schedules review screen](images/generated-schedules-review-screen.png)

The results screen lets the user review one generated exam-system option at a
time. The calendar highlights scheduled exam dates, and the side panel lists the
exams on the selected date plus the full system grouped by semester and moed.
The user can move between generated systems with previous/next controls.

![Generated schedules navigation controls](images/generated-schedules-navigation-header.png)

The navigation header shows the current system number out of the total generated
options. After reviewing the alternatives, the user can save the selected system
to a readable output file.


## Project Structure

```text
Schedulix/
|-- data/
|   |-- examples/
|   |   |-- CourseExample.txt        # Example course records
|   |   |-- DatesExample.txt         # Example exam periods and excluded dates
|   |   |-- ProgramsExample.txt      # Example selected study programs
|   |   `-- SettingsExample.txt      # Example Part 3 scheduling-settings file (optional)
|   |-- outputs/
|   |   `-- exam_schedules.txt       # Generated output file after running the system
|   `-- output/                      # Old/unused output folder placeholder
|-- images/                          # README screenshots for the GUI workflow
|-- src/
|   |-- main.py                      # Main file to run from PyCharm or terminal
|   |-- models.py                    # Shared data classes: Course, ProgramEnrollment, ExamPeriod
|   |-- application/
|   |   `-- schedulixApp.py          # Connects readers, filtering, scheduling, and output
|   |-- fileReader/
|   |   |-- baseFileReader.py        # Shared reader base class and reader factory
|   |   `-- fileTypeReaders/
|   |       |-- coursesReader.py             # Parses CourseExample-style course files
|   |       |-- examPeriodsReader.py         # Parses DatesExample-style exam-period files
|   |       |-- programReader.py             # Parses selected program files
|   |       |-- schedulingSettingsReader.py  # Parses optional Part 3 settings files
|   |       `-- schedulingSettingsWriter.py  # Writes Part 3 settings files
|   |-- output/
|   |   |-- exportService.py         # Exports one chosen generated schedule
|   |   `-- outputWriter.py          # Formats and writes readable schedule output
|   |-- gui/
|   |   |-- workflow/
|   |   |   |-- mainGui.py            # Opens the Version 2.0 desktop app
|   |   |   `-- workflowApp.py       # Owns the multi-step GUI workflow
|   |   |-- screens/                 # customTkinter views only
|   |   |   |-- fileUploadScreen.py
|   |   |   |-- programConfigScreen.py
|   |   |   |-- dateManagementScreen.py
|   |   |   `-- scheduleNavigationScreen.py
|   |   |-- presenters/              # Testable MVP presenter logic
|   |   |   |-- dateManagementPresenter.py
|   |   |   |-- exportPresenter.py
|   |   |   |-- programSelectionPresenter.py
|   |   |   |-- schedulingPresenter.py
|   |   |   `-- uploadedDataPresenter.py
|   |   |-- services/                # GUI-facing data services
|   |   |   |-- uploadService.py
|   |   |   `-- uploadedDataExportService.py
|   |   `-- factories/               # View/presenter factories
|   |       |-- presenter_factory.py
|   |       `-- view_factory.py
|   `-- scheduling/
|       |-- courseFilter.py          # Keeps only selected-program exam courses
|       |-- examDateHandler.py       # Builds valid exam dates and removes blocked dates
|       |-- examConflictDetector.py  # Detects critical same-date conflicts
|       `-- examScheduleGenerator.py # Generates valid exam-system options
`-- tests/
    |-- README.md                    # Notes for the tester
    |-- unit/                        # Tests for one module at a time
    |-- integration/                 # Tests for several parts working together
    `-- system/                      # End-to-end example-file tests
```

## How To Run

### Run The Version 2.0 GUI App

Install the GUI dependency once from the project root:

```powershell
cd C:\Users\user\Desktop\Schedulix
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The Version 2.0 GUI workflow can be opened from the project root:

```powershell
cd C:\Users\user\Desktop\Schedulix
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m gui.workflow.mainGui
```

The app opens the full workflow: upload input files, select study programs,
review and edit exam dates, generate schedules directly from the Date Management
screen, review generated schedule systems, and export the chosen result.

The upload window uses `customtkinter`, as planned in the Version 2.0 software
design document. If a teammate does not have a `.venv` folder yet, create it
first and then install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## GUI State Cache

The GUI stores uploaded data, selected programs, edited exam periods, and
generated schedules in a local pickle file:

```text
src/application/internal_data.pkl
```

This file is runtime state and is ignored by git. It lets the GUI reopen with
the last saved data, but teammates do not need to commit or share it.

## What The Run Prints

A successful run prints a summary like this:

```text
Schedulix run completed successfully.
Selected programs: 3
Courses read: 3
Relevant Exam courses: 2
Exam periods read: 3
Schedules generated: 76032
Output file: C:\Users\user\Desktop\Schedulix\data\outputs\exam_schedules.txt
Runtime seconds: 1.42
```

`Runtime seconds` is useful for checking the Version 1.0 performance requirement.
The requirement says the system should create the output within 30 seconds.

## Default Example Files

The normal run uses these files automatically:

```text
data/examples/CourseExample.txt
data/examples/DatesExample.txt
data/examples/ProgramsExample.txt
```

The output is written to:

```text
data/outputs/exam_schedules.txt
```

## Output Format

The output starts with a title and then lists schedule options:

```text
Schedulix Exam Schedules
========================================

Schedule 1
========================================
Semester: FALL
Moed: Aleph
29-01-2026 | Physics 1 | Prof. O. Some
30-01-2026 | Calculus 1 | Dr. Erez Scheiner
Moed: Bet
10-04-2026 | Physics 1 | Prof. O. Some
12-04-2026 | Calculus 1 | Dr. Erez Scheiner
```

Each `Schedule N` represents one complete exam-system option. Inside it, exams
are separated by semester and moed. Each exam line contains:

```text
exam date | course name | instructor name
```

## Input File Format

All input files are text files. Save them as UTF-8.

### 1. Selected Programs File

File:

```text
data/examples/ProgramsExample.txt
```

Format:

```text
83101, 83102, 83108
```

Rules:

- Up to 5 programs.
- Each program must be a 5-digit ID.
- Supported program IDs:

```text
83101, 83102, 83104, 83107, 83108,
83109, 83105, 83182, 83103, 83115
```

### 2. Courses File

File:

```text
data/examples/CourseExample.txt
```

Each course record starts with `$$$$`.

Format:

```text
$$$$
Course name
Course number
Instructor name
Program,Year,Semester,Requirement
Program,Year,Semester,Requirement
Evaluation
```

Example:

```text
$$$$
Physics 1
83102
Prof. O. Some
83101,1,FALL,Obligatory
83102,1,FALL,Obligatory
Exam
```

Rules:

- Course number must be 5 digits.
- Program must be 5 digits.
- Year must be one of: `1`, `2`, `3`, `4`.
- Semester must be one of: `FALL`, `SPRI`, `SUMM`.
- Requirement must be one of: `Obligatory`, `Elective`.
- Evaluation must be one of: `Exam`, `Project`, `Attendance`.
- Only courses with `Exam` are scheduled.
- Courses with `Project` or `Attendance` are read but not scheduled.

### 3. Exam Periods File

File:

```text
data/examples/DatesExample.txt
```

Each exam-period record starts with `$$$$`.

Format:

```text
$$$$
Semester, Moed
Start date, End date
Excluded date optional comment
Excluded start date, Excluded end date optional comment
```

Example:

```text
$$$$
FALL, Aleph
29-01-2026, 11-03-2026
- 31-01-2026 Shabat
- 02-03-2026, 04-03-2026 Purim
```

Rules:

- Dates use `DD-MM-YYYY`.
- Semester must be one of: `FALL`, `SPRI`, `SUMM`.
- Moed must be one of: `Aleph`, `Bet`, `Gimel`.
- The exam-period start date must be before or equal to the end date.
- Excluded dates can be single dates or date ranges.
- The leading `-` before excluded dates is optional.
- Comments after excluded dates are ignored by the scheduler.

### 4. Scheduling Settings File (optional, Part 3)

File:

```text
data/examples/SettingsExample.txt
```

This optional fourth file configures the Part 3 threshold constraints
(Section 2 of the requirements) and the ranking-criteria priority order
(Section 3). It is parsed by `SchedulingSettingsFileReader` into the same
`SchedulingConstraintSettings` and `RankingSettings` models used by the GUI.

> **Status:** This file is parsed and validated, but is not yet wired into
> `SchedulixApp.run()`. CLI integration is tracked under SCRUM-166.

Format:

```text
# Comments start with '#'. Blank lines are ignored.
#
# Threshold constraints (Section 2).
# Each line:  <constraint_type> = <enabled>, <k>
mandatory_gap_days             = on,  3
any_course_gap_days            = off, 0
elective_conflicts_per_program = off, 0
mandatory_span_days            = off, 0
max_exams_per_day              = on,  2

# Ranking criteria (Section 3), in priority order.
# Each line:  ranking: <criterion> [ : <direction> ]
ranking: min_mandatory_gap
ranking: average_all_gap : desc
```

Rules:

- Enabled tokens: `on` / `off` (also accepted: `true`/`false`, `yes`/`no`, `1`/`0`).
- Constraint names: `mandatory_gap_days`, `any_course_gap_days`,
  `elective_conflicts_per_program`, `mandatory_span_days`, `max_exams_per_day`.
- `k` must be a positive integer when the constraint is enabled, except
  `elective_conflicts_per_program` which also allows `k = 0`.
- Ranking criteria: `min_mandatory_gap`, `average_all_gap`,
  `elective_collision_count`, `mandatory_span`, `max_exams_per_day`.
- Ranking direction: `desc` (default) or `asc`.
- Each constraint and each ranking criterion may appear at most once.
- Omitting the file preserves Version 2.0 behavior (all constraints
  disabled, generation order preserved).

## How To Make Your Own Example
There are two simple options.

### Option A: Replace The Default Example Files

Edit these files directly:

```text
data/examples/CourseExample.txt
data/examples/DatesExample.txt
data/examples/ProgramsExample.txt
```

Then run:

```text
src/main.py
```

This is the easiest way when you just want to test a new dataset.

### Option B: Create Separate Files And Run Them From Code

Create new files, for example:

```text
data/examples/MyCourses.txt
data/examples/MyDates.txt
data/examples/MyPrograms.txt
```

Then call the application with custom paths:

```python
from pathlib import Path

from application.schedulixApp import PROJECT_ROOT, SchedulixApp

app = SchedulixApp()
result = app.run(
    courses_path=PROJECT_ROOT / "data" / "examples" / "MyCourses.txt",
    exam_periods_path=PROJECT_ROOT / "data" / "examples" / "MyDates.txt",
    programs_path=PROJECT_ROOT / "data" / "examples" / "MyPrograms.txt",
    output_path=PROJECT_ROOT / "data" / "outputs" / "my_exam_schedules.txt",
)

print(result)
```

## Conflict Rule

Two exams are a critical conflict when:

- they are on the same date
- they belong to the same program
- they belong to the same year
- they are not both elective courses

Two elective courses in the same program/year may be scheduled on the same date
in Version 1.0.

## Performance Notes

Schedulix generates every valid schedule option. This can grow very quickly when
you add more exam courses or more valid dates.

For example:

- 2 exam courses across many dates can generate many schedules.
- 5 or 6 exam courses across long exam periods can generate a very large output.
- Large outputs can take time to open in an editor even if generation is fast.

When testing performance, check the printed line:

```text
Runtime seconds: X.XX
```

Version 1.0 should stay under 30 seconds for the required dataset.

## Running Tests

The intended full test command is:

```powershell
python -m pytest
```

Some unit tests can also run with:

```powershell
python -m unittest discover -s tests -p "test*.py"
```

The full suite uses `pytest` features such as temporary folders, so `pytest`
must be installed to run every test normally.

## Common Problems

### File Not Found

Run `src/main.py` from PyCharm or from the project root. The code now resolves
default paths from the project folder, so normal PyCharm runs should work.

### Invalid Program Number

Check `ProgramsExample.txt`. Program IDs must be five digits and must appear in
the supported program list.

### Invalid Date

Use this date format:

```text
DD-MM-YYYY
```

Example:

```text
29-01-2026
```
