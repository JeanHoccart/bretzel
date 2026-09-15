"""Unit tests for :class:`bretzel.server.middleware.csrf.CSRFMiddleware`.

We stand up a tiny Starlette app that stacks
:class:`SessionMiddleware <bretzel.server.middleware.session.SessionMiddleware>`
+ the :class:`CSRFMiddleware` we want to exercise + a couple of stub
routes. Tests then drive it with ``TestClient`` exactly the way a real
browser would — read the ``Bretzel_session`` cookie, compute the
expected token, send it back on the next POST.
"""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from bretzel.runtime.protocol import ROUTE_ACTION
from bretzel.server.crypto import PURPOSE_CSRF, derive_key
from bretzel.server.middleware.csrf import CSRFMiddleware, csrf_token_for
from bretzel.server.middleware.session import SessionMiddleware

_MASTER = "x" * 32
_CSRF_KEY = derive_key(_MASTER, PURPOSE_CSRF)


# ───────────────────────────────────────────────────────────────────────────
# Stub app
# ───────────────────────────────────────────────────────────────────────────


async def _ok(request):  # type: ignore[no-untyped-def]
    return PlainTextResponse("ok")


async def _ok_action(request):  # type: ignore[no-untyped-def]
    """Stand-in for the framework action route — protected by HMAC,
    NOT by CSRF (the middleware short-circuits these)."""
    return PlainTextResponse("ok-action")


def _build_app(trusted_hosts: tuple[str, ...] = ()) -> Starlette:
    """Stack SessionMiddleware → CSRFMiddleware → a couple of routes.

    Order matches what ``lifecycle.build_middleware_stack`` does in
    prod : Session mints the cookie outermost, CSRF reads
    ``state.session_id`` inside.
    """
    app = Starlette(
        routes=[
            Route("/", _ok, methods=["GET"]),
            Route("/submit", _ok, methods=["POST"]),
            Route(f"{ROUTE_ACTION}/dummy", _ok_action, methods=["POST"]),
        ],
    )
    app.add_middleware(
        CSRFMiddleware,
        csrf_key=_CSRF_KEY,
        trusted_hosts=trusted_hosts,
    )
    app.add_middleware(
        SessionMiddleware,
        max_age_seconds=3600,
        secure=False,
    )
    return app


def _prime_session(client: TestClient) -> str:
    """Hit a GET so the Session middleware mints a cookie ; return its value."""
    response = client.get("/")
    assert response.status_code == 200
    return client.cookies["Bretzel_session"]


# ───────────────────────────────────────────────────────────────────────────
# Safe methods pass through
# ───────────────────────────────────────────────────────────────────────────


class TestSafeMethods:
    def test_get_unchecked(self) -> None:
        with TestClient(_build_app()) as client:
            response = client.get("/")
        assert response.status_code == 200

    def test_head_unchecked(self) -> None:
        with TestClient(_build_app()) as client:
            response = client.head("/")
        assert response.status_code == 200


# ───────────────────────────────────────────────────────────────────────────
# Action route is skipped (HMAC handles it elsewhere)
# ───────────────────────────────────────────────────────────────────────────


class TestActionRouteSkipped:
    def test_post_to_action_route_passes_without_csrf(self) -> None:
        # Even without ``X-Bretzel-CSRF``, the action route is not
        # CSRF-checked — the per-call HMAC inside the action dispatcher
        # is the authoritative gate.
        with TestClient(_build_app()) as client:
            response = client.post(f"{ROUTE_ACTION}/dummy")
        assert response.status_code == 200
        assert response.text == "ok-action"


# ───────────────────────────────────────────────────────────────────────────
# User POST routes
# ───────────────────────────────────────────────────────────────────────────


