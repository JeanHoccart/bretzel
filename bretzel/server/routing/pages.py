"""Page routing — turn ``@page("/path")`` into FastAPI routes.

Walked once at startup. Each registered page becomes one (or several,
when ``methods=`` lists more than ``GET``) FastAPI route ; the route
handler delegates to :func:`bretzel.render.render_page` and wraps
the resulting :class:`RenderResult` in a Starlette :class:`HTMLResponse`.

Path-template parameters land on ``path_params`` ; the pipeline does
the lightweight signature inspection that injects them into the page
function's kwargs.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from bretzel.render.pipeline import _resolve_layout_chain, render_page
from bretzel.runtime.protocol import outlet_id_for

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp


def register_pages(fastapi: FastAPI, bretzel_app: BretzelApp) -> None:
    """Add every registered ``@page`` function to ``fastapi``.

    Called from :py:meth:`Bretzel._lifespan` once at startup. Pages
    appended after startup aren't picked up — that's intentional :
    routing tables changing under live traffic is a footgun we don't
    enable.
    """
    for fn in bretzel_app._pages:
        meta = getattr(fn, "_bz_page", None)
        if meta is None:
            continue
        _register_one(fastapi, bretzel_app, fn, meta)


def _register_one(
    fastapi: FastAPI,
    bretzel_app: BretzelApp,
    page_fn: Callable[..., Any],
    meta: Any,
) -> None:
    """Register a single page handler against every method it accepts."""

    async def _handler(request: Request) -> Response:
        # Path params arrive as a Mapping on Starlette — we coerce
        # to a plain dict so the pipeline sees a stable shape.
        path_params = dict(request.path_params)
        # The ctx was built by the render-context middleware ; pull it
        # off the active task rather than reconstructing.
        from bretzel.render.context import current_context

        ctx = current_context()

        # ── Partial-nav detection ──────────────────────────────────
        # When an htmx-boosted internal link fires, htmx sends:
        #     HX-Request: true
        #     HX-Target:  outlet_<layout_fn.__name__>
        # We walk the target page's layout chain (innermost → outermost
        # via the ``parent=`` decorator chain) looking for the layout
        # whose outlet matches ``HX-Target``. A match means the request
        # is a partial swap targeting THAT layout's outlet ; the
        # pipeline will render the layouts *inside* the match plus the
        # page, but skip everything outside (already mounted in the
        # browser). Initial loads / F5 / non-htmx clients miss the
        # match and fall through to the full render path.
        #
        # This covers both intra-section nav (HX-Target = innermost
        # layout outlet → page-only render, same as before) and cross-
        # section nav (HX-Target = an ancestor layout's outlet, e.g.
        # a sidebar in the outer ``shell`` jumping between
        # ``admin_shell`` and ``billing_shell`` siblings → renders the
        # whole inner sub-chain into the shared ``outlet_shell``).
        hx_request = request.headers.get("HX-Request") == "true"
        hx_target = request.headers.get("HX-Target", "")
        if hx_request and meta.layout is not None and hx_target:
            if _match_outlet_in_chain(meta.layout, hx_target) is not None:
                ctx.is_partial = True
                ctx.partial_target = hx_target

        result = await render_page(
            bretzel_app, page_fn, ctx=ctx, path_params=path_params
        )
        response = HTMLResponse(content=result.body, status_code=result.status_code)
        # Push pipeline-emitted headers (e.g. ``HX-Trigger`` carrying
        # the new title on a partial nav) onto the response. We skip
        # the entity headers Starlette controls.
        for name, value in result.headers.items():
            if name.lower() in ("content-length", "content-type"):
                continue
            response.headers[name] = value
        return response

    for method in meta.methods:
        fastapi.add_api_route(
            meta.path,
            _handler,
            methods=[method],
            response_class=HTMLResponse,
            include_in_schema=False,
            name=page_fn.__qualname__,
        )


def _match_outlet_in_chain(
    layout_fn: Callable[..., Any], hx_target: str
) -> Callable[..., Any] | None:
    """Return the layout in ``layout_fn``'s chain whose outlet matches
    ``hx_target``, or ``None`` if no layer in the chain matches.

    Delegates the walk to :func:`bretzel.render.pipeline._resolve_layout_chain`
    so we share the cycle detection + ``_bz_layout.parent`` traversal
    discipline with the pipeline's own chain resolution. Layout names
    are unique within an app, so iteration order (outermost-first vs
    innermost-first) doesn't affect the match — there's at most one.
    """
    for fn in _resolve_layout_chain(layout_fn):
        if hx_target == outlet_id_for(fn.__name__):
            return fn
    return None
