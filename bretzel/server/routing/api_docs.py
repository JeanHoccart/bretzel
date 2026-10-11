"""``GET /docs`` — Swagger UI over the app's own JSON API, opt-in.

An app serves its API as plain routes on ``app.fastapi`` (a caller with
``Authorization: Bearer`` writes past the CSRF check, cf.
:mod:`bretzel.server.middleware.csrf`). ``Bretzel(api_docs=True)`` gives
those routes the usual pair: the schema at ``/openapi.json`` and an
interactive page at ``/docs``. Off by default: the schema maps every
route the app declares there, and publishing that is the app's call.

What FastAPI's own page could not do for a Bretzel app:

- **the schema declares the bearer scheme**, so "Authorize" takes the
  key and "Try it out" sends it. Without it, every write tried from the
  page answers the CSRF 403. A public route opts out with
  ``openapi_extra={"security": []}``;
- **the page carries its own CSP** when ``csp=`` is on: Swagger UI comes
  from a CDN and initialises in an inline script, both of which the
  app's policy blocks. Same builder, same ``csp_sources`` ; the
  middleware's ``setdefault`` leaves a route's own header in place;
- **a route already at ``/docs`` or ``/openapi.json`` raises** at
  startup. The first route registered would win, silently.

The framework's own routes never appear in the schema: each one is
declared ``include_in_schema=False``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from fastapi.openapi.docs import get_swagger_ui_html
from starlette.responses import HTMLResponse

from bretzel.render.shell import favicon_href
from bretzel.server.security import CSP_HEADER, build_policy

if TYPE_CHECKING:
    from fastapi import FastAPI

    from bretzel.render.types import BretzelApp

DOCS_ROUTE = "/docs"
OPENAPI_ROUTE = "/openapi.json"

_SWAGGER_JS = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
_SWAGGER_CSS = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
INLINE_SCRIPT = re.compile(r"<script>(.*?)</script>", re.DOTALL)

# The route's name, which is how a second startup recognises it.
_DOCS_NAME = "bretzel_api_docs"


def register_api_docs(fastapi: FastAPI, bretzel_app: BretzelApp) -> None:
    """Mount ``/docs`` and declare the bearer scheme, if ``api_docs``.

    Called LAST among the routes: the collision check needs every page
    already registered.
    """
    config = bretzel_app.config
    if not config.api_docs:
        return
    # The same app can start twice (a test opening two clients on it)
    # and ``_register_routes`` runs on each start: once is enough here,
    # and a second ``/docs`` would read as a collision.
    if any(getattr(r, "name", None) == _DOCS_NAME for r in fastapi.routes):
        return

    build_schema = fastapi.openapi

    def openapi_with_bearer() -> dict[str, Any]:
        # ``setdefault``: a scheme or a global requirement the app
        # declared itself (FastAPI's ``Security``) stays its own.
        schema = build_schema()
        schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
        schemes.setdefault("bearer", {"type": "http", "scheme": "bearer"})
        schema.setdefault("security", [{"bearer": []}])
        return schema

    fastapi.openapi = openapi_with_bearer  # type: ignore[method-assign]

    html = get_swagger_ui_html(
        openapi_url=OPENAPI_ROUTE,
        title=f"{config.title} — API",
        swagger_js_url=_SWAGGER_JS,
        swagger_css_url=_SWAGGER_CSS,
        swagger_favicon_url=favicon_href(config.favicon, getattr(bretzel_app, "_cache_bust", None)),
    ).body
    headers: dict[str, str] = {}
    if config.csp is not False:
        headers[CSP_HEADER[config.csp]] = build_policy(
            inline_bodies=INLINE_SCRIPT.findall(html.decode("utf-8")),
            script_urls=[_SWAGGER_JS],
            style_urls=[_SWAGGER_CSS],
            extra=config.csp_sources,
        )

    @fastapi.get(DOCS_ROUTE, include_in_schema=False, name=_DOCS_NAME)
    async def _api_docs() -> HTMLResponse:
        return HTMLResponse(html, headers=headers)

    for path in (DOCS_ROUTE, OPENAPI_ROUTE):
        if sum(getattr(r, "path", None) == path for r in fastapi.routes) > 1:
            raise RuntimeError(
                f"`Bretzel(api_docs=True)` serves {path}, and the app already "
                f"declares a route there. Move that route, or drop api_docs."
            )
