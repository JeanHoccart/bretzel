"""``DateRangePicker`` server-side handlers."""

from __future__ import annotations

import functools

from examples.playground.features.date_range_picker.state import (
    DateRangePickerPlayground,
)


def server_changed(state: DateRangePickerPlayground) -> None:
    # Typed param: the dispatcher hydrates the changed control into state.
    pass


def log(name: str) -> None:
    state = DateRangePickerPlayground()
    state.log = (state.log + [name])[-12:]


def clear_log() -> None:
    state = DateRangePickerPlayground()
    state.log = []


log_change = functools.partial(log, "change")
log_focus = functools.partial(log, "focus")
log_blur = functools.partial(log, "blur")
