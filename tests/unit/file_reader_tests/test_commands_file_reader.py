import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from fileReader.baseFileReader import FileReaderFactory, FileReaderType
from fileReader.fileTypeReaders.commandsFileReader import CommandsFileReader, CommandType, ParsedCommand


class CommandsFileReaderTests(unittest.TestCase):
    """Unit tests for commands file reader parsing."""

    def test_parses_move_command(self) -> None:
        """A valid MOVE command should be parsed correctly."""
        content = "MOVE 83115 TO 12-07-2026"
        result = CommandsFileReader().parse(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].command_type, CommandType.MOVE)
        self.assertEqual(result[0].parameters["course_id"], "83115")
        self.assertEqual(result[0].parameters["new_date"], "12-07-2026")
        self.assertEqual(result[0].line_number, 1)

    def test_parses_save_snapshot_command(self) -> None:
        """A valid SAVE_SNAPSHOT command should be parsed correctly."""
        content = "SAVE_SNAPSHOT Initial_State"
        result = CommandsFileReader().parse(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].command_type, CommandType.SAVE_SNAPSHOT)
        self.assertEqual(result[0].parameters["name"], "Initial_State")
        self.assertEqual(result[0].line_number, 1)

    def test_parses_load_snapshot_command(self) -> None:
        """A valid LOAD_SNAPSHOT command should be parsed correctly."""
        content = "LOAD_SNAPSHOT Initial_State"
        result = CommandsFileReader().parse(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].command_type, CommandType.LOAD_SNAPSHOT)
        self.assertEqual(result[0].parameters["name"], "Initial_State")
        self.assertEqual(result[0].line_number, 1)

    def test_parses_compare_command(self) -> None:
        """A valid COMPARE command should be parsed correctly."""
        content = "COMPARE snapA snapB"
        result = CommandsFileReader().parse(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].command_type, CommandType.COMPARE)
        self.assertEqual(result[0].parameters["name_a"], "snapA")
        self.assertEqual(result[0].parameters["name_b"], "snapB")
        self.assertEqual(result[0].line_number, 1)

    def test_parses_snapshot_name_with_spaces(self) -> None:
        """Snapshot commands should support names containing spaces."""
        content = (
            "SAVE_SNAPSHOT 'My Initial Snapshot'\n"
            "LOAD_SNAPSHOT \"My Custom Snapshot\"\n"
            "COMPARE \"My Initial Snapshot\" \"My Custom Snapshot\""
        )
        result = CommandsFileReader().parse(content)
        self.assertEqual(len(result), 3)

        self.assertEqual(result[0].command_type, CommandType.SAVE_SNAPSHOT)
        self.assertEqual(result[0].parameters["name"], "My Initial Snapshot")

        self.assertEqual(result[1].command_type, CommandType.LOAD_SNAPSHOT)
        self.assertEqual(result[1].parameters["name"], "My Custom Snapshot")

        self.assertEqual(result[2].command_type, CommandType.COMPARE)
        self.assertEqual(result[2].parameters["name_a"], "My Initial Snapshot")
        self.assertEqual(result[2].parameters["name_b"], "My Custom Snapshot")

    def test_ignores_comments_and_blank_lines(self) -> None:
        """Comments (including inline comments) and empty lines should be ignored."""
        content = (
            "\n"
            "# This is a comment\n"
            "SAVE_SNAPSHOT StateA  # Inline comment here\n"
            "   \n"
            "COMPARE StateA StateB"
        )
        result = CommandsFileReader().parse(content)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].command_type, CommandType.SAVE_SNAPSHOT)
        self.assertEqual(result[0].parameters["name"], "StateA")
        self.assertEqual(result[0].line_number, 3)
        self.assertEqual(result[1].command_type, CommandType.COMPARE)
        self.assertEqual(result[1].line_number, 5)

    def test_rejects_unknown_command_with_line_number(self) -> None:
        """An unrecognized command should raise ValueError indicating the line number."""
        content = "UNKNOWN snapA"
        with self.assertRaises(ValueError) as context:
            CommandsFileReader().parse(content)
        self.assertIn("Line 1", str(context.exception))
        self.assertIn("Unrecognized command: 'UNKNOWN'", str(context.exception))

    def test_rejects_malformed_move_command(self) -> None:
        """A MOVE command missing TO or course ID or date should raise ValueError."""
        invalid_commands = [
            "MOVE 83115 12-07-2026",
            "MOVE 83115 TO",
            "MOVE TO 12-07-2026",
            "MOVE TO",
        ]
        for cmd in invalid_commands:
            with self.assertRaises(ValueError) as context:
                CommandsFileReader().parse(cmd)
            self.assertIn("Malformed MOVE command", str(context.exception))

    def test_rejects_compare_with_wrong_number_of_arguments(self) -> None:
        """COMPARE command with wrong number of arguments should raise ValueError."""
        invalid_commands = [
            "COMPARE snapA",
            "COMPARE snapA snapB snapC",
            "COMPARE",
        ]
        for cmd in invalid_commands:
            with self.assertRaises(ValueError) as context:
                CommandsFileReader().parse(cmd)
            self.assertIn("Malformed COMPARE command", str(context.exception))

    def test_returns_empty_list_for_empty_file(self) -> None:
        """An empty file or a file with only comments should return an empty list."""
        self.assertEqual(CommandsFileReader().parse(""), [])
        self.assertEqual(CommandsFileReader().parse("# only comments\n   # another one"), [])

    def test_factory_returns_commands_reader(self) -> None:
        """FileReaderFactory should return an instance of CommandsFileReader."""
        reader = FileReaderFactory.get_reader(FileReaderType.COMMANDS)
        self.assertIsInstance(reader, CommandsFileReader)


if __name__ == "__main__":
    unittest.main()
