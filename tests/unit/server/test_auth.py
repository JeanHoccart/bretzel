"""Unit tests for ``bretzel.server.auth``.

Auth helpers read / write through the active ``RenderContext``, so
the tests spin up a context with a stub app + minimal config and
inspect ``ctx.new_cookies`` / ``ctx.user_id`` after the call.
"""

from __future__ import annotations

import time

import pytest

from bretzel.render.context import RenderContext, use_context
from bretzel.server.auth import (
    COOKIE_AUTH,
    COOKIE_SESSION,
    AuthUser,
    login,
    user_id,
    logout,
    is_authenticated,
    verify_auth_cookie,
)
from bretzel.server.crypto import PURPOSE_AUTH, derive_key


_SECRET = "x" * 32
_AUTH_KEY = derive_key(_SECRET, PURPOSE_AUTH)


# ───────────────────────────────────────────────────────────────────────────
# Test fixtures
# ───────────────────────────────────────────────────────────────────────────


class _StubConfig:
    secret_key = _SECRET
    session_max_age_days = 30
    # Mirrors what ``BretzelConfig.__post_init__`` derives — the auth
    # path reads this directly via ``ctx.app.config._auth_key`` now
    # that we no longer hand the raw secret to HMAC.
    _auth_key = _AUTH_KEY


class _StubApp:
    config = _StubConfig()
    debug = True
    _pages: list = []
    _realtime: dict = {}
    _error_handlers: dict = {}

    @property
    def theme(self) -> object:
        return object()

    @property
    def state_backend(self) -> object:
        return object()


class _StubRequestState:
    user: AuthUser | None = None


class _StubRequest:
    state = _StubRequestState()


def _ctx() -> RenderContext:
    return RenderContext(app=_StubApp(), request=_StubRequest())


# ───────────────────────────────────────────────────────────────────────────
# login — sets cookies + rotates session
# ───────────────────────────────────────────────────────────────────────────


