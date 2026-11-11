"""Combobox playground — the server handlers the cards wire."""

from examples.playground.features.combobox.state import (
    ComboboxEvents,
    ComboboxPlayground,
)

# ── Handlers ──────────────────────────────────────────────────────────


def log(name: str) -> None:
    state = ComboboxEvents()
    state.log = [*state.log, name]


def log_change(value: str = "") -> None: log(f"change(value={value!r})")
def log_focus()  -> None: log("focus")
def log_blur()   -> None: log("blur")
def log_search(query: str = "") -> None:
    if query:
        log(f"search(query={query!r})")


def log_close() -> None: log("close")


def clear_log() -> None:
    ComboboxEvents().log = []


def server_changed(state: ComboboxPlayground) -> None:
    # Typed param → the dispatcher hydrates the changed
    # control's value into ``state`` (coerced + persisted).
    pass
