"""
presenter_factory.py
~~~~~~~~~~~~~~~~~~~~
Centralises the creation of all MVP Presenters in the Schedulix GUI layer.

Design mirrors the existing ``FileReaderFactory`` in
``fileReader/baseFileReader.py``:

* A ``PresenterType`` enum acts as the public key so callers never import
  concrete presenter classes directly.
* ``PresenterFactory.create`` dispatches through an internal registry dict and
  forwards all keyword arguments to the selected constructor, cleanly
  supporting Dependency Injection (CacheManager, course lists, etc.).
* Concrete presenter classes are imported **inside** the method body to avoid
  circular imports and to keep the factory importable in headless test
  environments without triggering any GUI code.

No existing Version 1.0 files are modified by this module.
"""

from enum import Enum, auto


class PresenterType(Enum):
    """
    Identifies each Presenter that the factory can build.

    Add a new member here whenever a new Presenter class is created.
    """

    # Drives the study-program selection checkboxes (five-program limit).
    PROGRAM_SELECTION = auto()

    # Supplies grouped course details for one selected study program.
    PROGRAM_DETAILS = auto()


class PresenterFactory:
    """
    Creates Presenter objects by type, forwarding dependencies as kwargs.

    Usage
    -----
    Instantiate once at the application root and call ``create`` for every
    presenter the current screen needs::

        selection_presenter = PresenterFactory.create(
            PresenterType.PROGRAM_SELECTION,
            courses=cache.get_courses(),
        )

        details_presenter = PresenterFactory.create(
            PresenterType.PROGRAM_DETAILS,
            courses=cache.get_courses(),
        )

    Dependency Injection
    --------------------
    Any runtime object (``CacheManager``, course lists, configuration values)
    can be passed as a keyword argument.  The factory does not inspect the
    kwargs — it forwards them verbatim to the constructor, so adding a new
    parameter to a presenter requires no change here.

    Design constraints
    ------------------
    * Static method only — no factory instance required.
    * Mirrors ``FileReaderFactory``: enum key, registry dict, lazy imports,
      ``ValueError`` on unknown key.
    """

    @staticmethod
    def create(presenter_type: PresenterType, **kwargs) -> object:
        """
        Build and return the Presenter matching ``presenter_type``.

        Parameters
        ----------
        presenter_type:
            Which presenter to build.
        **kwargs:
            Arguments forwarded verbatim to the presenter constructor.
            For example, ``courses=cache.get_courses()`` or
            ``max_programs=3``.

        Returns
        -------
        object
            The fully constructed presenter instance.

        Raises
        ------
        ValueError
            If ``presenter_type`` is not registered in the factory.
        """
        # Imports are placed here — not at module level — to avoid circular
        # imports between gui modules and to keep this file importable in
        # headless test environments.
        from gui.programSelectionPresenter import ProgramSelectionPresenter
        from gui.programDetailsPresenter import ProgramDetailsPresenter

        # Maps each PresenterType to its concrete implementation class.
        # Extend this dict whenever a new presenter is added.
        registry: dict[PresenterType, type] = {
            PresenterType.PROGRAM_SELECTION: ProgramSelectionPresenter,
            PresenterType.PROGRAM_DETAILS:   ProgramDetailsPresenter,
        }

        cls = registry.get(presenter_type)

        if cls is None:
            raise ValueError(
                f"No presenter registered for type: {presenter_type!r}"
            )

        return cls(**kwargs)
