import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from fileReader.fileTypeReaders.programReader import ProgramsFileReader


class ProgramsFileReaderTests(unittest.TestCase):
    """Unit tests for selected programs file parsing."""

    def test_reads_selected_programs(self) -> None:
        """A valid programs file should return clean program numbers."""
        result = ProgramsFileReader().parse("83101, 83102, 83108")

        self.assertEqual(result, ["83101", "83102", "83108"])

    def test_ignores_empty_values_and_spaces(self) -> None:
        """Extra commas and spaces should be ignored."""
        result = ProgramsFileReader().parse("83101, , 83102 ,, 83108 ")

        self.assertEqual(result, ["83101", "83102", "83108"])

    def test_reads_more_than_five_valid_programs(self) -> None:
        """The GUI may load many programs; selection is limited on-screen."""
        result = ProgramsFileReader().parse(
            "83101,83102,83103,83104,83105,83107"
        )

        self.assertEqual(
            result,
            ["83101", "83102", "83103", "83104", "83105", "83107"],
        )

    def test_rejects_program_number_that_is_not_five_digits(self) -> None:
        """Program numbers must match the five-digit identifier format."""
        with self.assertRaises(ValueError):
            ProgramsFileReader().parse("83101, 8310A")

    def test_rejects_unsupported_program_number(self) -> None:
        """Only programs listed in the requirements document are supported."""
        with self.assertRaises(ValueError):
            ProgramsFileReader().parse("83101, 99999")


if __name__ == "__main__":
    unittest.main()
