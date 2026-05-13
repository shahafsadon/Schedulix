from fileReader.baseFileReader import BaseFileReader

# The business rule: no exam schedule should cover more than 5 programs at once.
# Defined as a constant so it's easy to find and change if the rule ever shifts.
MAX_PROGRAMS = 5


class ProgramsFileReader(BaseFileReader[list[str]]):
    """
    Reads the programs input file and returns a list of program number strings.

    The file is intentionally simple — just a comma-separated list on one line:
        83101, 83102, 83108

    The reader's only real job beyond splitting is enforcing the cap on how
    many programs can be scheduled together (see MAX_PROGRAMS).
    """

    def parse(self, content: str) -> list[str]:
        """
        Split the comma-separated content into individual program numbers.

        We strip whitespace from each entry so that "83101 , 83102" and
        "83101,83102" are treated identically — the file format should be
        forgiving of minor formatting differences.
        """
        # Split on commas, strip surrounding whitespace, and drop any empty
        # tokens (e.g. a trailing comma would otherwise produce an empty string)
        programs = [p.strip() for p in content.split(",") if p.strip()]

        if len(programs) > MAX_PROGRAMS:
            raise ValueError(
                f"Program file contains {len(programs)} programs; "
                f"maximum allowed is {MAX_PROGRAMS}."
            )

        return programs