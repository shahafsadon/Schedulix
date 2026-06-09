from fileReader.baseFileReader import BaseFileReader


VALID_PROGRAMS = {
    "83101",
    "83102",
    "83104",
    "83107",
    "83108",
    "83109",
    "83105",
    "83182",
    "83103",
    "83115",
}


class ProgramsFileReader(BaseFileReader[list[str]]):
    """Reads the comma-separated selected-programs file."""

    def parse(
        self,
        content: str,
    ) -> list[str]:
        programs = [
            part.strip()
            for part in content.split(",")
            if part.strip()
        ]

        if not programs:
            raise ValueError(
                "Programs file must select at least one program."
            )

        unique_programs: list[str] = []
        seen: set[str] = set()

        for program in programs:
            if not program.isdigit() or len(program) != 5:
                raise ValueError(
                    f"Invalid program number: '{program}'"
                )

            if program not in VALID_PROGRAMS:
                raise ValueError(
                    f"Unsupported program number: '{program}'"
                )

            if program not in seen:
                unique_programs.append(program)
                seen.add(program)

        return unique_programs
