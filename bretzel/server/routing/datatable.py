"""``GET /_bretzel/datatable.csv`` — the Datatable's export endpoint.

Why this is a route and not an action. An action's response is swapped
into the page by the runtime bridge ; a download's response has to BE the
file. So the CSV button is a plain signed link the bridge leaves alone
(``hx-boost="false"``), and this route answers it.

Why the endpoint needs a payload at all. By the time the reader clicks
Export, the render that built the table is long gone — with it the row
list, the column labels and the component itself. So the link carries
what cannot be rediscovered : the reader's **query** (as values, not as a
state address — a download is a plain navigation with no page identity,
so resolving the page-scoped state here would export the default view),
the rows callable to re-run it as a ``module::qualname`` address, and the
``(key, label)`` pairs.

Why it is signed. ``rows_ref`` names a callable the server will invoke. An
unsigned parameter would make this endpoint a "call any module-level
function of my choosing" gadget. The HMAC is the same one that guards
actions, over the same payload the link was built with, and it is checked
BEFORE anything in the payload is decoded or resolved.

⚠️ The link is a bearer capability with no user binding and no expiry :
whoever holds the URL gets the rows. That is deliberate — an expiring
download 403s under a reader who left the tab open, and there is no
bridge to catch it — but an app serving per-user data must scope its rows
callable itself.

The CSV itself follows RFC 4180, with the two corrections the V1
implementation had already identified and which are easy to get wrong :
a UTF-8 BOM so Excel does not mangle accents, and quoting only when the
value actually needs it.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import Response

from bretzel.components import Query
from bretzel.components.data.datatable.datatable import (
    EXPORT_ROUTE,
    decode_export,
)
from bretzel.components.data.table import read_cell
from bretzel.core import call_without_blocking
from bretzel.render.context import maybe_current_context
from bretzel.server.handlers import (
    HandlerResolutionError,
    resolve_handler,
    verify_action,
)
from bretzel.server.routing._csv import to_csv
from bretzel.state.registry import use_registry

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp



def register_datatable_export_route(
    fastapi: FastAPI, bretzel_app: BretzelApp
) -> None:
    """Wire the single ``GET /_bretzel/datatable.csv`` route."""

    @fastapi.get(EXPORT_ROUTE, include_in_schema=False)
    async def _export(request: Request) -> Response:
        return await _serve(bretzel_app, request)


async def _serve(bretzel_app: BretzelApp, request: Request) -> Response:
    payload = request.query_params.get("q", "")
    signature = request.query_params.get("sig", "")
    key = getattr(bretzel_app.config, "_action_key", b"")
    # Same gate as an action, minus the timestamp : an export link is
    # meant to survive as long as the page it sits on, so an age limit
    # would expire the button under a reader who left the tab open.
    if not key or not verify_action(key, EXPORT_ROUTE, payload, signature):
        return Response("Forbidden", status_code=403)

    try:
        spec = decode_export(payload)
        rows_source = resolve_handler(spec["r"])
        # The reader's view rides IN the link. A plain browser navigation
        # carries no page identity, so resolving the page-scoped state
        # here would hand back a pristine query and export the default
        # view — with ``for_export`` forced on either way, because a
        # tampered payload must not be able to ask for a single page.
        query = replace(Query(**spec["q"]), for_export=True)
    except (HandlerResolutionError, ValueError, KeyError, TypeError):
        return Response("Not found", status_code=404)

    try:
        columns: list[list[str]] = spec["c"]
        filename = spec.get("f") or "export.csv"
    except (KeyError, TypeError):
        return Response("Not found", status_code=404)

    # Run the caller's code the way EVERY other user-code entry point in
    # this framework runs it — inside the request's state registry. This
    # is a fourth entry point (page render, action, realtime refetch,
    # and now export) and the only one that had been written bare.
    #
    # Measured before fixing : without the registry, ``current_registry()``
    # is None and ``StateMeta.__call__`` falls through to a plain
    # constructor — so two ``MyState()`` calls inside one callable
    # returned two DIFFERENT objects, ``get()`` saw no form data, and
    # nothing the callable read was the request's state.
    #
    # ⚠️ What this does NOT fix : a ``SessionState`` written during the
    # page render still reads its default here. Verified that an ordinary
    # action handler behaves identically, so that is a framework-wide
    # property of the sync-resolve path, not something this route broke.
    # Noted in work/todo.md rather than papered over here.
    context = maybe_current_context()
    registry = getattr(context, "state_registry", None) if context else None
    with use_registry(registry) if registry is not None else nullcontext():
        # A rows callable that hits a database is the tier's whole
        # reason to exist — so it is awaited when it is ``async``, and
        # OFFLOADED onto the threadpool when it is a ``def``: a blocking
        # read here froze the worker's loop for the duration of the
        # export (cf. ``core/invoke``).
        rows, _total = await call_without_blocking(rows_source, query)

    return Response(
        to_csv(rows, columns, read_cell),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


