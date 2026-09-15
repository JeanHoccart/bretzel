"""Server-side handlers — mutate state and refresh the relevant panel.

Every handler is a **module-level callable** so Bretzel can address it
via ``module::qualname`` ; the framework rejects lambdas / closures
upstream. The shared ``log`` helper re-assigns the list (instead of
in-place ``append``) so the Field descriptor sees the write and marks
the state dirty.

Imports of the refreshable panels are **deferred** to inside the
handler bodies — ``ui.py`` imports handlers from this module at
import time, so importing the panels here at module-level would cycle.
The deferred form is a clean Python idiom for this case.
"""

from examples.playground.features.button.state import (
    ButtonEvents,
    ButtonPlayground,
)


def log(name: str) -> None:
    state = ButtonEvents()
    state.log = [*state.log, name]


def log_click()      -> None: log("click")
def log_focus()      -> None: log("focus")
def log_blur()       -> None: log("blur")
def log_mouseenter() -> None: log("mouseenter")
def log_mouseleave() -> None: log("mouseleave")


def clear_log() -> None:
    state = ButtonEvents()
    state.log = []


def server_changed(state: ButtonPlayground) -> None:
    """Typed param - the dispatcher hydrates the changed control's value
    into ``state`` (coerced + persisted). No ``**kwargs`` / ``setattr``."""


def playground_click_handler() -> None:
    """Server callable wired to the preview button when
    ``on_click_mode`` is ``server`` or ``both``. Appends an entry to
    the same events log the Server events card renders, so the round-
    trip is visible end-to-end."""
    log("playground-server-click")
