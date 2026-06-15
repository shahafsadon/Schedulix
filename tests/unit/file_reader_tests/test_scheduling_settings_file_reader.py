"""Unit tests for the Part 3 scheduling-settings file reader (SCRUM-165)."""
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from constraint_settings import ThresholdConstraintType
from fileReader.baseFileReader import (
    FileReaderFactory,
    FileReaderType,
)
from fileReader.fileTypeReaders.schedulingSettingsReader import (
    SchedulingSettingsBundle,
    SchedulingSettingsFileReader,
)
from ranking_settings import RankingCriterion


class SchedulingSettingsFileReaderTests(unittest.TestCase):
    """Behavioural tests for the settings-file parser."""

    def test_returns_bundle_with_default_settings_for_empty_input(self) -> None:
        """An empty file produces all-disabled constraints and no ranking."""
        bundle = SchedulingSettingsFileReader().parse("")

        self.assertIsInstance(bundle, SchedulingSettingsBundle)
        self.assertEqual(bundle.ranking_settings.priority_list, [])
        for constraint_type in ThresholdConstraintType:
            setting = bundle.constraint_settings.constraints[constraint_type]
            self.assertFalse(setting.enabled)
            self.assertEqual(setting.k, 0)

    def test_parses_enabled_constraint_with_k(self) -> None:
        """A single enabled constraint line is reflected in the bundle."""
        bundle = SchedulingSettingsFileReader().parse(
            "mandatory_gap_days = on, 3"
        )

        setting = bundle.constraint_settings.constraints[
            ThresholdConstraintType.mandatory_gap_days
        ]
        self.assertTrue(setting.enabled)
        self.assertEqual(setting.k, 3)

    def test_accepts_comments_and_blank_lines(self) -> None:
        """Comment and blank lines must be ignored, not crash the parser."""
        content = (
            "# header comment\n"
            "\n"
            "mandatory_gap_days = on, 3  # inline comment\n"
            "\n"
        )
        bundle = SchedulingSettingsFileReader().parse(content)

        setting = bundle.constraint_settings.constraints[
            ThresholdConstraintType.mandatory_gap_days
        ]
        self.assertTrue(setting.enabled)
        self.assertEqual(setting.k, 3)

    def test_parses_ranking_priority_in_declared_order(self) -> None:
        """The priority list keeps the order found in the file."""
        content = (
            "ranking: min_mandatory_gap\n"
            "ranking: average_all_gap : desc\n"
            "ranking: max_exams_per_day : asc\n"
        )
        bundle = SchedulingSettingsFileReader().parse(content)

        priorities = bundle.ranking_settings.priority_list
        self.assertEqual(
            [preference.criterion for preference in priorities],
            [
                RankingCriterion.min_mandatory_gap,
                RankingCriterion.average_all_gap,
                RankingCriterion.max_exams_per_day,
            ],
        )
        self.assertTrue(priorities[0].descending)
        self.assertTrue(priorities[1].descending)
        self.assertFalse(priorities[2].descending)

    def test_allows_zero_k_for_elective_conflicts(self) -> None:
        """Req 2.3 explicitly permits k = 0 for elective collisions."""
        bundle = SchedulingSettingsFileReader().parse(
            "elective_conflicts_per_program = on, 0"
        )
        setting = bundle.constraint_settings.constraints[
            ThresholdConstraintType.elective_conflicts_per_program
        ]
        self.assertTrue(setting.enabled)
        self.assertEqual(setting.k, 0)

    def test_rejects_zero_k_when_constraint_requires_positive(self) -> None:
        """Enabled mandatory_gap_days with k = 0 must fail validation."""
        with self.assertRaises(ValueError):
            SchedulingSettingsFileReader().parse(
                "mandatory_gap_days = on, 0"
            )

    def test_rejects_negative_k(self) -> None:
        """Negative integers are never a valid threshold."""
        with self.assertRaises(ValueError):
            SchedulingSettingsFileReader().parse(
                "mandatory_gap_days = on, -1"
            )

    def test_rejects_unknown_constraint_name(self) -> None:
        """Typos in constraint names are reported with line context."""
        with self.assertRaises(ValueError):
            SchedulingSettingsFileReader().parse(
                "mandatory_gap = on, 3"
            )

    def test_rejects_unknown_ranking_criterion(self) -> None:
        """Unknown criteria must be rejected at parse time."""
        with self.assertRaises(ValueError):
            SchedulingSettingsFileReader().parse(
                "ranking: not_a_real_metric"
            )

    def test_rejects_duplicate_constraint(self) -> None:
        """Declaring the same constraint twice is ambiguous and refused."""
        content = (
            "mandatory_gap_days = on, 3\n"
            "mandatory_gap_days = on, 5\n"
        )
        with self.assertRaises(ValueError):
            SchedulingSettingsFileReader().parse(content)

    def test_rejects_duplicate_ranking_criterion(self) -> None:
        """A criterion may appear at most once in the priority list."""
        content = (
            "ranking: min_mandatory_gap\n"
            "ranking: min_mandatory_gap\n"
        )
        with self.assertRaises(ValueError):
            SchedulingSettingsFileReader().parse(content)

    def test_rejects_malformed_constraint_line(self) -> None:
        """Lines missing '=' are not valid constraint declarations."""
        with self.assertRaises(ValueError):
            SchedulingSettingsFileReader().parse(
                "mandatory_gap_days on 3"
            )

    def test_factory_returns_a_settings_reader(self) -> None:
        """The factory must recognise the new file type."""
        reader = FileReaderFactory.get_reader(
            FileReaderType.SCHEDULING_SETTINGS
        )
        self.assertIsInstance(reader, SchedulingSettingsFileReader)


if __name__ == "__main__":
    unittest.main()
