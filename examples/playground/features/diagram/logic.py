"""The Diagram playground's server handlers.

Every handler is a MODULE-LEVEL callable: Bretzel addresses it by
``module::qualname`` and refuses a lambda or a closure.

No ``ui`` import: the panels declare ``deps=[…]``, so mutating the state
is enough to re-render them. It is what avoids the handler ↔ panel cycle.
"""

from examples.playground.features.diagram.state import (
    DiagramPlayground,
    DiagramServerEvents,
    Picked,
)


def pick(key: str) -> None:
    """``on_item_click`` receives the node's KEY, nothing else.

    Clicking the centred node again returns the overview: without that
    one gets locked into a neighbourhood with no way out.
    """
    state = Picked()
    state.key = "" if state.key == key else key


def playground_click_handler(key: str) -> None:
    """The Server playground's handler — module-level, hence
    addressable."""


def server_changed(state: DiagramPlayground) -> None:
    """The dispatcher hydrates the changed control into ``state``."""




def log_item_click(key: str) -> None:
    """Log a server click.

    RE-ASSIGNS the list rather than an in-place ``append``: the field
    descriptor does not see an internal mutation, so the state would not
    be marked dirty and the panel would not re-render.
    """
    state = DiagramServerEvents()
    state.log = [*state.log, f"item_click(key={key!r})"]


def clear_log() -> None:
    DiagramServerEvents().log = []
