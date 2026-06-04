"""
view_factory.py
~~~~~~~~~~~~~~~
Centralises the creation of all customTkinter Views (screens) in the
Schedulix GUI layer.

Design mirrors the existing ``FileReaderFactory`` and the new
``PresenterFactory``:

* A ``ViewType`` enum acts as the public key so callers never import concrete
  view classes directly.
* ``ViewFactory.create`` dispatches through an internal registry dict and
  forwards ``master`` plus all keyword arguments (presenter instances,
  navigation callbacks, etc.) to the selected constructor.
* Both the concrete view classes **and** ``customtkinter`` are imported
  **inside** the method body.  This keeps the factory importable in headless
  test environments without triggering a display connection — the same
  technique used by ``FileReaderFactory`` to avoid circular imports.

No existing Version 1.0 files are modified by this module.
"""

import importlib
from enum import Enum, auto


class ViewType(Enum):
    """
    Identifies each View (screen) that the factory can build.

    Add a new member here whenever a new screen class is created.
    """

    # First wizard step: browse and validate the three required input files.
    FILE_UPLOAD = auto()

    # Second wizard step: select study programs and inspect their course lists.
    PROGRAM_CONFIG = auto()

    # Third wizard step: manage exam dates (exclude/activate days, edit window).
    DATE_MANAGEMENT = auto()


class ViewFactory:
    """
    Creates customTkinter screen instances by type, injecting dependencies.

    Usage
    -----
    Call ``create`` at the wizard/navigation layer to build a screen without
    coupling that layer to a specific screen class::

        screen = ViewFactory.create(
            ViewType.FILE_UPLOAD,
            master=root,
        )

        screen = ViewFactory.create(
            ViewType.PROGRAM_CONFIG,
            master=root,
            selection_presenter=sel_presenter,
            details_presenter=det_presenter,
            on_next=lambda: navigate_to_next(),
            on_back=lambda: navigate_to_prev(),
        )

    Dependency Injection
    --------------------
    Presenter instances, navigation callbacks, and any other runtime objects
    travel as keyword arguments.  The factory forwards them verbatim to the
    screen constructor, so adding a new constructor parameter to a screen
    requires no change here.

    Headless safety
    ---------------
    ``customtkinter`` and all concrete screen classes are imported *inside*
    ``create``, so importing this module in a test suite that runs without a
    display does **not** crash.  Tests stub the inner imports via
    ``unittest.mock.patch``.

    Design constraints
    ------------------
    * Static method only — no factory instance required.
    * Mirrors ``FileReaderFactory``: enum key, registry dict, lazy imports,
      ``ValueError`` on unknown key.
    """

    @staticmethod
    def create(view_type: ViewType, master, **kwargs):
        """
        Build and return the View (screen) matching ``view_type``.

        Parameters
        ----------
        view_type:
            Which screen to build.
        master:
            The parent customTkinter container passed as the first positional
            argument to every ``ctk.CTkFrame`` subclass.
        **kwargs:
            Additional arguments forwarded verbatim to the screen constructor.
            Typical kwargs: ``upload_service``, ``selection_presenter``,
            ``details_presenter``, ``on_next``, ``on_back``.

        Returns
        -------
        ctk.CTkFrame
            The fully constructed, ready-to-pack screen instance.

        Raises
        ------
        ValueError
            If ``view_type`` is not registered in the factory.
        """
        # Registry maps each ViewType to the dotted module+class path of the
        # concrete screen.  Using string identifiers here means the registry
        # can be checked (and a ValueError raised) BEFORE importing customtkinter
        # or any concrete screen — keeping headless tests safe.
        _registry: dict[ViewType, tuple[str, str]] = {
            ViewType.FILE_UPLOAD:    ("gui.fileUploadScreen",   "FileUploadScreen"),
            ViewType.PROGRAM_CONFIG: ("gui.programConfigScreen", "ProgramConfigScreen"),
            ViewType.DATE_MANAGEMENT: ("gui.dateManagementScreen", "DateManagementScreen"),
        }

        entry = _registry.get(view_type)

        if entry is None:
            raise ValueError(
                f"No view registered for type: {view_type!r}"
            )

        # Only import the concrete screen (and therefore customtkinter) after
        # confirming the key is valid.  This import is the one tests patch.
        module_path, class_name = entry
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        return cls(master, **kwargs)
