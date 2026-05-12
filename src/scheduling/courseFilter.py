from models import Course, ProgramEnrollment


class CourseFilter:
    """
    Filters courses before they are sent to the scheduling algorithm.
    The scheduler only needs courses that belong to the selected programs and
    have an Exam evaluation type.
    """

    def filter_relevant_courses(
        self,
        courses: list[Course],
        selected_programs: list[str],
    ) -> list[Course]:
        """
        Return only Exam courses that belong to the selected programs.
        Each returned course keeps only the program enrollment rows that match
        the selected programs.
        """
        selected_program_set = set(selected_programs)
        relevant_courses: list[Course] = []

        for course in courses:
            if course.evaluation_type != "Exam":
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
        """Return only enrollment rows that match selected programs."""
        return [
            program
            for program in programs
            if program.program_number in selected_programs
        ]
