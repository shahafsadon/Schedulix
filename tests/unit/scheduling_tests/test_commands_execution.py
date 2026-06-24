import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from application.schedulixApp import SchedulixApp
from fileReader.fileTypeReaders.commandsFileReader import CommandType, ParsedCommand
from scheduling.scheduleSnapshot import SnapshotManager
from scheduling.scheduleIntrospection import flatten_exam_system
from ._part4_helpers import make_exam, make_system


class TestCommandsExecution(unittest.TestCase):
    """Unit tests for snapshot and move command execution in SchedulixApp."""

    def setUp(self) -> None:
        self.app = SchedulixApp()
        self.initial_schedule = make_system(
            make_exam("83115", date(2026, 7, 10)),
            make_exam("83101", date(2026, 7, 15)),
        )
        self.snapshot_manager = SnapshotManager()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.diff_report_path = Path(self.temp_dir.name) / "diff_report.txt"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_move_command_updates_active_schedule(self) -> None:
        """MOVE command should successfully update the active schedule."""
        cmd = ParsedCommand(
            command_type=CommandType.MOVE,
            parameters={"course_id": "83115", "new_date": "12-07-2026"},
            line_number=1,
            raw_line="MOVE 83115 TO 12-07-2026",
        )
        active_schedule, errors, diff_path, executed = self.app._execute_commands(
            commands=[cmd],
            initial_schedule=self.initial_schedule,
            snapshot_manager=self.snapshot_manager,
            diff_report_path=self.diff_report_path,
        )
        self.assertEqual(executed, 1)
        self.assertEqual(len(errors), 0)
        self.assertIsNone(diff_path)
        
        # Verify the course has indeed been moved to date(2026, 7, 12)
        exams = flatten_exam_system(active_schedule)
        moved_exam = next(e for e in exams if e.course_id == "83115")
        self.assertEqual(moved_exam.exam_date, date(2026, 7, 12))

    def test_move_command_invalid_course_id_logs_error(self) -> None:
        """MOVE command with an invalid course ID should log an error and leave the schedule unchanged."""
        cmd = ParsedCommand(
            command_type=CommandType.MOVE,
            parameters={"course_id": "99999", "new_date": "12-07-2026"},
            line_number=1,
            raw_line="MOVE 99999 TO 12-07-2026",
        )
        active_schedule, errors, diff_path, executed = self.app._execute_commands(
            commands=[cmd],
            initial_schedule=self.initial_schedule,
            snapshot_manager=self.snapshot_manager,
            diff_report_path=self.diff_report_path,
        )
        self.assertEqual(executed, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("Line 1", errors[0])
        # The schedule should remain unchanged
        self.assertEqual(active_schedule, self.initial_schedule)

    def test_save_snapshot_stores_named_snapshot(self) -> None:
        """SAVE_SNAPSHOT should save the active schedule in the SnapshotManager."""
        cmd = ParsedCommand(
            command_type=CommandType.SAVE_SNAPSHOT,
            parameters={"name": "Snap1"},
            line_number=1,
            raw_line="SAVE_SNAPSHOT Snap1",
        )
        _, errors, _, executed = self.app._execute_commands(
            commands=[cmd],
            initial_schedule=self.initial_schedule,
            snapshot_manager=self.snapshot_manager,
            diff_report_path=self.diff_report_path,
        )
        self.assertEqual(executed, 1)
        self.assertEqual(len(errors), 0)
        
        # Verify snapshot is in manager
        snapshots = self.snapshot_manager.list_snapshots()
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].name, "Snap1")

    def test_load_snapshot_restores_schedule(self) -> None:
        """LOAD_SNAPSHOT should restore the active schedule to a previously saved snapshot."""
        # Setup: save a snapshot "Snap1" in manager manually
        self.snapshot_manager.set_active_schedule(self.initial_schedule)
        self.snapshot_manager.save_current("Snap1")
        
        # Modify active schedule via a move
        cmd_move = ParsedCommand(
            command_type=CommandType.MOVE,
            parameters={"course_id": "83115", "new_date": "12-07-2026"},
            line_number=1,
            raw_line="MOVE 83115 TO 12-07-2026",
        )
        # Load snapshot "Snap1"
        cmd_load = ParsedCommand(
            command_type=CommandType.LOAD_SNAPSHOT,
            parameters={"name": "Snap1"},
            line_number=2,
            raw_line="LOAD_SNAPSHOT Snap1",
        )
        active_schedule, errors, _, executed = self.app._execute_commands(
            commands=[cmd_move, cmd_load],
            initial_schedule=self.initial_schedule,
            snapshot_manager=self.snapshot_manager,
            diff_report_path=self.diff_report_path,
        )
        self.assertEqual(executed, 2)
        self.assertEqual(len(errors), 0)
        # The returned active schedule should match initial_schedule (restored from Snap1)
        self.assertEqual(active_schedule, self.initial_schedule)

    def test_load_snapshot_unknown_name_logs_error(self) -> None:
        """LOAD_SNAPSHOT with an unknown snapshot name should log an error and leave schedule unchanged."""
        cmd = ParsedCommand(
            command_type=CommandType.LOAD_SNAPSHOT,
            parameters={"name": "UnknownSnap"},
            line_number=1,
            raw_line="LOAD_SNAPSHOT UnknownSnap",
        )
        active_schedule, errors, _, executed = self.app._execute_commands(
            commands=[cmd],
            initial_schedule=self.initial_schedule,
            snapshot_manager=self.snapshot_manager,
            diff_report_path=self.diff_report_path,
        )
        self.assertEqual(executed, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("Line 1", errors[0])
        self.assertIn("Snapshot was not found: UnknownSnap", errors[0])
        self.assertEqual(active_schedule, self.initial_schedule)

    def test_compare_generates_diff_report_file(self) -> None:
        """COMPARE command should generate a diff report file at the target path."""
        # Setup: save Snap1, move an exam, save Snap2
        self.snapshot_manager.set_active_schedule(self.initial_schedule)
        self.snapshot_manager.save_current("Snap1")
        
        moved_schedule = make_system(
            make_exam("83115", date(2026, 7, 12)),
            make_exam("83101", date(2026, 7, 15)),
        )
        self.snapshot_manager.set_active_schedule(moved_schedule)
        self.snapshot_manager.save_current("Snap2")
        
        cmd_compare = ParsedCommand(
            command_type=CommandType.COMPARE,
            parameters={"name_a": "Snap1", "name_b": "Snap2"},
            line_number=1,
            raw_line="COMPARE Snap1 Snap2",
        )
        _, errors, diff_path, executed = self.app._execute_commands(
            commands=[cmd_compare],
            initial_schedule=moved_schedule,
            snapshot_manager=self.snapshot_manager,
            diff_report_path=self.diff_report_path,
        )
        self.assertEqual(executed, 1)
        self.assertEqual(len(errors), 0)
        self.assertEqual(diff_path, self.diff_report_path)
        self.assertTrue(self.diff_report_path.exists())
        
        # Verify content contains snapshot comparison report and details of move
        content = self.diff_report_path.read_text(encoding="utf-8")
        self.assertIn("Snapshot Comparison Report", content)
        self.assertIn("From: Snap1", content)
        self.assertIn("To:   Snap2", content)
        self.assertIn("Changed courses:", content)
        self.assertIn("83115", content)

    def test_compare_unknown_snapshot_logs_error(self) -> None:
        """COMPARE command referencing an unknown snapshot should log an error."""
        self.snapshot_manager.set_active_schedule(self.initial_schedule)
        self.snapshot_manager.save_current("Snap1")
        
        cmd_compare = ParsedCommand(
            command_type=CommandType.COMPARE,
            parameters={"name_a": "Snap1", "name_b": "UnknownSnap"},
            line_number=1,
            raw_line="COMPARE Snap1 UnknownSnap",
        )
        _, errors, diff_path, executed = self.app._execute_commands(
            commands=[cmd_compare],
            initial_schedule=self.initial_schedule,
            snapshot_manager=self.snapshot_manager,
            diff_report_path=self.diff_report_path,
        )
        self.assertEqual(executed, 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("Line 1", errors[0])
        self.assertIn("Snapshot was not found: UnknownSnap", errors[0])
        self.assertIsNone(diff_path)

    def test_multiple_commands_execute_in_order(self) -> None:
        """A series of commands should be executed sequentially, maintaining the correct state transition."""
        commands = [
            ParsedCommand(
                command_type=CommandType.SAVE_SNAPSHOT,
                parameters={"name": "SnapA"},
                line_number=1,
                raw_line="SAVE_SNAPSHOT SnapA",
            ),
            ParsedCommand(
                command_type=CommandType.MOVE,
                parameters={"course_id": "83115", "new_date": "12-07-2026"},
                line_number=2,
                raw_line="MOVE 83115 TO 12-07-2026",
            ),
            ParsedCommand(
                command_type=CommandType.SAVE_SNAPSHOT,
                parameters={"name": "SnapB"},
                line_number=3,
                raw_line="SAVE_SNAPSHOT SnapB",
            ),
            ParsedCommand(
                command_type=CommandType.COMPARE,
                parameters={"name_a": "SnapA", "name_b": "SnapB"},
                line_number=4,
                raw_line="COMPARE SnapA SnapB",
            ),
        ]
        active_schedule, errors, diff_path, executed = self.app._execute_commands(
            commands=commands,
            initial_schedule=self.initial_schedule,
            snapshot_manager=self.snapshot_manager,
            diff_report_path=self.diff_report_path,
        )
        self.assertEqual(executed, 4)
        self.assertEqual(len(errors), 0)
        self.assertEqual(diff_path, self.diff_report_path)
        self.assertTrue(self.diff_report_path.exists())
        
        # Verify SnapA and SnapB exist
        snapshots = {s.name: s for s in self.snapshot_manager.list_snapshots()}
        self.assertIn("SnapA", snapshots)
        self.assertIn("SnapB", snapshots)

    def test_error_in_one_command_does_not_stop_execution(self) -> None:
        """An error executing one command should not interrupt subsequent commands."""
        commands = [
            # 1. Invalid move (should log error, but continue)
            ParsedCommand(
                command_type=CommandType.MOVE,
                parameters={"course_id": "99999", "new_date": "12-07-2026"},
                line_number=1,
                raw_line="MOVE 99999 TO 12-07-2026",
            ),
            # 2. Valid save
            ParsedCommand(
                command_type=CommandType.SAVE_SNAPSHOT,
                parameters={"name": "SnapOk"},
                line_number=2,
                raw_line="SAVE_SNAPSHOT SnapOk",
            ),
        ]
        _, errors, _, executed = self.app._execute_commands(
            commands=commands,
            initial_schedule=self.initial_schedule,
            snapshot_manager=self.snapshot_manager,
            diff_report_path=self.diff_report_path,
        )
        self.assertEqual(executed, 2)
        self.assertEqual(len(errors), 1)
        self.assertIn("Line 1", errors[0])
        # Verify subsequent command executed
        self.assertIn("SnapOk", [s.name for s in self.snapshot_manager.list_snapshots()])


if __name__ == "__main__":
    unittest.main()
