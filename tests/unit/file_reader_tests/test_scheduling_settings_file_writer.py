"""Unit tests for the Part 3 scheduling-settings file writer (SCRUM-165)."""
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"

sys.path.insert(0, str(SRC))

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from fileReader.fileTypeReaders.schedulingSettingsReader import (
    SchedulingSettingsFileReader,
)
from fileReader.fileTypeReaders.schedulingSettingsWriter import (
    SchedulingSettingsFileWriter,
)
from ranking_settings import (
    RankingCriterion,
    RankingPreference,
    RankingSettings,
)


def _sample_constraint_settings() -> SchedulingConstraintSettings:
    """Build a non-trivial constraint configuration for round-trip tests."""
    settings = SchedulingConstraintSettings.default_configuration()
    settings.constraints[ThresholdConstraintType.mandatory_gap_days] = (
        ThresholdConstraintSetting(enabled=True, k=3)
    )
    settings.constraints[ThresholdConstraintType.max_exams_per_day] = (
        ThresholdConstraintSetting(enabled=True, k=2)
    )
    return settings


def _sample_ranking_settings() -> RankingSettings:
    """Build a non-trivial ranking configuration for round-trip tests."""
    return RankingSettings(
        priority_list=[
            RankingPreference(
                criterion=RankingCriterion.min_mandatory_gap,
            ),
            RankingPreference(
                criterion=RankingCriterion.max_exams_per_day,
                descending=False,
            ),
        ]
    )


class SchedulingSettingsFileWriterTests(unittest.TestCase):
    """Behavioural tests for the settings-file writer."""

    def test_round_trip_preserves_constraint_settings(self) -> None:
        """parse(write(settings)) returns the same constraint configuration."""
        original_constraints = _sample_constraint_settings()
        original_ranking = _sample_ranking_settings()

        text = SchedulingSettingsFileWriter().format(
            original_constraints,
            original_ranking,
        )
        reparsed = SchedulingSettingsFileReader().parse(text)

        for constraint_type in ThresholdConstraintType:
            self.assertEqual(
                reparsed.constraint_settings.constraints[constraint_type],
                original_constraints.constraints[constraint_type],
            )

    def test_round_trip_preserves_ranking_settings(self) -> None:
        """parse(write(settings)) preserves criterion order and direction."""
        original_constraints = _sample_constraint_settings()
        original_ranking = _sample_ranking_settings()

        text = SchedulingSettingsFileWriter().format(
            original_constraints,
            original_ranking,
        )
        reparsed = SchedulingSettingsFileReader().parse(text)

        self.assertEqual(
            reparsed.ranking_settings.priority_list,
            original_ranking.priority_list,
        )

    def test_write_creates_file_on_disk(self) -> None:
        """write() returns the resolved path and the file is readable."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "settings.txt"

            result_path = SchedulingSettingsFileWriter().write(
                _sample_constraint_settings(),
                _sample_ranking_settings(),
                target,
            )

            self.assertTrue(result_path.exists())
            self.assertEqual(result_path, target)
            content = result_path.read_text(encoding="utf-8")
            self.assertIn("mandatory_gap_days", content)
            self.assertIn("ranking:", content)

    def test_empty_ranking_emits_placeholder_comment(self) -> None:
        """An empty priority list emits the placeholder comment, not a
        ranking: entry."""
        text = SchedulingSettingsFileWriter().format(
            SchedulingConstraintSettings.default_configuration(),
            RankingSettings(priority_list=[]),
        )
        self.assertNotIn("ranking:", text)
        self.assertIn(
            "# (none — generation order is preserved)",
            text,
        )


if __name__ == "__main__":
    unittest.main()
