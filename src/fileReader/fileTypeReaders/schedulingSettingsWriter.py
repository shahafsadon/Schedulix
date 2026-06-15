"""Writer for the optional Part 3 scheduling-settings file (SCRUM-165).

Produces a file consumable by ``SchedulingSettingsFileReader``. The output
format is line-oriented UTF-8 text, with one line per threshold constraint
(in the enum's declared order) followed by one ranking line per active
priority entry. Comments are added for human readability.

This writer is the inverse of the reader: round-tripping ``parse`` and
``write`` over the same bundle is expected to produce an equivalent bundle.
"""
from __future__ import annotations

from pathlib import Path

from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintType,
)
from ranking_settings import RankingSettings


_HEADER = (
    "# Schedulix scheduling-settings file (Part 3).\n"
    "# Lines starting with '#' and blank lines are ignored.\n"
)


class SchedulingSettingsFileWriter:
    """Serialise scheduling settings to the shared file format."""

    def write(
        self,
        constraint_settings: SchedulingConstraintSettings,
        ranking_settings: RankingSettings,
        path: str | Path,
    ) -> Path:
        """
        Write ``constraint_settings`` and ``ranking_settings`` to ``path``.

        The parent directory is created if it does not exist. The returned
        ``Path`` is the resolved location of the file just written.
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(
            self.format(constraint_settings, ranking_settings),
            encoding="utf-8",
        )

        return output_path

    def format(
        self,
        constraint_settings: SchedulingConstraintSettings,
        ranking_settings: RankingSettings,
    ) -> str:
        """Return the textual representation without touching the filesystem."""
        lines: list[str] = [_HEADER, "# Threshold constraints (Section 2).\n"]

        # Iterate over the enum so the output keeps a stable, declared order
        # regardless of insertion order in the constraints dict.
        for constraint_type in ThresholdConstraintType:
            setting = constraint_settings.constraints.get(constraint_type)
            if setting is None:
                # Treat a missing entry as disabled with k = 0, matching
                # SchedulingConstraintSettings.default_configuration().
                enabled_token = "off"
                k_value = 0
            else:
                enabled_token = "on" if setting.enabled else "off"
                k_value = setting.k

            lines.append(
                f"{constraint_type.value} = {enabled_token}, {k_value}\n"
            )

        lines.append("\n# Ranking criteria (Section 3), in priority order.\n")

        if not ranking_settings.priority_list:
            lines.append("# (none — generation order is preserved)\n")
        else:
            for preference in ranking_settings.priority_list:
                direction_token = "desc" if preference.descending else "asc"
                lines.append(
                    f"ranking: {preference.criterion.value} : "
                    f"{direction_token}\n"
                )

        return "".join(lines)
