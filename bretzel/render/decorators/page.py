"""``@page`` — register a function as a routed page handler.

Decorators in Bretzel are intentionally pure markers. The decorated
function gets a ``_bz_page`` :class:`PageMeta` attached and is added
to the app's ``_pages`` list ; the routing layer (Layer 6) walks that
list at startup to register FastAPI routes.

"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bretzel.core.errors import BretzelError


class PageAlreadyMarkedError(BretzelError):
    """Two ``@page`` on the SAME function — the second would erase the first.

    Raised at DECORATION time, so at import: it never travels as far as
    the server layer, and the ``500`` mapping of its parent class does
    not apply. It carries its own name so a test can target it without
    catching every framework failure.
    """


@dataclass(frozen=True, slots=True)
class PageMeta:
    """Captured at decoration time, read by the route registrar."""

    path: str
    layout: Callable[..., Any] | None
    title: str | None
    description: str | None
    shell: Callable[..., Any] | None
    methods: tuple[str, ...]
    signature: inspect.Signature


def page(
    path: str,
    *,
    layout: Callable[..., Any] | None = None,
    title: str | None = None,
    description: str | None = None,
    shell: Callable[..., Any] | None = None,
    methods: tuple[str, ...] = ("GET",),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark ``fn`` as the handler for ``GET path`` (or other methods).

    Free decorator — imported from ``bretzel``, needs no app instance.
    It only MARKS the function (stamps ``_bz_page``) ; the app picks it
    up at :meth:`Bretzel.include` time and registers the FastAPI route.
    Import order has no effect (charter anti-rule #4). Usage ::

        from bretzel import page

        @page("/cart", layout=main_layout, title="Your Cart")
        def cart_page():
            ...

    Static title / description bake into the document head ; for
    dynamic meta drop ``ui.title(...)`` inside the page function.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        # Capture inspection now — at decoration time we still have
        # the user's original annotations / defaults intact.
        meta = PageMeta(
            path=path,
            layout=layout,
            title=title,
            description=description,
            shell=shell,
            methods=tuple(m.upper() for m in methods),
            signature=inspect.signature(fn),
        )
        # ⚠️ The mark lives ON THE FUNCTION OBJECT, so a second
        # decoration of the SAME function overwrites the first — and the
        # first route disappears, as a 404, in an app one is not even
        # reading.
        #
        # Measured on 2026-08-29: two benches in ``tests/probes/`` did
        # ``page("/")(sidebar_feat.page)`` on the function the playground
        # already mounted at ``/sidebar``. Importing either bench — which
        # any gate sweeping ``tests/probes`` does — was enough to make
        # ``/sidebar`` and ``/datatable_solo`` unreachable. That is the
        # cause of the two reds saying "the fast suite depends on ORDER":
        # under ``xdist``, the worker inheriting a bench loses both
        # pages; sequentially the order spared them.
        #
        # The refusal is explicit rather than silent, and it costs the
        # legitimate case nothing: mounting the same function twice is
        # written ``page("/b")(lambda: feat.page())`` — one function per
        # route, which the mark already assumes.
        seen = getattr(fn, "_bz_page", None)
        if seen is not None and seen != meta:
            raise PageAlreadyMarkedError(
                f"{getattr(fn, '__qualname__', fn)!r} is already marked for "
                f"{seen.path!r} and is being re-marked for {path!r}. The "
                f"mark lives on the function object: the second OVERWRITES "
                f"the first, so {seen.path!r} would become a 404 without a "
                f"word — including in another app in the same process. "
                f"To mount the same page in two places, give it two "
                f"functions: `page({path!r})(lambda: mod.page())`."
            )
        fn._bz_page = meta  # type: ignore[attr-defined]
        return fn

    return decorator