class TestLogin:
    def test_sets_auth_cookie(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            login("user-42")
        assert COOKIE_AUTH in ctx.new_cookies
        cookie = ctx.new_cookies[COOKIE_AUTH]
        assert "user-42" in cookie["value"]
        assert cookie["httponly"] is True
        assert cookie["samesite"] == "lax"
        # mode="dev" → secure=False (HTTP allowed in dev).
        assert cookie["secure"] is False

    def test_rotates_session(self) -> None:
        ctx = _ctx()
        ctx.session_id = "old"
        with use_context(ctx):
            login("user-42")
        assert ctx.session_id != "old"
        assert COOKIE_SESSION in ctx.new_cookies
        assert ctx.new_cookies[COOKIE_SESSION]["value"] == ctx.session_id

    def test_updates_ctx_user_id(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            login("user-42")
        assert ctx.user_id == "user-42"

    def test_updates_request_state_user(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            login("user-42")
        user = ctx.request.state.user
        assert user is not None
        assert user.id == "user-42"
        assert user.is_authenticated is True

    def test_non_string_id_rejected(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            with pytest.raises(TypeError):
                login(42)  # type: ignore[arg-type]

    def test_empty_id_rejected(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            with pytest.raises(TypeError):
                login("")


# ───────────────────────────────────────────────────────────────────────────
# logout — clears auth + rotates session
# ───────────────────────────────────────────────────────────────────────────


class TestLogout:
    def test_clears_auth_cookie(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            login("user-42")
            logout()
        assert COOKIE_AUTH in ctx.deleted_cookies

    def test_rotates_session(self) -> None:
        ctx = _ctx()
        ctx.session_id = "before-logout"
        with use_context(ctx):
            login("user-42")
            sid_after_login = ctx.session_id
            logout()
            sid_after_logout = ctx.session_id
        assert sid_after_logout != sid_after_login

    def test_clears_user_id(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            login("user-42")
            logout()
        assert ctx.user_id is None
        assert ctx.request.state.user is None

    def test_idempotent_on_anonymous(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            logout()  # no-op-ish, must not raise
        assert COOKIE_AUTH in ctx.deleted_cookies


# ───────────────────────────────────────────────────────────────────────────
# user_id / is_authenticated
# ───────────────────────────────────────────────────────────────────────────


class TestReadAPI:
    def test_returns_none_when_anonymous(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            assert user_id() is None
            assert is_authenticated() is False

    def test_returns_id_after_login(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            login("user-42")
            assert user_id() == "user-42"
            assert is_authenticated() is True


# ───────────────────────────────────────────────────────────────────────────
# verify_auth_cookie — round-trip
# ───────────────────────────────────────────────────────────────────────────


class TestVerifyAuthCookie:
    def test_round_trip(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            login("user-42")
        cookie = ctx.new_cookies[COOKIE_AUTH]["value"]
        assert verify_auth_cookie(cookie, _AUTH_KEY) == "user-42"

    def test_missing_signature_rejected(self) -> None:
        assert verify_auth_cookie("user:0", _AUTH_KEY) is None

    def test_malformed_payload_rejected(self) -> None:
        assert verify_auth_cookie("malformed.signature", _AUTH_KEY) is None

    def test_wrong_secret_rejected(self) -> None:
        ctx = _ctx()
        with use_context(ctx):
            login("user-42")
        cookie = ctx.new_cookies[COOKIE_AUTH]["value"]
        # A *different* derived key — what an attacker with another
        # master secret would compute. Must not verify.
        assert verify_auth_cookie(cookie, derive_key("y" * 32, PURPOSE_AUTH)) is None

    def test_expired_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _ctx()
        with use_context(ctx):
            login("user-42")
        cookie = ctx.new_cookies[COOKIE_AUTH]["value"]

        # Jump 60 days into the future — past the 30-day default.
        original = time.time
        monkeypatch.setattr(
            "bretzel.server.auth.time.time", lambda: original() + 60 * 86400
        )
        assert verify_auth_cookie(cookie, _AUTH_KEY) is None

    def test_empty_cookie_rejected(self) -> None:
        assert verify_auth_cookie("", _AUTH_KEY) is None


# ───────────────────────────────────────────────────────────────────────────
# ``Secure`` suit le transport, pas le mode
# ───────────────────────────────────────────────────────────────────────────


class _StubURL:
    def __init__(self, scheme: str) -> None:
        self.scheme = scheme


class _StubRequestWithScheme(_StubRequest):
    def __init__(self, scheme: str) -> None:
        self.url = _StubURL(scheme)


def _login_over(scheme: str, *, secure_cookies: bool | None = None) -> RenderContext:
    class _App(_StubApp):
        config = type(
            "_C", (_StubConfig,), {"secure_cookies": secure_cookies}
        )()

    ctx = RenderContext(app=_App(), request=_StubRequestWithScheme(scheme))
    with use_context(ctx):
        login("user-42")
    return ctx


def test_secure_on_https() -> None:
    ctx = _login_over("https")
    assert ctx.new_cookies[COOKIE_AUTH]["secure"] is True
    assert ctx.new_cookies[COOKIE_SESSION]["secure"] is True


def test_not_secure_on_http() -> None:
    # Le contraire casserait la session : un cookie ``Secure`` n'est pas
    # renvoyé sur une origine http. C'était le bug de ``secure=not debug``.
    ctx = _login_over("http")
    assert ctx.new_cookies[COOKIE_AUTH]["secure"] is False
    assert ctx.new_cookies[COOKIE_SESSION]["secure"] is False


def test_explicit_override_wins() -> None:
    # Cas réel : proxy qui termine le TLS sans ``proxy_headers=True``.
    ctx = _login_over("http", secure_cookies=True)
    assert ctx.new_cookies[COOKIE_AUTH]["secure"] is True
