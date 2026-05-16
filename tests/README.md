# Schedulix Test Suite

This folder is organized by test level and then by the part of the flow being
checked.

## Structure

```text
tests/
  unit/
    file_reader_tests/     Tests one reader at a time.
    scheduling_tests/      Tests scheduling rules and helpers.
    output_tests/          Tests output formatting and file writing.
  integration/
    file_reader_flow/      Checks readers working together with filtering/date logic.
    scheduling_flow/       Checks filter output feeding the scheduler and conflict rules.
    application_flow/      Checks the SchedulixApp orchestration with real or temp files.
  system/
    full_flow/             Runs the full example-file system from input to output.
```

## How To Run

The intended full-suite command is:

```bash
python -m pytest
```

The current tests use `pytest` features such as `tmp_path`, especially in
integration and system tests. Some unit tests are written with `unittest`, so
this command can run only that subset:

```bash
python -m unittest discover -s tests -p "test*.py"
```

## Notes For The Tester

- Unit tests should stay small and focused on one class or function.
- Integration tests should prove that two or more project parts work together.
- System tests should use the real example files and verify the user-visible
  result.
- If a test needs temporary input or output files, use `tmp_path` so the repo
  is not changed by the test run.
- The output contract is important: one `Schedule N` should represent a full
  exam-system option, separated inside by semester and moed.
- The project currently expects Python plus `pytest` for the full test suite.
