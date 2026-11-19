"""Exception handlers — turn raised errors into Bretzel-rendered pages.

Four handlers wired at startup, one per concrete exception class :

- :class:`StarletteHTTPException` — covers ``abort(code)``, FastAPI's own
  404 routing fallback, and anything else handlers raise as
  ``HTTPException``.
- :class:`AuthRequiredError` — an anonymous visitor resolving a
  ``UserState``. Raised by ``state/registry.py``, which may not import
  Starlette, so the mapping to 401 belongs here.
- :class:`BretzelError` — framework internals signalling a bug ;
  always renders the 500 page (message kept in debug, stripped in
  prod).
- :class:`Exception` (catch-all) — wired **only** when
  ``config.expose_errors`` is False. In dev we let FastAPI surface its
  interactive traceback ; in prod we never leak a stack trace to
  the client.

Each handler looks up an optional user-registered
``@error_page(code)`` function in ``app._error_handlers`` and runs it
through the standard :func:`render_page` pipeline. If lookup fails
— or the user page itself raises during render — we fall back to
the self-contained :func:`default_error_page` HTML (no Tailwind /
runtime dependencies, works even if the theme is broken).

A page is for the browser. A caller that asks for no HTML — a program
reading the app's JSON API, ``curl`` — gets FastAPI's own answer,
``{"detail": …}`` in JSON, the shape an existing FastAPI app already
promised its clients. The browser and the runtime's own requests ask
for HTML (``Accept: text/html``, ``HX-Request``).
"""

from __future__ import annotations

import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from bretzel.render.context import maybe_current_context
from bretzel.render.pipeline import render_page
from bretzel.server.errors import (
    AuthRequiredError,
    BretzelError,
    default_error_page,
)
from bretzel.server.navigation import response_is_read_by_htmx

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp


_log = logging.getLogger("bretzel.server.errors")


def register_error_handlers(fastapi: FastAPI, bretzel_app: BretzelApp) -> None:
    """Wire the four exception handlers on the FastAPI app.

    Order of registration doesn't matter — Starlette dispatches by
    concrete exception type, picking the most specific subclass
    match. The catch-all is opt-out (only added when
    ``config.expose_errors`` is False) so dev keeps the FastAPI traceback
    page.
    """
    # Exposure, not verbosity: the detail of an exception that goes out
    # in the response is a security decision. ``expose_errors`` defaults
    # to the mode but can be set on its own (``mode="dev",
    # expose_errors=False`` to test the real error pages).
    expose = bool(getattr(bretzel_app.config, "expose_errors", False))

    async def on_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> Response:
        return await _render_error(
            bretzel_app,
            request,
            exc.status_code,
            detail=str(exc.detail) if exc.detail else "",
            raw=exc.detail,
            headers=getattr(exc, "headers", None),
        )

    async def on_auth_required(
        request: Request,
        exc: AuthRequiredError,
    ) -> Response:
        # No log : an anonymous visitor hitting a user-scoped page is a
        # normal outcome, not an incident. Detail stays out of the
        # response — "who is missing" is never the client's business.
        return await _render_error(bretzel_app, request, 401)

    async def on_bretzel_error(
        request: Request,
        exc: BretzelError,
    ) -> Response:
        _log.exception("BretzelError caught", exc_info=exc)
        # Surface the message in debug, strip in prod : keeps internal
        # invariants from leaking on a production page.
        detail = str(exc) if expose else ""
        return await _render_error(bretzel_app, request, 500, detail=detail)

    fastapi.add_exception_handler(StarletteHTTPException, on_http_exception)
    fastapi.add_exception_handler(AuthRequiredError, on_auth_required)
    fastapi.add_exception_handler(BretzelError, on_bretzel_error)

    if not expose:

        async def on_unhandled(
            request: Request,
            exc: Exception,
        ) -> Response:
            _log.exception("Unhandled exception", exc_info=exc)
            return await _render_error(bretzel_app, request, 500)

        fastapi.add_exception_handler(Exception, on_unhandled)


# ───────────────────────────────────────────────────────────────────────────
# Render path — user handler with fallback to the static HTML page
# ───────────────────────────────────────────────────────────────────────────


async def _render_error(
    app: BretzelApp,
    request: Request,
    status_code: int,
    *,
    detail: str = "",
    raw: object = None,
    headers: dict[str, str] | None = None,
) -> Response:
    """Render the user-registered ``@error_page(code)`` page, or fallback.

    A caller that asks for no HTML gets ``{"detail": …}`` instead (cf.
    the module docstring): ``raw`` when the exception carried one, as
    FastAPI answers it, else ``detail`` or the status's own phrase. The
    browser and the runtime ask for HTML (``Accept: text/html``,
    ``HX-Request``).

    Layered fallback :

    1. user handler exists + render succeeds → that HTML
    2. user handler exists but render raises → log + static fallback
    3. no user handler → static fallback
    """
    if not ("text/html" in request.headers.get("accept", "")
            or response_is_read_by_htmx(request)):
        body = raw if raw is not None else detail or HTTPStatus(status_code).phrase
        return JSONResponse({"detail": body}, status_code=status_code, headers=headers)
    page_fn = app._error_handlers.get(status_code)
    if page_fn is not None:
        ctx = maybe_current_context()
        if ctx is not None:
            if ctx.state_registry is not None:
                ctx.state_registry.discard()
            try:
                result = await render_page(app, page_fn, ctx=ctx)
                return HTMLResponse(
                    content=result.body,
                    status_code=status_code,
                    headers=_safe_headers(result.headers),
                )
            except Exception as exc:
                # A broken error page must NEVER take down the whole
                # response chain. Log, then degrade to the static HTML.
                _log.exception(
                    "Error page render failed (code=%s)",
                    status_code,
                    exc_info=exc,
                )

    body = default_error_page(status_code, message=detail or None)
    return HTMLResponse(content=body, status_code=status_code)


def _safe_headers(headers: dict[str, str]) -> dict[str, str]:
    """Drop entity headers Starlette manages from the render result.

    ``HTMLResponse`` computes ``Content-Length`` / ``Content-Type``
    from the body it receives ; copying those over from
    ``RenderResult.headers`` would double them.
    """
    return {
        k: v
        for k, v in headers.items()
        if k.lower() not in ("content-length", "content-type")
    }
