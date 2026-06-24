"""Scheduling settings screen for Part 3 threshold constraints."""
from __future__ import annotations

from typing import Callable

try:
    import customtkinter as ctk
except ModuleNotFoundError as error:
    raise ModuleNotFoundError(
        "customtkinter is required for the Version 2.0 GUI. "
        "Install it with: .venv\\Scripts\\python.exe -m pip install -r requirements.txt"
    ) from error

from application.settings_validator import SchedulingSettingsValidator
from constraint_settings import (
    SchedulingConstraintSettings,
    ThresholdConstraintSetting,
    ThresholdConstraintType,
)
from gui.screens.themeToggle import (
    THEME_BUTTON_WIDTH,
    ThemeButtonText,
    ThemeToggleCallback,
    current_theme_button_text,
    handle_theme_toggle,
)


_PAGE_BG = ("#F3F6FB", "#0B1220")
_SURFACE = ("#FFFFFF", "#151B26")
_SUBTLE_SURFACE = ("#F8FAFC", "#101826")
_BORDER = ("#D8E2F0", "#2D3748")
_TEXT = ("#111827", "#F8FAFC")
_MUTED = ("#5F6368", "#A8A8A8")
_PRIMARY = "#2563EB"
_PRIMARY_HOVER = "#1D4ED8"
_ERROR = "#B00020"
_SUCCESS = "#2E7D32"

_REQUIREMENT_COPY: dict[ThresholdConstraintType, tuple[str, str]] = {
    ThresholdConstraintType.mandatory_gap_days: (
        "Minimum days between mandatory exams",
        "Minimum days between mandatory exams that share a program and year.",
    ),
    ThresholdConstraintType.any_course_gap_days: (
        "Minimum days between any exams",
        "Minimum days between any exams that share a program and year.",
    ),
    ThresholdConstraintType.elective_conflicts_per_program: (
        "Maximum elective course conflicts",
        "Maximum same-date elective exam conflicts allowed inside one program.",
    ),
    ThresholdConstraintType.mandatory_span_days: (
        "Minimum spread between first and last mandatory exam",
        "Minimum number of days covered by mandatory exams in each exam period.",
    ),
    ThresholdConstraintType.max_exams_per_day: (
        "Maximum exams on the same day",
        "Maximum total exams that may be placed on a single calendar day.",
    ),
}

_VALUE_LABELS: dict[ThresholdConstraintType, str] = {
    ThresholdConstraintType.mandatory_gap_days: "Days",
    ThresholdConstraintType.any_course_gap_days: "Days",
    ThresholdConstraintType.elective_conflicts_per_program: "Max Conflicts",
    ThresholdConstraintType.mandatory_span_days: "Days",
    ThresholdConstraintType.max_exams_per_day: "Max Exams",
}

_VALUE_ERROR_COPY: dict[ThresholdConstraintType, tuple[str, str]] = {
    ThresholdConstraintType.mandatory_gap_days: (
        "Enter a whole number of days.",
        "Enter at least 1 day.",
    ),
    ThresholdConstraintType.any_course_gap_days: (
        "Enter a whole number of days.",
        "Enter at least 1 day.",
    ),
    ThresholdConstraintType.elective_conflicts_per_program: (
        "Enter a whole number of conflicts.",
        "Enter 0 or more conflicts.",
    ),
    ThresholdConstraintType.mandatory_span_days: (
        "Enter a whole number of days.",
        "Enter at least 1 day.",
    ),
    ThresholdConstraintType.max_exams_per_day: (
        "Enter a whole number of exams.",
        "Enter at least 1 exam.",
    ),
}


