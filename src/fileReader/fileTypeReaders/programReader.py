from fileReader.baseFileReader import BaseFileReader

# Maximum number of selected programs supported in version 1.0.
MAX_PROGRAMS = 5

# Study programs supported by the requirements document.
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
    """
    Reads the selected programs input file.

    The file contains program numbers separated by commas.
    """

    def parse(self, content: str) -> list[str]:
        """
        Parse the selected program numbers from the file content.
        """
        # Split by comma, remove surrounding spaces, and ignore empty values.
        programs = [p.strip() for p in content.split(",") if p.strip()]

        if len(programs) > MAX_PROGRAMS:
            raise ValueError(
                f"Program file contains {len(programs)} programs; "
                f"maximum allowed is {MAX_PROGRAMS}."
            )

        for program in programs:
            if not program.isdigit() or len(program) != 5:
                raise ValueError(f"Invalid program number: '{program}'")

            if program not in VALID_PROGRAMS:
                raise ValueError(f"Unsupported program number: '{program}'")

        return programs
