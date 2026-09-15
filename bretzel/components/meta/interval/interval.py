"""``Interval`` — recurring client timer that fires a server action.

``ui.interval(on_tick=advance, seconds=1, active=play.running)`` fires the
``on_tick`` action every ``seconds`` while ``active`` is truthy. ``active``
accepts a :class:`ClientBinding`, so flipping it — from the server (a
mutated ClientState syncs to the page) or the client — **stops the timer
instantly**. No held connection, no background loop, no orphan requests :
this is the controllable replacement for a server-driven polling loop.

The element renders hidden ; the runtime owns the ``setInterval`` via
``$bz._tick`` (``06_helpers.js``) and dispatches the ``tick`` event htmx
fires the action on. The ``on_tick`` action is signed + wired exactly
like any ``on_<event>`` callable — it just rides a ``tick`` trigger
instead of a DOM event.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from bretzel.components.base import Component
from bretzel.core.tree import Element
from bretzel.state.scopes.client import ClientBinding


class Interval(Component):
    """Hidden recurring timer. Pairs with a ``ClientBinding`` gate so the
    cadence is stoppable without any server-side task lifecycle."""
    IS_CONTAINER: ClassVar[bool] = False
    BINDABLE_PROPS: ClassVar[tuple[str, ...]] = ()
    EVENTS: ClassVar[tuple[str, ...]] = ("tick",)

    def __init__(
        self,
        *,
        on_tick: Callable[..., Any] | str | None = None,
        seconds: float = 1.0,
        active: ClientBinding | bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(on_tick=on_tick, **kwargs)
        self._seconds = seconds
        self._active = active

    def render(self) -> Element:
        attrs = self.emit_attrs()  # hx-post + hx-trigger="tick" + data-bz-sig
        ms = max(1, int(self._seconds * 1000))
        if isinstance(self._active, ClientBinding):
            active_js = self.path_of(self._active)
        else:
            active_js = "true" if self._active else "false"
        attrs["bz-effect"] = f"$bz._tick($el, ({active_js}), {ms})"
        attrs["hidden"] = True
        attrs["aria-hidden"] = "true"
        return Element(tag=self._tag, attrs=attrs, children=())


__all__ = ["Interval"]