class SchedulingSettingsScreen(ctk.CTkFrame):
    """Passive view for configuring threshold requirements 2.1-2.5."""

    def __init__(
        self,
        master,
        initial_settings: SchedulingConstraintSettings | None = None,
        validator: SchedulingSettingsValidator | None = None,
        on_next: Callable[[SchedulingConstraintSettings], None] | None = None,
        on_back: Callable[[], None] | None = None,
        on_theme_toggle: ThemeToggleCallback | None = None,
        theme_button_text: ThemeButtonText = None,
    ) -> None:
        super().__init__(master, corner_radius=0, fg_color=_PAGE_BG)
        self._initial_settings = (
            initial_settings
            or SchedulingConstraintSettings.default_configuration()
        )
        self._validator = validator or SchedulingSettingsValidator()
        self._on_next = on_next
        self._on_back = on_back
        self._on_theme_toggle = on_theme_toggle
        self._theme_button_text = theme_button_text

        self._enabled_vars: dict[ThresholdConstraintType, ctk.BooleanVar] = {}
        self._k_entries: dict[ThresholdConstraintType, ctk.CTkEntry] = {}
        self._error_labels: dict[ThresholdConstraintType, ctk.CTkLabel] = {}
        self._continue_button: ctk.CTkButton | None = None
        self._status_label: ctk.CTkLabel | None = None
        self._theme_button: ctk.CTkButton | None = None

        self._build()

    def _build(self) -> None:
        """Build the settings workspace."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_requirements()
        self._build_footer()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 12))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Scheduling Settings",
            font=("Segoe UI", 24, "bold"),
            text_color=_TEXT,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            header,
            text="Choose optional scheduling rules to shape the generated schedules.",
            font=("Segoe UI", 13),
            text_color=_MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        if self._on_theme_toggle is not None:
            # Button text tells the user which mode the click will open.
            self._theme_button = ctk.CTkButton(
                header,
                text=current_theme_button_text(self._theme_button_text),
                width=THEME_BUTTON_WIDTH,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=(_PRIMARY, "#93C5FD"),
                hover_color=("#DCE8FF", "#1E293B"),
                command=self._handle_theme_toggle,
            )
            self._theme_button.grid(row=0, column=1, sticky="ne", rowspan=2)

    def _build_requirements(self) -> None:
        body = ctk.CTkScrollableFrame(
            self,
            fg_color=_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 12))
        body.grid_columnconfigure(0, weight=1)

        for row_index, constraint_type in enumerate(ThresholdConstraintType):
            self._build_requirement_row(
                body,
                row_index,
                constraint_type,
            )

    def _build_requirement_row(
        self,
        master: ctk.CTkFrame,
        row_index: int,
        constraint_type: ThresholdConstraintType,
    ) -> None:
        title, description = _REQUIREMENT_COPY[constraint_type]
        saved_setting = self._saved_setting_for(constraint_type)

        row = ctk.CTkFrame(
            master,
            fg_color=_SUBTLE_SURFACE,
            border_width=1,
            border_color=_BORDER,
            corner_radius=8,
        )
        row.grid(
            row=row_index,
            column=0,
            sticky="ew",
            padx=10,
            pady=(10, 0),
        )
        row.grid_columnconfigure(1, weight=1)

        enabled_var = ctk.BooleanVar(value=saved_setting.enabled)
        self._enabled_vars[constraint_type] = enabled_var

        checkbox = ctk.CTkCheckBox(
            row,
            text="",
            variable=enabled_var,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            width=24,
            command=lambda current=constraint_type: self._handle_enabled_toggle(current),
        )
        checkbox.grid(row=0, column=0, rowspan=3, sticky="n", padx=(14, 10), pady=16)

        ctk.CTkLabel(
            row,
            text=title,
            font=("Segoe UI", 14, "bold"),
            text_color=_TEXT,
            anchor="w",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 0))

        ctk.CTkLabel(
            row,
            text=description,
            font=("Segoe UI", 11),
            text_color=_MUTED,
            anchor="w",
            wraplength=560,
            justify="left",
        ).grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=(2, 10))

        k_area = ctk.CTkFrame(row, fg_color="transparent")
        k_area.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(8, 14), pady=(12, 8))

        ctk.CTkLabel(
            k_area,
            text=_VALUE_LABELS[constraint_type],
            font=("Segoe UI", 11, "bold"),
            text_color=_MUTED,
        ).grid(row=0, column=0, sticky="w")

        k_entry = ctk.CTkEntry(
            k_area,
            width=92,
            placeholder_text="1",
            justify="center",
        )
        k_entry.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        saved_text = self._saved_k_text(saved_setting)
        if saved_text:
            k_entry.insert(0, saved_text)
        self._k_entries[constraint_type] = k_entry

        error_label = ctk.CTkLabel(
            row,
            text="",
            font=("Segoe UI", 12),
            text_color=_ERROR,
            anchor="w",
            wraplength=720,
            justify="left",
        )
        error_label.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=(0, 12))
        self._error_labels[constraint_type] = error_label

        self._sync_row_state(constraint_type)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(
            footer,
            text="Disabled rules are ignored and do not need a value.",
            text_color=_MUTED,
            anchor="w",
        )
        self._status_label.grid(row=0, column=0, sticky="w")

        if self._on_back is not None:
            ctk.CTkButton(
                footer,
                text="Back",
                width=90,
                fg_color="transparent",
                border_width=1,
                border_color=_BORDER,
                text_color=(_PRIMARY, "#93C5FD"),
                command=self._on_back,
            ).grid(row=0, column=1, padx=(8, 8))

        self._continue_button = ctk.CTkButton(
            footer,
            text="Continue",
            width=112,
            fg_color=_PRIMARY,
            hover_color=_PRIMARY_HOVER,
            command=self._handle_continue,
        )
        self._continue_button.grid(row=0, column=2)

    def _handle_enabled_toggle(
        self,
        constraint_type: ThresholdConstraintType,
    ) -> None:
        """Enable or disable the matching k field."""
        self._sync_row_state(constraint_type)
        self._clear_error(constraint_type)
        self._show_status(
            "Update the values for enabled rules before continuing.",
            ok=None,
        )

    def _handle_theme_toggle(self) -> None:
        """Switch between light and dark mode."""
        handle_theme_toggle(
            self._on_theme_toggle,
            self._theme_button,
            self._theme_button_text,
        )

    def _handle_continue(self) -> None:
        """Validate the edited settings and move forward when valid."""
        settings = self._settings_from_inputs()
        validation = self._validator.validate_constraint_settings(settings)
        self._clear_errors()

        if not validation.is_valid:
            affected_rules: list[ThresholdConstraintType] = []
            for error in validation.errors:
                constraint_type = self._constraint_from_field_path(
                    error.field_path
                )
                if constraint_type is not None:
                    affected_rules.append(constraint_type)
                    self._show_row_error(
                        constraint_type,
                        error.message,
                    )

            self._show_status(
                self._invalid_settings_message(affected_rules),
                ok=False,
            )
            return

        self._show_status("Settings saved.", ok=True)
        if self._on_next is not None:
            self._on_next(settings)

    def _settings_from_inputs(self) -> SchedulingConstraintSettings:
        constraints: dict[ThresholdConstraintType, ThresholdConstraintSetting] = {}

        for constraint_type in ThresholdConstraintType:
            enabled = bool(self._enabled_vars[constraint_type].get())
            raw_value = self._k_entries[constraint_type].get().strip()
            k_value = self._coerce_k_value(raw_value, enabled)

            constraints[constraint_type] = ThresholdConstraintSetting(
                enabled=enabled,
                k=k_value,
            )

        return SchedulingConstraintSettings(constraints=constraints)

    @staticmethod
    def _coerce_k_value(
        raw_value: str,
        enabled: bool,
    ) -> int | str:
        if not enabled and raw_value == "":
            return 0

        try:
            return int(raw_value)
        except ValueError:
            return raw_value

    def _sync_row_state(
        self,
        constraint_type: ThresholdConstraintType,
    ) -> None:
        enabled = bool(self._enabled_vars[constraint_type].get())
        state = "normal" if enabled else "disabled"
        self._k_entries[constraint_type].configure(state=state)

    def _clear_errors(self) -> None:
        for constraint_type in ThresholdConstraintType:
            self._clear_error(constraint_type)

    def _clear_error(
        self,
        constraint_type: ThresholdConstraintType,
    ) -> None:
        self._error_labels[constraint_type].configure(text="")

    def _show_row_error(
        self,
        constraint_type: ThresholdConstraintType,
        message: str,
    ) -> None:
        self._error_labels[constraint_type].configure(
            text=self._friendly_validation_message(constraint_type, message)
        )

    def _show_status(
        self,
        message: str,
        ok: bool | None,
    ) -> None:
        if self._status_label is None:
            return

        if ok is True:
            color = _SUCCESS
        elif ok is False:
            color = _ERROR
        else:
            color = _MUTED

        self._status_label.configure(
            text=message,
            text_color=color,
        )

    def _saved_setting_for(
        self,
        constraint_type: ThresholdConstraintType,
    ) -> ThresholdConstraintSetting:
        return self._initial_settings.constraints.get(
            constraint_type,
            ThresholdConstraintSetting(enabled=False, k=0),
        )

    @staticmethod
    def _saved_k_text(setting: ThresholdConstraintSetting) -> str:
        if setting.enabled or setting.k not in (0, None):
            return str(setting.k)
        return ""

    @staticmethod
    def _friendly_validation_message(
        constraint_type: ThresholdConstraintType,
        raw_message: str,
    ) -> str:
        integer_message, range_message = _VALUE_ERROR_COPY[constraint_type]
        if "must be an integer" in raw_message:
            return integer_message
        if "must be >=" in raw_message:
            return range_message
        return "Enter a valid value for this rule."

    @staticmethod
    def _invalid_settings_message(
        affected_rules: list[ThresholdConstraintType],
    ) -> str:
        if not affected_rules:
            return "Fix the highlighted rules before continuing."

        seen: set[ThresholdConstraintType] = set()
        titles: list[str] = []
        for constraint_type in affected_rules:
            if constraint_type in seen:
                continue
            seen.add(constraint_type)
            titles.append(_REQUIREMENT_COPY[constraint_type][0])

        if len(titles) == 1:
            return f"Fix this rule before continuing: {titles[0]}."

        shown = "; ".join(titles[:2])
        if len(titles) > 2:
            shown += f"; and {len(titles) - 2} more"
        return f"Fix the highlighted rules before continuing: {shown}."

    @staticmethod
    def _constraint_from_field_path(
        field_path: str,
    ) -> ThresholdConstraintType | None:
        for constraint_type in ThresholdConstraintType:
            if constraint_type.value in field_path:
                return constraint_type
        return None
