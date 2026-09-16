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
    """Mark a function as the custom page for an HTTP status code."""
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
