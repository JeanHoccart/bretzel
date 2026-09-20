"""``GET /_bretzel/sse`` — the EventSource endpoint for realtime.

The route opens a long-lived ``text/event-stream`` response, delegates
to :meth:`SSEBroker.connect` for the per-session event generator,
applies the headers proxies care about (no caching, no buffering), and
returns. Auth comes for free via the session cookie + auth middleware
upstream — no extra signature handshake.

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import PlainTextResponse, StreamingResponse

from bretzel.runtime.protocol import ROUTE_SSE, SSE_TAB_PARAM
from bretzel.server.middleware._state import ensure_state

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp


def register_sse_route(fastapi: FastAPI, bretzel_app: BretzelApp) -> None:
    """Wire ``GET /_bretzel/sse`` on ``fastapi``.

    The route reads the session id off the request state (populated by
    :class:`SessionMiddleware <bretzel.server.middleware.session.SessionMiddleware>`),
    hands it to the broker, and streams the result. Disconnects unwind
    via ``StreamingResponse`` → Starlette cancellation → broker
    teardown in :py:meth:`MemoryBroker.connect`'s ``finally`` block.
    """

    @fastapi.get(ROUTE_SSE, include_in_schema=False)
    async def _sse_stream(request: Request) -> StreamingResponse:
        broker = bretzel_app.sse_broker
        if broker is None:
            # App built without going through ``bretzel_startup`` —
            # the route exists but can't function. Return 503 so test
            # rigs notice rather than streaming forever.
            return PlainTextResponse(
                "SSE broker not initialised.",
                status_code=503,
            )

        state = ensure_state(request.scope)
        session_id = getattr(state, "session_id", "") or ""
        if not session_id:
            return PlainTextResponse(
                "No session cookie — open a page first.",
                status_code=400,
            )

        # ⚠️ In the URL and not in a header: ``EventSource`` has no way
        # of setting one. The identity is drawn by the browser on every
        # page load, it designates nothing server-side and does not
        # survive the tab being closed.
        tab_id = (request.query_params.get(SSE_TAB_PARAM) or "").strip()[:64]

        return StreamingResponse(
            broker.connect(session_id, tab_id),
            media_type="text/event-stream",
            headers={
                # The EventSource client owns reconnection ; the
                # browser default 3s is fine. Disable any caching
                # layer between us and the client.
                "Cache-Control": "no-cache, no-transform",
                # Nginx-specific : turn off buffering so events land
                # at the browser immediately rather than at 4 KB
                # chunk boundaries.
                "X-Accel-Buffering": "no",
                # Some proxies sniff Connection: keep-alive ; spell
                # it out so they don't silently downgrade to close.
                "Connection": "keep-alive",
            },
        )
