"""``GET /_bretzel/refetch/{zone}`` — the per-zone refetch route.

Triggered by the runtime when an SSE ``state-dirty`` event names a
state one of the page's zones read. The route :

1. Refuses a URL not signed for this session (``sig``, set at render by
   ``RefreshableHandle.subscription``): the zone renders outside its
   page, so outside whatever the page checks — only a client the zone
   was rendered for may ask for it again, and the signature covers the
   zone's identifier, so it cannot be pointed at another zone. A 403
   ``reload`` envelope, the same as a stale action signature (a login
   rotates the session).
2. Resolves the zone (a :class:`RefreshableHandle`) via ``sys.modules`` —
   same scheme as the action route, no separate registry.
3. Re-renders the zone in the client's **own** RenderContext, which
   the upstream middleware already set up : session / auth cookies
   are honoured and ``auth.user_id()`` returns the right value.
   This is a plain GET — no client-state travels on it (the bridge
   strips it ; ``X-Bretzel-Client-State`` was dropped in V3), so the
   zone renders from server-side state only.

"""

from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response

from bretzel.render.context import current_context
from bretzel.render.decorators.refreshable import RefreshableHandle
from bretzel.render.partials import render_partial
from bretzel.runtime.envelope import error_envelope
from bretzel.runtime.protocol import REFETCH_SIG_PARAM, ROUTE_REFETCH
from bretzel.server.handlers import HandlerResolutionError, resolve_handler, verify_refetch
from bretzel.state.registry import use_registry

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp


def register_realtime_route(fastapi: FastAPI, bretzel_app: BretzelApp) -> None:
    """Wire ``GET /_bretzel/refetch/{zone_qualname}``."""

    @fastapi.get(
        ROUTE_REFETCH + "/{zone_qualname:path}",
        include_in_schema=False,
    )
    async def _refetch_zone(zone_qualname: str, request: Request) -> Response:
        ctx = current_context()
        action_key = bretzel_app.config._action_key  # type: ignore[attr-defined]
        signature = request.query_params.get(REFETCH_SIG_PARAM, "")
        if not verify_refetch(action_key, zone_qualname, ctx.session_id, signature):
            return HTMLResponse(
                content=error_envelope("reload", "This zone was not rendered for this session."),
                status_code=403,
            )
        try:
            target = resolve_handler(zone_qualname)
        except HandlerResolutionError:
            return HTMLResponse(content="Unknown zone.", status_code=404)

        # The resolved name is the module attribute the user assigned
        # the decorated function to — which is the wrapping
        # :class:`RefreshableHandle`. Anything else (raw fn, bare
        # value) means the URL is forged or the app changed shape
        # mid-flight ; refuse rather than guess.
        if not isinstance(target, RefreshableHandle):
            return HTMLResponse(content="Zone is not refreshable.", status_code=404)

        # Bind the request's state registry so ``MyState()`` calls
        # inside the zone hit the cache + sync-hydrate path, same as
        # the action dispatch (see ``routing/actions.py``). Without
        # it ``IssueStore()`` would short-circuit through the
        # metaclass to a defaults-only instance and the zone would
        # render an empty fragment regardless of what's in the
        # backend.
        registry_cm = (
            use_registry(ctx.state_registry)
            if ctx.state_registry is not None
            else nullcontext()
        )
        with registry_cm:
            result = await render_partial(bretzel_app, target, ctx=ctx)
        return HTMLResponse(content=result.body, status_code=result.status_code)
