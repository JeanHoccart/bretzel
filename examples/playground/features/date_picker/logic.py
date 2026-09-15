"""``DatePicker`` server-side handlers (mutate state).

Panels re-render automatically : the ``@refreshable(deps=[...])`` zones
in ``ui.py`` observe ``DatePickerPlayground`` and re-render whenever a
handler mutates it — no imperative refresh needed.
"""

from __future__ import annotations

import functools

from examples.playground.features.date_picker.state import (
    DatePickerPlayground,
)


def server_changed(state: DatePickerPlayground) -> None:
    """Typed param - the dispatcher hydrates the changed control's value
    into ``state`` (coerced + persisted). No ``**kwargs`` / ``setattr``."""


def log(name: str) -> None:
    """Append ``name`` to the event log (keep last 12)."""
    state = DatePickerPlayground()
    state.log = (state.log + [name])[-12:]


def clear_log() -> None:
    state = DatePickerPlayground()
    state.log = []


# Pre-curried event loggers — addressed by ``module::qualname`` for
# the handler registry (so they survive across refreshes / pickle).
log_change = functools.partial(log, "change")
log_focus = functools.partial(log, "focus")
log_blur = functools.partial(log, "blur")
