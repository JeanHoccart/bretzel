"""End-to-end tests for ``@error_page`` + exception-handler wiring.

Covers the three handlers registered by
:func:`bretzel.server.routing.errors.register_error_handlers` :

- ``StarletteHTTPException`` → 404 / ``abort()`` paths.
- ``BretzelError`` → forced 500 with debug-aware detail.
- ``Exception`` catch-all → enabled only in prod (``mode="prod"``).

Plus the layered fallback to :func:`default_error_page` when no
user handler is registered, or when the user page itself raises.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, abort, error_page, page, ui
from bretzel.server.errors import BretzelError

_SECRET = "x" * 32


# ───────────────────────────────────────────────────────────────────────────
# 404 — no handler vs. user-registered handler
# ───────────────────────────────────────────────────────────────────────────


class TestNotFoundFallback:
    def test_no_handler_returns_default_html(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")
        with TestClient(app) as client:
            response = client.get("/does-not-exist")
        assert response.status_code == 404
        assert "text/html" in response.headers["content-type"]
        # Default page is self-contained — no external stylesheet.
        assert "<!doctype html>" in response.text.lower()
        assert "404" in response.text
        assert "Page not found" in response.text
        # No JSON detail leak.
        assert '{"detail"' not in response.text

    def test_user_handler_rendered(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")

        @error_page(404)
        def not_found() -> None:
            ui.heading("Custom 404", level=1)
            ui.text("Lost in the void.")

        app.include(not_found)
        with TestClient(app) as client:
            response = client.get("/nope")
        assert response.status_code == 404
        # User content renders through the full pipeline → envelope present.
        assert "Custom 404" in response.text
        assert "Lost in the void." in response.text
        assert "<bz-envelope>" in response.text

    def test_title_kwarg_lands_in_head(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")

        @error_page(404, title="Page introuvable")
        def not_found() -> None:
            ui.text("Sorry.")

        app.include(not_found)
        with TestClient(app) as client:
            response = client.get("/nope")
        assert "<title>Page introuvable</title>" in response.text


# ───────────────────────────────────────────────────────────────────────────
# abort — turns a runtime call into a routed error page
# ───────────────────────────────────────────────────────────────────────────


class TestAbort:
    def test_abort_default_page_carries_detail(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")

        @page("/secret")
        def secret() -> None:
            abort(403, "Project archived")

        app.include(secret)
        with TestClient(app) as client:
            response = client.get("/secret")
        assert response.status_code == 403
        # Detail flows into the default page as the message.
        assert "Project archived" in response.text

    def test_abort_routes_to_user_handler(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")

        @error_page(403)
        def forbidden() -> None:
            ui.heading("Forbidden", level=1)

        @page("/secret")
        def secret() -> None:
            abort(403)

        app.include(forbidden, secret)
        with TestClient(app) as client:
            response = client.get("/secret")
        assert response.status_code == 403
        assert "Forbidden" in response.text


# ───────────────────────────────────────────────────────────────────────────
# BretzelError — framework signalling a bug, always 500
# ───────────────────────────────────────────────────────────────────────────


class TestBretzelError:
    def test_bretzel_error_renders_500_user_page(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")

        @error_page(500)
        def server_error() -> None:
            ui.heading("Boom", level=1)

        @page("/broken")
        def broken() -> None:
            raise BretzelError("internal invariant violated")

        app.include(server_error, broken)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/broken")
        assert response.status_code == 500
        assert "Boom" in response.text

    def test_bretzel_error_strips_message_in_prod(self) -> None:
        # No user handler → default page. detail comes from
        # str(BretzelError) in debug, "" in prod.
        app = Bretzel(secret_key=_SECRET, mode="prod")

        @page("/broken")
        def broken() -> None:
            raise BretzelError("LEAKY SECRET DETAIL")

        app.include(broken)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/broken")
        assert response.status_code == 500
        # Internal message must not surface in production.
        assert "LEAKY SECRET DETAIL" not in response.text


# ───────────────────────────────────────────────────────────────────────────
# Catch-all — only in prod (mode="prod")
# ───────────────────────────────────────────────────────────────────────────


class TestUnhandledException:
    def test_prod_catches_bare_exception(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="prod")

        @page("/oops")
        def oops() -> None:
            raise RuntimeError("unexpected")

        app.include(oops)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/oops")
        # Caught by the catch-all → static 500 page (no user handler).
        assert response.status_code == 500
        assert "500" in response.text
        # No traceback leak.
        assert "Traceback" not in response.text
        assert "unexpected" not in response.text

    def test_debug_lets_traceback_escape(self) -> None:
        # In debug we do NOT register the catch-all — keep FastAPI's
        # default behaviour intact. Starlette re-raises through the
        # TestClient when ``raise_server_exceptions=True`` (default).
        app = Bretzel(secret_key=_SECRET, mode="dev")

        @page("/oops")
        def oops() -> None:
            raise RuntimeError("debug-visible")

        app.include(oops)
        with TestClient(app) as client:
            with pytest.raises(RuntimeError, match="debug-visible"):
                client.get("/oops")


# ───────────────────────────────────────────────────────────────────────────
# Layered fallback — broken user page degrades gracefully
# ───────────────────────────────────────────────────────────────────────────


class TestRenderFallback:
    def test_crashing_user_page_falls_back_to_default(self) -> None:
        app = Bretzel(secret_key=_SECRET, mode="dev")

        @error_page(404)
        def broken_not_found() -> None:
            raise RuntimeError("user error page crashed")

        app.include(broken_not_found)
        with TestClient(app) as client:
            response = client.get("/missing")
        # Status preserved, body is the static fallback.
        assert response.status_code == 404
        assert "Page not found" in response.text
        # The user crash didn't leak — the static page has no envelope.
        assert "<bz-envelope>" not in response.text
