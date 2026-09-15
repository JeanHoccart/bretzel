"""``@layout`` — mark a function as a layout that wraps pages.

A layout is a function that emits the framing UI of the app (navbar,
sidebar, footer) and calls ``ui.outlet()`` exactly once to mark where
the page content goes. Layouts can nest via the ``parent=`` keyword.

"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, overload


@dataclass(frozen=True, slots=True)
class LayoutMeta:
    """Captured at decoration time."""

    name: str
    parent: Callable[..., Any] | None


def _decorate(
    fn: Callable[..., Any],
    parent: Callable[..., Any] | None,
) -> Callable[..., Any]:
    fn._bz_layout = LayoutMeta(  # type: ignore[attr-defined]
        name=fn.__name__,
        parent=parent,
    )
    return fn


@overload
def layout(fn: Callable[..., Any]) -> Callable[..., Any]: ...
@overload
def layout(
    *, parent: Callable[..., Any] | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]: ...


def layout(
    fn: Callable[..., Any] | None = None,
    *,
    parent: Callable[..., Any] | None = None,
) -> Any:
    """Mark a function as a layout. Free decorator — needs no app.

    A layout needs no registration : pages reference it directly via
    ``PageMeta.layout`` and the pipeline walks the ``parent=`` chain
    through ``_bz_layout``. The decorator only stamps the mark. Two
    call shapes :

    Bare form ::

        from bretzel import layout

        @layout
        def app_layout():
            ui.navbar()
            ui.outlet()

    Parameterised form ::

        @layout(parent=app_layout)
        def admin_layout():
            with ui.flex():
                ui.sidebar()
                ui.outlet()
    """
    if fn is not None and callable(fn) and parent is None:
        return _decorate(fn, None)

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        return _decorate(fn, parent)

    return decorator
