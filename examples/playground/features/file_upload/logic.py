"""``FileUpload`` server-side handlers."""

from __future__ import annotations

import functools

from examples.playground.features.file_upload.state import (
    FileUploadPlayground,
)


def server_changed(state: FileUploadPlayground) -> None:
    # Typed param: the dispatcher hydrates the changed control into state.
    pass


def log(name: str) -> None:
    state = FileUploadPlayground()
    state.log = (state.log + [name])[-12:]


def clear_log() -> None:
    state = FileUploadPlayground()
    state.log = []


log_change = functools.partial(log, "change")
log_upload_start = functools.partial(log, "upload_start")
log_upload_complete = functools.partial(log, "upload_complete")
log_upload_error = functools.partial(log, "upload_error")
log_focus = functools.partial(log, "focus")
log_blur = functools.partial(log, "blur")
