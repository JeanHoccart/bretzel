"""The ``Sidebar`` bench's handlers — they MUTATE, the panels re-render.

Every ``log_*`` pushes a line into ``SidebarEvents``, whose dependency
the events panel declares: the re-render is the base layer's, not an
explicit call.
"""

from examples.playground.features.sidebar.state import (
    SidebarEvents,
    SidebarPlayground,
)


def log(name: str) -> None:
    state = SidebarEvents()
    state.log = [*state.log, name]


def log_home() -> None:
    log("click(item='Home')")


def log_issues() -> None:
    log("click(item='Issues')")


def log_settings() -> None:
    log("click(item='Settings')")


def log_logout() -> None:
    log("click(footer_item='Log out')")


def clear_log() -> None:
    SidebarEvents().log = []


def server_changed(state: SidebarPlayground) -> None:
    # A typed param → the dispatcher hydrates the changed control's
    # value into ``state`` (coerced + persisted). The panel declares
    # ``deps=[SidebarPlayground]``, it re-renders on its own.
    pass


def parse_extra_attrs(blob: str) -> dict:
    result: dict = {}
    for raw in blob.splitlines():
        line = raw.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result
