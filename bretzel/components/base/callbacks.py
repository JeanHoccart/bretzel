"""``render=`` escape hatches: what a callback builds, it must return.

The rest of the API teaches "a component attaches itself to the current
parent"; a ``render=`` callback runs outside any parent, so a component
it builds and does not RETURN is dropped — an empty cell, silently.
``Component.__init__`` notes each component built outside a ``with``
while a callback runs; a callback that built some and returned ``None``
is refused.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from bretzel.components.base.attrs import ComponentUsageError

#: The components a ``render=`` callback builds outside any ``with`` —
#: collected by :func:`call_render`, ``None`` outside one.
_BUILT_IN_CALLBACK: ContextVar[list[str] | None] = ContextVar("bz_built_in_callback", default=None)


def call_render(callback: Callable[..., Any], *args: Any) -> Any:
    """Call a ``render=`` escape hatch, and refuse one that built
    components and returned none of them. A callback that builds nothing
    and returns ``None`` stays an empty cell, on purpose."""
    built: list[str] = []
    token = _BUILT_IN_CALLBACK.set(built)
    try:
        rendered = callback(*args)
    finally:
        _BUILT_IN_CALLBACK.reset(token)
    if rendered is None and built:
        name = getattr(callback, "__qualname__", repr(callback))
        raise ComponentUsageError(
            f"The render callback {name} built {', '.join(dict.fromkeys(built))} "
            f"and returned None: a callback runs outside any parent, so what it "
            f"does not return is not shown. Return the component — "
            f"`return ui.badge(…)` — or build several inside "
            f"`with ui.hstack() as cell:` and `return cell`."
        )
    return rendered
