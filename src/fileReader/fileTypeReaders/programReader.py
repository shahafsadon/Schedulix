from fileReader.baseFileReader import BaseFileReader

# Maximum number of selected programs supported in version 1.0.
MAX_PROGRAMS = 5


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

        return programs