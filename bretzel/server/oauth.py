"""OAuth and OpenID Connect authentication providers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from bretzel.core import call_without_blocking
from bretzel.server.auth import (
    app_of,
    login,
    request_scheme,
    resolve_cookie_secure,
)
from bretzel.server.crypto import sign as _crypto_sign
from bretzel.server.crypto import verify as _crypto_verify
from bretzel.server.navigation import redirect_response

__all__ = ["OIDC", "OAuth2", "OAuthProfile", "OAuthError"]

#: Lifetime of the transaction cookie (``state`` + PKCE verifier). Ten
#: minutes: the time to type a password and a second factor at the
#: provider, not the time of a forgotten tab.
_TRANSACTION_MAX_AGE = 600

_HTTP_TIMEOUT = 10


class OAuthError(RuntimeError):
    """An OAuth transaction that does not complete, framework-side.

    It **never** carries the detail to the browser: the causes (missing
    state, refused code, profile with no identifier) are server
    diagnostics. The visitor is sent back to the sign-in page.
    """


@dataclass(frozen=True, slots=True)
class OAuthProfile:
    """Represent the normalized user profile returned by an OAuth provider."""

    subject: str
    email: str = ""
    name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    token: str = ""


# ───────────────────────────────────────────────────────────────────────────
# HTTP — stdlib, pushed into a thread
# ───────────────────────────────────────────────────────────────────────────


def _http_json(
    url: str,
    *,
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """One HTTP round trip returning JSON. Blocking — cf. :func:`_fetch`."""
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method="POST" if data else "GET")
    req.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        # ⚠️ An OAuth endpoint that REFUSES answers 4xx **with a useful
        # JSON body** (``{"error": "invalid_grant"}``) — that is the
        # protocol, not a failure. ``urlopen`` nonetheless raises on any
        # non-2xx, and without this catch the exception crossed the door:
        # the visitor got a 500 instead of coming back to the sign-in
        # page. Found on 2026-08-24 by faking the PKCE verifier against a
        # real provider — the probe did not turn red, it BROKE.
        try:
            payload = exc.read().decode("utf-8")
        except Exception:
            # Deliberately broad: empty body, truncated, exotic
            # encoding — the exact cause has no value here, there is only
            # one possible continuation, refusing cleanly.
            raise OAuthError(f"{url} returned {exc.code} without a readable response body") from None
    except urllib.error.URLError as exc:
        # Provider unreachable, DNS, TLS. A clean refusal rather than a
        # traceback: the visitor can do nothing about it.
        raise OAuthError(f"{url} injoignable : {exc.reason}") from None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        # GitHub returns form-urlencoded when the ``Accept`` header is
        # not honoured — we set it, but a provider may ignore it, and a
        # failure here would be unreadable.
        parsed = {k: v[0] for k, v in urllib.parse.parse_qs(payload).items()}
    if not isinstance(parsed, dict):
        raise OAuthError(f"{url} did not return a JSON object.")
    return parsed


async def _fetch(
    url: str,
    *,
    data: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """:func:`_http_json`, off the event loop.

    Same crossing point as app code (``core/invoke``): the HTTP call here
    is blocking by nature — ``urllib`` — and leaving it on the loop would
    freeze the worker for the duration of the code exchange.
    """
    return await call_without_blocking(_http_json, url, data=data, headers=headers)


def _b64url_json(segment: str) -> dict[str, Any]:
    """Decode one JWT segment (base64url without padding) into a dict."""
    padded = segment + "=" * (-len(segment) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception as exc:
        raise OAuthError("id_token illisible.") from exc


# ───────────────────────────────────────────────────────────────────────────
# La porte
# ───────────────────────────────────────────────────────────────────────────


class _Door:
    """The common trunk of both protocols: two routes and a transaction.

    Subclassing is not intended outside this module — what varies between
    the two forms fits in two methods (:meth:`_endpoints`,
    :meth:`_profile`), not in the sequence.
    """

    def __init__(
        self,
        *,
        name: str,
        client_id: str,
        client_secret: str,
        scope: str,
        path: str | None = None,
        redirect_uri: str | None = None,
        on_denied: str = "/login",
        on_success: str = "/",
    ) -> None:
        if not name or not name.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                f"oauth: name={name!r} must be alphanumeric — it becomes "
                "a URL segment and distinguishes two doors of the same "
                "protocol."
            )
        if not client_id or not client_secret:
            raise ValueError(
                f"oauth {name!r}: client_id and client_secret are required."
            )
        self.name = name
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.path = path or f"/auth/{name}"
        self.redirect_uri = redirect_uri
        self.on_denied = on_denied
        self.on_success = on_success

    # ── what the app and the guard read ────────────────────────────────

    @property
    def callback_path(self) -> str:
        return f"{self.path}/callback"

    @property
    def paths(self) -> tuple[str, str]:
        """The two paths, to be left open by any auth guard.

        BOTH: forgetting the callback produces a redirect loop whose
        symptom points at nothing. That is why they surface in
        ``app.public_paths`` instead of being copied by the app.
        """
        return (self.path, self.callback_path)

    # ── to be specialised ──────────────────────────────────────────────

    async def _endpoints(self) -> dict[str, str]:
        raise NotImplementedError

    async def _profile(self, tokens: dict[str, Any], nonce: str) -> OAuthProfile:
        raise NotImplementedError

    # ── the sequence, common ───────────────────────────────────────────

    def mount(self, app: Any, on_user: Any) -> None:
        """Mount the two routes on the underlying FastAPI.

        Raw routes, not ``@page``: a door renders no HTML — it redirects,
        twice. They do not need a render context for all that:
        ``RenderContextMiddleware`` wraps ALL requests, so
        ``auth.login()`` does set its cookie from the callback (measured
        on 2026-08-23).

        ⚠️ The three redirects go through :func:`redirect_response` and
        **never** through a bare ``RedirectResponse``. The reason is a
        trap nothing signals: ``render/shell.py`` sets ``hx-boost="true"``
        at document level as soon as a page carries an ``outlet``. The
        "Continue with X" link is an internal ``<a>``, so boosted — htmx
        would follow the 302 with ``fetch``, towards ANOTHER origin, and
        that fails silently (CORS) or swaps foreign HTML into the outlet.
        ``redirect_response`` then answers an ``HX-Redirect``, which the
        browser executes as a real navigation. ``examples/auth`` escaped
        it by accident (its sign-in page has no outlet), so the probe was
        green.
        """
        async def start(request: Any) -> Any:
            endpoints = await self._endpoints()
            state = secrets.token_urlsafe(24)
            verifier = secrets.token_urlsafe(48)
            nonce = secrets.token_urlsafe(16)
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            )
            params = {
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": self._redirect_uri(request),
                "scope": self.scope,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
            response = redirect_response(
                request, f"{endpoints['authorize']}?{urllib.parse.urlencode(params)}"
            )
            self._seal(request, response, state, verifier, nonce)
            return response

        async def callback(request: Any) -> Any:
            try:
                state, verifier, nonce = self._unseal(request)
                supplied = request.query_params.get("state", "")
                if not supplied or not hmac.compare_digest(supplied, state):
                    raise OAuthError("state absent ou non concordant.")
                code = request.query_params.get("code", "")
                if not code:
                    raise OAuthError(
                        "no code — the provider answered "
                        f"{request.query_params.get('error', 'saying nothing')}."
                    )
                endpoints = await self._endpoints()
                tokens = await _fetch(
                    endpoints["token"],
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": self._redirect_uri(request),
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "code_verifier": verifier,
                    },
                )
                if "access_token" not in tokens and "id_token" not in tokens:
                    raise OAuthError(
                        f"the token endpoint refused: {tokens.get('error')}"
                    )
                profile = await self._profile(tokens, nonce)
                # ``@auth.door`` REFUSES an ``async def`` (cf.
                # ``decorators/identity.py``), and its canonical example
                # is a ``users.upsert(...)`` — so a database write,
                # necessarily synchronous, in the callback. Offloaded,
                # otherwise it freezes the loop on every sign-in.
                user_id = await call_without_blocking(on_user, profile)
            except OAuthError:
                return self._refuse(request)
            if not user_id:
                return self._refuse(request)
            login(str(user_id))
            response = redirect_response(request, self.on_success)
            response.delete_cookie(self._cookie_name)
            return response

        app.fastapi.add_route(
            self.path, start, methods=["GET"], name=f"bz_login_{self.name}"
        )
        app.fastapi.add_route(
            self.callback_path,
            callback,
            methods=["GET"],
            name=f"bz_login_{self.name}_cb",
        )

    # ── transaction ────────────────────────────────────────────────────

    @property
    def _cookie_name(self) -> str:
        return f"Bretzel_oauth_{self.name}"

    def _refuse(self, request: Any) -> Any:
        """Every cause of refusal leaves through the same door, with no detail.

        An anonymous visitor who learns *why* their transaction failed
        learns something about the targeted account. The diagnosis stays
        server-side, in the raised exception.
        """
        response = redirect_response(request, self.on_denied)
        response.delete_cookie(self._cookie_name)
        return response

    def _key(self, request: Any) -> bytes:
        key = getattr(getattr(app_of(request), "config", None), "_auth_key", None)
        if not key:
            raise OAuthError("derived key unavailable — the application is not mounted")
        return key

    def _secure(self, request: Any) -> bool:
        config = getattr(app_of(request), "config", None)
        return resolve_cookie_secure(
            request_scheme(request), getattr(config, "secure_cookies", None)
        )

    def _seal(
        self, request: Any, response: Any, state: str, verifier: str, nonce: str
    ) -> None:
        """Set ``state`` + PKCE verifier + ``nonce`` in a signed cookie.

        Signed, and not merely set: without a signature, an attacker
        chooses the ``state`` on both sides and the flow's CSRF
        protection falls. Ten minutes of life, ``HttpOnly``,
        ``SameSite=lax`` — and ``lax`` rather than ``strict``, otherwise
        the browser does not send it back on the return from the
        provider, which is a cross-site navigation.
        """
        payload = f"{state}:{verifier}:{nonce}"
        signature = _crypto_sign(self._key(request), payload)
        response.set_cookie(
            self._cookie_name,
            f"{payload}.{signature}",
            max_age=_TRANSACTION_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=self._secure(request),
        )

    def _unseal(self, request: Any) -> tuple[str, str, str]:
        raw = request.cookies.get(self._cookie_name, "")
        if not raw or "." not in raw:
            raise OAuthError("transaction cookie missing — the link is direct or has expired")
        payload, signature = raw.rsplit(".", 1)
        if not _crypto_verify(self._key(request), payload, signature):
            raise OAuthError("transaction cookie was not signed by this application")
        parts = payload.split(":")
        if len(parts) != 3:
            raise OAuthError("malformed transaction cookie")
        return parts[0], parts[1], parts[2]

    def _redirect_uri(self, request: Any) -> str:
        """The callback's absolute URL.

        Derived from the request by default, overridable with
        ``redirect_uri=``: behind a proxy terminating TLS, ``base_url``
        may announce ``http`` while the provider will require the
        ``https`` registered with it.
        """
        if self.redirect_uri:
            return self.redirect_uri
        return str(request.base_url).rstrip("/") + self.callback_path


# ───────────────────────────────────────────────────────────────────────────
# OIDC
# ───────────────────────────────────────────────────────────────────────────


class OIDC(_Door):
    """Configure an OpenID Connect provider from its issuer metadata."""

    def __init__(
        self,
        *,
        name: str,
        issuer: str,
        client_id: str,
        client_secret: str,
        scope: str = "openid email profile",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=name,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            **kwargs,
        )
        self.issuer = issuer.rstrip("/")
        self._cache: dict[str, str] | None = None

    async def _endpoints(self) -> dict[str, str]:
        if self._cache is None:
            doc = await _fetch(f"{self.issuer}/.well-known/openid-configuration")
            try:
                self._cache = {
                    "authorize": doc["authorization_endpoint"],
                    "token": doc["token_endpoint"],
                    "userinfo": doc.get("userinfo_endpoint", ""),
                }
            except KeyError as exc:
                raise OAuthError(
                    f"{self.issuer} does not publish a complete OIDC "
                    f"configuration ({exc}). If the provider is not OIDC, "
                    "use oauth.OAuth2 with its three URLs."
                ) from None
        return self._cache

    async def _profile(self, tokens: dict[str, Any], nonce: str) -> OAuthProfile:
        raw_id = tokens.get("id_token", "")
        if not raw_id or raw_id.count(".") != 2:
            raise OAuthError("OIDC response does not contain a usable id_token")
        claims = _b64url_json(raw_id.split(".")[1])

        # What we verify, and why not the signature: the token comes
        # from the token endpoint, over TLS, in reply to OUR
        # authenticated POST — OIDC Core § 3.1.3.7 deems that sufficient.
        # What remain are the four checks the transport does not give.
        if str(claims.get("iss", "")).rstrip("/") != self.issuer:
            raise OAuthError("id_token was issued by a different issuer")
        aud = claims.get("aud", "")
        auds = aud if isinstance(aud, list) else [aud]
        if self.client_id not in auds:
            raise OAuthError("id_token was issued for a different client")
        if int(claims.get("exp", 0)) <= int(time.time()):
            raise OAuthError("id_token has expired")
        # ⚠️ The ``and claims.get("nonce")`` that used to be here made
        # the check OPTIONAL: a token WITHOUT a nonce passed, although we
        # had sent one. That is exactly the replay door the nonce exists
        # to close, and OIDC Core requires it the other way round ("if a
        # nonce was sent, its presence AND its value MUST be verified").
        # Found on 2026-08-24 by mutating the nonce's emission: the probe
        # stayed green.
        if nonce and not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
            raise OAuthError("nonce absent ou non concordant — rejeu possible.")

        subject = str(claims.get("sub", ""))
        if not subject:
            raise OAuthError("id_token does not contain a sub claim")
        return OAuthProfile(
            subject=subject,
            email=str(claims.get("email", "")),
            name=str(claims.get("name", "")),
            raw=claims,
            token=str(tokens.get("access_token", "")),
        )


# ───────────────────────────────────────────────────────────────────────────
# OAuth2 nu
# ───────────────────────────────────────────────────────────────────────────


class OAuth2(_Door):
    """Configure an OAuth 2 provider from explicit endpoint URLs."""

    def __init__(
        self,
        *,
        name: str,
        authorize: str,
        token: str,
        userinfo: str,
        client_id: str,
        client_secret: str,
        subject: str = "id",
        email_field: str = "email",
        name_field: str = "name",
        scope: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            name=name,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            **kwargs,
        )
        self._urls = {"authorize": authorize, "token": token, "userinfo": userinfo}
        self.subject_field = subject
        self.email_field = email_field
        self.name_field = name_field

    async def _endpoints(self) -> dict[str, str]:
        return self._urls

    async def _profile(self, tokens: dict[str, Any], nonce: str) -> OAuthProfile:
        access = str(tokens.get("access_token", ""))
        if not access:
            raise OAuthError("response does not contain an access_token")
        raw = await _fetch(
            self._urls["userinfo"],
            headers={"Authorization": f"Bearer {access}", "User-Agent": "bretzel"},
        )
        subject = str(raw.get(self.subject_field, "") or "")
        if not subject:
            raise OAuthError(
                f"the profile does not carry {self.subject_field!r} — "
                "check subject= against the provider's documentation."
            )
        return OAuthProfile(
            subject=subject,
            email=str(raw.get(self.email_field, "") or ""),
            name=str(raw.get(self.name_field, "") or ""),
            raw=raw,
            token=access,
        )
