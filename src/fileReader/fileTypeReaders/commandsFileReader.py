"""Reads and parses a text file containing schedule snapshot commands.

Each command is parsed line by line. Blank lines and comments (starting with #)
are ignored. If a line contains an unrecognized command or has malformed
parameters, a ValueError is raised.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from enum import Enum

from fileReader.baseFileReader import BaseFileReader


class CommandType(Enum):
    """Supported snapshot and move commands."""

    MOVE = "MOVE"
    SAVE_SNAPSHOT = "SAVE_SNAPSHOT"
    LOAD_SNAPSHOT = "LOAD_SNAPSHOT"
    COMPARE = "COMPARE"


@dataclass(frozen=True)
class ParsedCommand:
    """A structured representation of a parsed command from a commands file."""

    command_type: CommandType
    parameters: dict[str, str]
    line_number: int
    raw_line: str


class CommandsFileReader(BaseFileReader[list[ParsedCommand]]):
    """File reader that parses list of commands from a text file."""

    def parse(self, content: str) -> list[ParsedCommand]:
        """Parse raw text content of commands file into ParsedCommand objects.

        Args:
            content: The raw text contents of the commands file.

        Returns:
            A list of ParsedCommand objects representing the valid commands.

        Raises:
            ValueError: If any command is unrecognized or malformed.
        """
        lines = content.splitlines()
        parsed_commands: list[ParsedCommand] = []

        for idx, line in enumerate(lines, start=1):
            # Extract inline comments starting with '#'
            clean_line = line.split("#", 1)[0].strip()
            if not clean_line:
                continue

            # Split command verb and arguments
            parts = clean_line.split(maxsplit=1)
            verb = parts[0].upper()
            args_str = parts[1].strip() if len(parts) > 1 else ""

            if verb == "MOVE":
                # Matches "MOVE [Course_ID] TO [New_Date]" (case-insensitive "TO")
                match = re.match(r"^(.+?)\s+\bTO\b\s+(.+)$", args_str, re.IGNORECASE)
                if not match:
                    raise ValueError(
                        f"Line {idx}: Malformed MOVE command. "
                        f"Expected format: MOVE [Course_ID] TO [New_Date]"
                    )
                course_id = match.group(1).strip().strip("'\"")
                new_date = match.group(2).strip().strip("'\"")
                if not course_id or not new_date:
                    raise ValueError(
                        f"Line {idx}: Malformed MOVE command. "
                        f"Course ID and New Date must not be empty."
                    )
                parsed_commands.append(
                    ParsedCommand(
                        command_type=CommandType.MOVE,
                        parameters={"course_id": course_id, "new_date": new_date},
                        line_number=idx,
                        raw_line=line,
                    )
                )

            elif verb == "SAVE_SNAPSHOT":
                name = args_str.strip().strip("'\"")
                if not name:
                    raise ValueError(
                        f"Line {idx}: Malformed SAVE_SNAPSHOT command. "
                        f"Expected snapshot name."
                    )
                parsed_commands.append(
                    ParsedCommand(
                        command_type=CommandType.SAVE_SNAPSHOT,
                        parameters={"name": name},
                        line_number=idx,
                        raw_line=line,
                    )
                )

            elif verb == "LOAD_SNAPSHOT":
                name = args_str.strip().strip("'\"")
                if not name:
                    raise ValueError(
                        f"Line {idx}: Malformed LOAD_SNAPSHOT command. "
                        f"Expected snapshot name."
                    )
                parsed_commands.append(
                    ParsedCommand(
                        command_type=CommandType.LOAD_SNAPSHOT,
                        parameters={"name": name},
                        line_number=idx,
                        raw_line=line,
                    )
                )

            elif verb == "COMPARE":
                try:
                    args = shlex.split(args_str)
                except ValueError as error:
                    raise ValueError(
                        f"Line {idx}: Malformed COMPARE command quotes: {error}"
                    ) from error

                if len(args) != 2:
                    raise ValueError(
                        f"Line {idx}: Malformed COMPARE command. "
                        f"Expected exactly 2 arguments, got {len(args)}."
                    )

                name_a = args[0].strip()
                name_b = args[1].strip()
                if not name_a or not name_b:
                    raise ValueError(
                        f"Line {idx}: Malformed COMPARE command. "
                        f"Snapshot names cannot be empty."
                    )

                parsed_commands.append(
                    ParsedCommand(
                        command_type=CommandType.COMPARE,
                        parameters={"name_a": name_a, "name_b": name_b},
                        line_number=idx,
                        raw_line=line,
                    )
                )

            else:
                raise ValueError(f"Line {idx}: Unrecognized command: '{verb}'")

        return parsed_commands
