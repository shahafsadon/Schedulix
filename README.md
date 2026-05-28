# Schedulix

Schedulix is a Python exam-scheduling system for Version 1.0 of the Software
Engineering project.

The system reads course data, exam-period data, and selected study programs from
text files. It then generates every valid exam-system option that avoids the
critical conflicts defined for Version 1.0, and writes the result to a readable
output text file.

## Version 1.0 Scope

Version 1.0 supports a file-based workflow:

1. Read selected study programs.
2. Read all course records.
3. Read exam periods and blocked dates.
4. Keep only relevant courses:
   - courses that belong to the selected programs
   - courses whose evaluation type is `Exam`
5. Generate all valid exam-system options.
6. Write the schedules to a readable text output file.
7. Print a short run summary, including runtime in seconds.

Version 1.0 checks conflicts by date only. It does not handle exam hours,
classrooms, student-level repeat courses, preference ranking, or UI filtering.

## Project Structure

```text
Schedulix/
|-- data/
|   |-- examples/
|   |   |-- CourseExample.txt        # Example course records
|   |   |-- DatesExample.txt         # Example exam periods and excluded dates
|   |   `-- ProgramsExample.txt      # Example selected study programs
|   |-- outputs/
|   |   `-- exam_schedules.txt       # Generated output file after running the system
|   `-- output/                      # Old/unused output folder placeholder
|-- src/
|   |-- main.py                      # Main file to run from PyCharm or terminal
|   |-- models.py                    # Shared data classes: Course, ProgramEnrollment, ExamPeriod
|   |-- application/
|   |   `-- schedulixApp.py          # Connects readers, filtering, scheduling, and output
|   |-- fileReader/
|   |   |-- baseFileReader.py        # Shared reader base class and reader factory
|   |   `-- fileTypeReaders/
|   |       |-- coursesReader.py     # Parses CourseExample-style course files
|   |       |-- examPeriodsReader.py # Parses DatesExample-style exam-period files
|   |       `-- programReader.py     # Parses selected program files
|   |-- output/
|   |   `-- outputWriter.py          # Formats and writes readable schedule output
|   |-- gui/
|   |   |-- mainGui.py               # Opens the Version 2.0 file upload window
|   |   |-- fileUploadScreen.py      # customTkinter screen for choosing input files
|   |   `-- uploadService.py         # Validates uploaded files with existing readers
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

### Run From PyCharm

1. Open `src/main.py`.
2. Press the green Run button.
3. After the run finishes, open:

```text
data/outputs/exam_schedules.txt
```

### Run From Terminal

From the project root:

```powershell
cd C:\Users\user\Desktop\Schedulix
python src\main.py
```

If `python` is not recognized on your computer, run it from PyCharm instead.

### Run The Version 2.0 Upload Window

Install the GUI dependency once from the project root:

```powershell
cd C:\Users\user\Desktop\Schedulix
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The SCRUM-117 upload workflow can be opened from the project root:

```powershell
cd C:\Users\user\Desktop\Schedulix
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe -m gui.mainGui
```

The window lets the user choose courses, programs, and exam-period files. Each
file is validated with the existing file readers, and the screen shows success
or error feedback for each upload.

The upload window uses `customtkinter`, as planned in the Version 2.0 software
design document. If a teammate does not have a `.venv` folder yet, create it
first and then install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

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
