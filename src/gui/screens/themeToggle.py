"""Small helpers for the shared light and dark mode button."""
from __future__ import annotations

from typing import Callable, Protocol, TypeAlias


ThemeToggleCallback: TypeAlias = Callable[[], object]
ThemeButtonText: TypeAlias = Callable[[], str] | str | None

THEME_BUTTON_WIDTH = 124
MOON_DARK_MODE_TEXT = "\u263e"
SUN_LIGHT_MODE_TEXT = "\u2600"


class ConfigurableWidget(Protocol):
    """Widget shape used by customTkinter buttons and the test fakes."""

    def configure(self, **kwargs) -> None:
        """Update widget options."""


def current_theme_button_text(text_source: ThemeButtonText) -> str:
    """Return the text shown on the theme button."""
    if callable(text_source):
        return text_source()

    if text_source:
        return str(text_source)

    return MOON_DARK_MODE_TEXT


def theme_button_text_for_mode(theme_mode: str) -> str:
    """Return the next theme action with a small icon."""
    if theme_mode == "Dark":
        return SUN_LIGHT_MODE_TEXT
    return MOON_DARK_MODE_TEXT


def handle_theme_toggle(
    on_theme_toggle: ThemeToggleCallback | None,
    button: ConfigurableWidget | None,
    text_source: ThemeButtonText,
) -> None:
    """Toggle the app theme and refresh the button text."""
    if on_theme_toggle is None:
        return

    on_theme_toggle()

    if button is not None:
        button.configure(text=current_theme_button_text(text_source))
