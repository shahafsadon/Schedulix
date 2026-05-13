from models import Course, ProgramEnrollment


class CourseFilter:
    """
    Selects the courses that should take part in the scheduling process.

    A course is relevant only if it has an Exam evaluation type and belongs to
    at least one of the selected study programs.
    """

    def filter_relevant_courses(
        self,
        courses: list[Course],
        selected_programs: list[str],
    ) -> list[Course]:
        """
        Return the relevant courses for the selected programs.

        The returned Course objects keep the original course details, but their
        programs list contains only the enrollments that match the selected
        programs.
        """
        selected_program_set = set(selected_programs)
        relevant_courses: list[Course] = []

        for course in courses:
            if course.evaluation_type.strip().lower() != "exam":
                continue

            matching_programs = self._matching_programs(
                course.programs,
                selected_program_set,
            )

            if not matching_programs:
                continue

            relevant_courses.append(
                Course(
                    name=course.name,
                    course_number=course.course_number,
                    instructor=course.instructor,
                    programs=matching_programs,
                    evaluation_type=course.evaluation_type,
                )
            )

        return relevant_courses

    @staticmethod
    def _matching_programs(
        programs: list[ProgramEnrollment],
        selected_programs: set[str],
    ) -> list[ProgramEnrollment]:
        """Keep only program enrollments that belong to the selected programs."""
        return [
            program
            for program in programs
            if program.program_number in selected_programs
        ]