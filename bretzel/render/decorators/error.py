"""``@error_page(status_code)`` — register a custom HTTP error page.

The decorated function is run through the standard render pipeline
when the matching status code is raised. It accepts the same
shape-of-output kwargs as ``@page`` (``layout``, ``title``,
``description``, ``shell``) so a 404 can sit under the app shell with
zero extra plumbing.

"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bretzel.render.decorators.page import PageMeta


@dataclass(frozen=True, slots=True)
class ErrorMeta:
    status_code: int


def error_page(
    status_code: int,
    *,
    layout: Callable[..., Any] | None = None,
    title: str | None = None,
    description: str | None = None,
    shell: Callable[..., Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a function as the custom page for an HTTP status code.

    Free decorator — imported from ``bretzel``, needs no app instance.
    It only MARKS the function (``_bz_error_page`` + ``_bz_page``) ; the
    app picks it up at :meth:`Bretzel.include` time. Usage ::

        from bretzel import error_page

        @error_page(404, layout=app_layout, title="Not found")
        def not_found():
            ui.heading("Page not found", level=1)

        @error_page(500)  # no layout — safer if the layout itself broke
        def server_error():
            ui.alert("Something went wrong", color="error")

    The function runs through the same pipeline as a regular page,
    so it has access to components, theme, runtime — every Bretzel
    affordance. For 500 specifically, leaving ``layout=None`` is the
    safe default : if the user-state that crashed also feeds the
    layout, rendering it again would re-raise inside the error page.

    Son nom suit ``@page`` et ``@layout`` : les trois décorateurs déclarent
    un rendu qui répond à une requête.
    """
    if not isinstance(status_code, int) or not 100 <= status_code <= 599:
        raise ValueError(
            f"@error_page expects an HTTP status integer in [100, 599], "
            f"got {status_code!r}."
        )

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn._bz_error_page = ErrorMeta(status_code=status_code)  # type: ignore[attr-defined]
        # Stamp a PageMeta too so ``render_page`` walks the layout
        # chain / shell / title machinery without any special-case.
        # ``path=""`` + ``methods=("GET",)`` are inert : error pages
        # are exception-driven, never registered on a route.
        fn._bz_page = PageMeta(  # type: ignore[attr-defined]
            path="",
            layout=layout,
            title=title,
            description=description,
            shell=shell,
            methods=("GET",),
            signature=inspect.signature(fn),
        )
        return fn

    return decorator
