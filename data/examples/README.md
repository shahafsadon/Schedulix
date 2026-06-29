# Official Schedulix Demo Data

This folder contains the three official demo scenarios for the live
presentation. Each demo folder is self-contained and includes:

- `programs.txt`
- `courses.txt`
- `dates.txt`
- `settings.txt`
- `README.md`

When the GUI uploads `programs.txt`, `courses.txt`, and `dates.txt` from the
same folder, Schedulix automatically preloads the colocated `settings.txt`
before the scheduling settings screen. The user can still edit settings
manually afterward.

| Demo | Purpose | Expected Result | Detailed Guide |
| --- | --- | --- | --- |
| `basic_course_example` | Normal generation and progressive ranking over a large schedule universe | About `76,032` valid schedules; ranking preview starts as Top 50 | [README](basic_course_example/README.md) |
| `quality_snapshot_demo` | Manual move, snapshots, and snapshot comparison | `56` schedules; `System 1` improves from `Risky` to `Excellent` | [README](quality_snapshot_demo/README.md) |
| `fallback_compromise_demo` | Fallback path when no strict schedule satisfies the soft threshold constraints | Prompt appears; compromise schedule has penalty `50` and one violation | [README](fallback_compromise_demo/README.md) |

## Recommended Live Demo Order

1. Start with `basic_course_example` to show normal generation and the full
   schedule count.
2. Use the same generated schedules to show progressive ranking and full ranked
   browsing.
3. Switch to `quality_snapshot_demo` to show manual editing and comparison.
4. Finish with `fallback_compromise_demo` to show the no-valid-strict-schedule
   compromise flow.