class TestUserPostRoute:
    def test_missing_token_rejected(self) -> None:
        with TestClient(_build_app()) as client:
            _prime_session(client)
            response = client.post("/submit")
        assert response.status_code == 403
        assert "CSRF" in response.text

    def test_wrong_token_rejected(self) -> None:
        with TestClient(_build_app()) as client:
            _prime_session(client)
            response = client.post(
                "/submit",
                headers={"X-Bretzel-CSRF": "deadbeef" * 4},
            )
        assert response.status_code == 403

    def test_correct_token_accepted(self) -> None:
        with TestClient(_build_app()) as client:
            session_id = _prime_session(client)
            token = csrf_token_for(session_id, _CSRF_KEY)
            response = client.post(
                "/submit",
                headers={"X-Bretzel-CSRF": token},
            )
        assert response.status_code == 200
        assert response.text == "ok"

    def test_token_from_different_session_rejected(self) -> None:
        # Tokens are session-bound : a leaked token from session A
        # cannot validate a request that carries session B's cookie.
        token_from_other = csrf_token_for("some-other-session-id", _CSRF_KEY)
        with TestClient(_build_app()) as client:
            _prime_session(client)
            response = client.post(
                "/submit",
                headers={"X-Bretzel-CSRF": token_from_other},
            )
        assert response.status_code == 403


# ───────────────────────────────────────────────────────────────────────────
# Origin / Referer check
# ───────────────────────────────────────────────────────────────────────────


class TestOriginCheck:
    def test_no_origin_allowed_with_valid_token(self) -> None:
        # curl / server-to-server : no Origin/Referer. Token check
        # remains the gate, which is the right behaviour.
        with TestClient(_build_app()) as client:
            session_id = _prime_session(client)
            token = csrf_token_for(session_id, _CSRF_KEY)
            response = client.post(
                "/submit",
                headers={"X-Bretzel-CSRF": token},
            )
        assert response.status_code == 200

    def test_cross_origin_rejected_even_with_valid_token(self) -> None:
        # The killer case : attacker has the token (e.g. leaked via
        # log file) but the request comes from a hostile origin. The
        # Origin check catches it before the token check.
        with TestClient(_build_app()) as client:
            session_id = _prime_session(client)
            token = csrf_token_for(session_id, _CSRF_KEY)
            response = client.post(
                "/submit",
                headers={
                    "X-Bretzel-CSRF": token,
                    "Origin": "https://evil.example.com",
                },
            )
        assert response.status_code == 403
        assert "origin" in response.text.lower()

    def test_same_origin_accepted(self) -> None:
        with TestClient(_build_app()) as client:
            session_id = _prime_session(client)
            token = csrf_token_for(session_id, _CSRF_KEY)
            response = client.post(
                "/submit",
                headers={
                    "X-Bretzel-CSRF": token,
                    "Origin": "http://testserver",  # TestClient's default host
                },
            )
        assert response.status_code == 200

    def test_trusted_host_origin_accepted(self) -> None:
        # The app sits behind a proxy whose external hostname is in
        # ``trusted_hosts`` — we accept that origin too.
        with TestClient(_build_app(trusted_hosts=("app.example.com",))) as client:
            session_id = _prime_session(client)
            token = csrf_token_for(session_id, _CSRF_KEY)
            response = client.post(
                "/submit",
                headers={
                    "X-Bretzel-CSRF": token,
                    "Origin": "https://app.example.com",
                },
            )
        assert response.status_code == 200

    def test_trusted_host_wildcard_accepted(self) -> None:
        with TestClient(_build_app(trusted_hosts=("*.example.com",))) as client:
            session_id = _prime_session(client)
            token = csrf_token_for(session_id, _CSRF_KEY)
            response = client.post(
                "/submit",
                headers={
                    "X-Bretzel-CSRF": token,
                    "Origin": "https://sub.example.com",
                },
            )
        assert response.status_code == 200

    def test_referer_fallback_when_no_origin(self) -> None:
        # Some legitimate paths only send Referer (browser default for
        # top-level GET-then-POST chains). Same check applies.
        with TestClient(_build_app()) as client:
            session_id = _prime_session(client)
            token = csrf_token_for(session_id, _CSRF_KEY)
            response = client.post(
                "/submit",
                headers={
                    "X-Bretzel-CSRF": token,
                    "Referer": "https://evil.example.com/path",
                },
            )
        assert response.status_code == 403
