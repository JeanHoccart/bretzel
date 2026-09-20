"""``GET /manifest.webmanifest`` — the app's manifest, when it declares one.

The route is only mounted when ``Bretzel(pwa=…)`` is set: an app that
asks for nothing does not carry the vocabulary.

⚠️ The MIME type is ``application/manifest+json`` and not
``application/json``. That is not fussiness: it is what the spec
requires, and browsers' diagnostic tools refuse a manifest served
otherwise — so the app would look non-installable with no error saying
so.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.responses import Response

from bretzel.server.pwa import MANIFEST_ROUTE

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp


def register_manifest_route(fastapi: FastAPI, bretzel_app: BretzelApp) -> None:
    """Mount the manifest route, if there is a manifest."""
    pwa = getattr(bretzel_app.config, "pwa", None)
    if pwa is None:
        return

    body = pwa.as_json()

    @fastapi.get(MANIFEST_ROUTE, include_in_schema=False)
    async def _manifest() -> Response:
        return Response(body, media_type="application/manifest+json")
