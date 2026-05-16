from time import perf_counter

from application.schedulixApp import SchedulixApp

def main() -> None:
    """
    Run Schedulix with the default example files.
    """
    # Create the application object that connects all project services.
    app = SchedulixApp()

    # Run the full flow: read files, filter courses, generate schedules, write output.
    started_at = perf_counter()
    result = app.run()
    elapsed = perf_counter() - started_at

    # Print a short summary so the user can see that the run finished.
    print("Schedulix run completed successfully.")
    print(f"Selected programs: {result.selected_program_count}")
    print(f"Courses read: {result.total_course_count}")
    print(f"Relevant Exam courses: {result.relevant_course_count}")
    print(f"Exam periods read: {result.exam_period_count}")
    print(f"Schedules generated: {result.schedule_count}")
    print(f"Output file: {result.output_path}")
    print(f"Runtime seconds: {elapsed:.2f}")

if __name__ == "__main__":
    main()
