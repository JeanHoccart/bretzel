"""``GET /_bretzel/refetch/{state}/{zone}`` — the per-zone refetch route.

Triggered by the runtime when an SSE ``state-dirty`` event names a
State the page has zones subscribed to. The path carries both the
State's wire identifier and the zone's, so the route can :

1. Resolve the zone callable (a :class:`RefreshableHandle` produced by
   ``@refreshable(deps=[State], broadcast=[State])``) via ``sys.modules`` — same
   scheme as the action route, no separate registry.
2. Defend against forged URLs : the resolved handle must carry the
   matching State binding. An attacker who swapped the state segment
   for an unrelated State qualname (or pointed the zone segment at a
   bare ``@refreshable`` zone with no subscribe binding) gets 404 —
   not a re-render of a zone they shouldn't see.
3. Re-render the zone in the client's **own** RenderContext, which
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
from bretzel.render.decorators.refreshable import (
    RefreshableHandle,
)
from bretzel.render.partials import render_partial
from bretzel.runtime.protocol import ROUTE_REFETCH
from bretzel.server.handlers import HandlerResolutionError, resolve_handler
from bretzel.state.registry import use_registry

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp


def register_realtime_route(fastapi: FastAPI, bretzel_app: BretzelApp) -> None:
    """Wire ``GET /_bretzel/refetch/{state_qualname}/{zone_qualname}``."""

    @fastapi.get(
        ROUTE_REFETCH + "/{state_qualname}/{zone_qualname:path}",
        include_in_schema=False,
    )
    async def _refetch_zone(
        state_qualname: str,
        zone_qualname: str,
        request: Request,  # unread here — the context is set upstream
    ) -> Response:
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

        if not target.broadcast:
            # Got a non-broadcast zone (bare ``@refreshable`` or a purely
            # local ``deps=`` zone) — refuse rather than serve a zone that
            # was never meant to be remotely refetched.
            return HTMLResponse(
                content="Zone is not a broadcast zone.",
                status_code=404,
            )
        if state_qualname not in set(target._broadcast_qualnames()):
            # The state segment isn't one of the zone's broadcast
            # channels — forged URL or stale client after a code change.
            #
            # ⚠️ **``broadcast``, and not ``deps``.** This line read
            # ``deps`` until 2026-09-09, and the two coincide as long as
            # ``broadcast`` is a subset of ``deps`` — which the
            # repository's six real declarations are. They diverge in the
            # very case the documentation puts forward:
            #
            #     @refreshable(broadcast=[Queue])   # I never change it
            #
            # ``deps`` is then EMPTY, so the guard always refused.
            # Measured: the zone subscribes, the signal arrives, the
            # browser goes to fetch, the server answers **404**, and
            # nothing moves — without a word, no console, no log. A zone
            # that only broadcasts had been dead all along.
            #
            # The client subscribes on ``_broadcast_qualnames()`` (cf.
            # ``refreshable._subscribe_url``): validating against the
            # same list is therefore the only one that can be true. It is
            # also TIGHTER — a zone with ``deps=[A, B], broadcast=[B]``
            # accepted a refetch for ``A``, which it announces nowhere.
            return HTMLResponse(
                content="Zone / State mismatch.",
                status_code=404,
            )

        ctx = current_context()
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
