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
        request: Request,  # non lu ici — le contexte est posé en amont
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
            # ⚠️ **``broadcast``, et pas ``deps``.** Cette ligne lisait
            # ``deps`` jusqu'au 2026-09-09, et les deux coïncident tant
            # que ``broadcast`` est un sous-ensemble de ``deps`` — ce que
            # font les six déclarations réelles du dépôt. Elles divergent
            # dans le cas que la doc met pourtant en avant :
            #
            #     @refreshable(broadcast=[FileAttente])   # je ne le
            #                                            # change jamais
            #
            # ``deps`` est alors VIDE, donc la garde refusait toujours.
            # Mesuré : la zone s'abonne, le signal arrive, le navigateur
            # va chercher, le serveur répond **404**, et rien ne bouge —
            # sans un mot, ni console ni journal. Une zone diffusée seule
            # était morte depuis toujours.
            #
            # Le client s'abonne sur ``_broadcast_qualnames()`` (cf.
            # ``refreshable._subscribe_url``) : valider contre la même
            # liste est donc la seule qui puisse être vraie. C'est aussi
            # plus SERRÉ — une zone ``deps=[A, B], broadcast=[B]``
            # acceptait un refetch pour ``A``, qu'elle n'annonce nulle
            # part.
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
