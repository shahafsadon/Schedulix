# SCRUM-114 — Implement Command Infrastructure

## Background

The Jira task asks for a **Command pattern** layer that decouples UI click
events (e.g., toggling a calendar date) from the underlying date-modification
logic in `ExamDateHandler`.

### Key observations from the codebase

| Component | Location | Role |
|---|---|---|
| `ExamDateHandler` | `src/scheduling/examDateHandler.py` | **Stateless** — builds valid-date lists from an `ExamPeriod`. No mutable state on the handler itself. |
| `ExamPeriod` | `src/models.py` | Mutable dataclass with `excluded_dates: list[date]`. This is the **receiver** the commands mutate. |
| `ExamScheduleGenerator` | `src/scheduling/examScheduleGenerator.py` | Consumes `ExamPeriod` + courses → `ExamSystem` list. A "regenerate" command will call this. |
| `CacheManager` | `src/application/cache_manager.py` | Holds the canonical in-RAM (+ pickled) exam periods and generated schedules. |

> [!IMPORTANT]
> `ExamDateHandler` is stateless — it has no `excluded_dates` list of its own.
> Mutation of blocked dates lives on `ExamPeriod`. Commands therefore operate on
> an `ExamPeriod` object (and optionally a `CacheManager`) rather than on the
> handler directly, then call `ExamDateHandler.get_valid_dates()` to recompute.
> This keeps Version 1.0 code completely untouched.

---

## Proposed Changes

### Component 1 — Command interface + concrete commands

#### [NEW] [commands.py](file:///c:/Users/Liran/Desktop/פרוייקט הנדסת תוכנה/Schedulix/src/application/commands.py)

**`Command` (ABC)** — defines `execute() -> CommandResult` and `undo() -> CommandResult`.

**`CommandResult` (frozen dataclass)** — lightweight result envelope:
```python
@dataclass(frozen=True)
class CommandResult:
    success: bool
    message: str = ""
    data: Any = None
```

**Concrete command classes** (all stateless-friendly, all DI-constructed):

| Class | Receiver(s) | `execute()` behaviour |
|---|---|---|
| `ExcludeDateCommand` | `ExamPeriod`, `ExamDateHandler` | Adds a `date` to `exam_period.excluded_dates`; returns updated valid-date list in `data` |
| `ActivateDateCommand` | `ExamPeriod`, `ExamDateHandler` | Removes a `date` from `exam_period.excluded_dates`; returns updated valid-date list |
| `ToggleDateExceptionCommand` | `ExamPeriod`, `ExamDateHandler` | Delegates to `ExcludeDateCommand` or `ActivateDateCommand` depending on current state; supports `undo()` by reversing the toggle |
| `RegenerateSchedulesCommand` | `ExamScheduleGenerator`, `CacheManager`, courses + periods | Runs `generate_exam_systems()`; writes result to `cache.set_generated_schedules()` |

All commands store their injected receivers and target date as constructor
arguments — no Singleton access, full DI.

---

### Component 2 — Date Management Presenter

#### [NEW] [dateManagementPresenter.py](file:///c:/Users/Liran/Desktop/פרוייקט הנדסת תוכנה/Schedulix/src/gui/dateManagementPresenter.py)

The Presenter is the "Invoker" in Command-pattern terminology. It:

- Holds a reference to the current `ExamPeriod` and `ExamDateHandler`.
- Exposes `on_date_clicked(d: date) -> CommandResult` — builds a
  `ToggleDateExceptionCommand` on the fly and calls `execute()`.
- Exposes `on_regenerate() -> CommandResult` — builds and executes a
  `RegenerateSchedulesCommand`.
- Keeps `_last_command` so a View can later call `undo()` via
  `presenter.undo_last()`.

No ctk imports — fully testable without a display.

---

### Component 3 — Unit Tests

#### [NEW] [test_commands.py](file:///c:/Users/Liran/Desktop/פרוייקט הנדסת תוכנה/Schedulix/tests/unit/scheduling_tests/test_commands.py)

| Test class | # tests | What it covers |
|---|---|---|
| `TestExcludeDateCommand` | 4 | Adds date to period, updates valid-date list, idempotent on duplicate, `data` field |
| `TestActivateDateCommand` | 4 | Removes date from period, updates valid-date list, no-op when not excluded, `data` field |
| `TestToggleDateExceptionCommand` | 5 | Toggle exclude → activate → exclude cycle, `undo()` reverses state, `success` flag |
| `TestRegenerateSchedulesCommand` | 4 | Result written to cache, `success=True`, empty courses → empty schedules, `data` matches |
| `TestDateManagementPresenter` | 5 | `on_date_clicked` toggles correctly, `undo_last` reverses, `on_regenerate` writes to cache |

**22 tests total, zero GUI / no ctk imports.**

---

## Files Left Untouched

- `src/scheduling/examDateHandler.py` — not modified
- `src/scheduling/examScheduleGenerator.py` — not modified
- `src/models.py` — not modified
- All other Version 1.0 files — not modified
- All existing tests — not modified

---

## Verification Plan

```bash
# Run only the new command tests
python -m pytest tests/unit/scheduling_tests/test_commands.py -v

# Confirm zero regressions
python -m pytest -v
```
