"""features/access — the TWO halves of identity, in a single file.

This is the file this demo exists to show: `@auth.source` says where an
identity may come from, `@auth.door` says how one gets in, and both end
up in the same place — ``auth.user_id()``, hence ``UserState``, hence all
the rest of the app without a single `if`.

It does NOT import ``main``: both decorators are free, exactly like
``@page`` (``app-structure.md`` § 9). It is ``main.include(...)`` that
picks the marks up.
"""

from __future__ import annotations

from typing import Any

from bretzel import Feature, auth, oauth, redirect
from bretzel.server import auth

from examples.auth.core.domain import (
    ALLOWED_DOMAIN,
    API_TOKENS,
    LOGIN_PATH,
    PROXY_HEADER,
    by_email,
    by_id,
    oauth2_settings,
    oidc_settings,
    trusted_proxy,
    upsert_by_email,
)

# ── Who is this request? ───────────────────────────────────────────────────


@auth.source
def from_api_token(request: object) -> str | None:
    """A machine identity, carried by the header on every call.

    No cookie, no session: the bearer IS the proof, and it is re-checked
    at every request. It is the second of the two families — the other
    (the signed cookie) is played before this one by the framework.

    A real app would verify a JWT signature here rather than a dict. What
    would not change: the function is **synchronous** (it runs on every
    request), and returns an identifier or ``None``.
    """
    header = request.headers.get("authorization", "")  # type: ignore[attr-defined]
    if not header.lower().startswith("bearer "):
        return None
    return API_TOKENS.get(header.split(" ", 1)[1].strip())


@auth.source
def from_trusted_proxy(request: object) -> str | None:
    """The identity set by an SSO proxy — oauth2-proxy, IAP, Access.

    The fourth way in, and **the only one with no screen**: authentication
    happened before arriving here, the reverse proxy attests it with a
    header, and the app only has to join its table.

    ⚠️ **It is off by default, and that is the point.** A header is
    declarative: anyone can send it. It is worth something ONLY behind a
    proxy that systematically overwrites it, and an app that turns it on
    without that opens a door to whoever can type `curl -H`. Hence the
    explicit switch (``BZ_TRUST_PROXY_HEADER=1``) rather than a default:
    that way round, forgetting closes instead of opening.
    """
    if not trusted_proxy():
        return None
    email = request.headers.get(PROXY_HEADER, "")  # type: ignore[attr-defined]
    user = by_email(email) if email else None
    return user["id"] if user else None


# ── Comment devient-on connu ? ─────────────────────────────────────────────


def on_oauth_user(profile: oauth.OAuthProfile) -> str | None:
    """The decision to accept, and where the door becomes a row.

    ``None`` refuses. It is the only filter that exists between "this
    person has a Google account" and "this person comes into my house" —
    without it, a door stands open to the whole planet.
    """
    if not profile.email or not profile.email.endswith(ALLOWED_DOMAIN):
        return None
    return upsert_by_email(profile.email, profile.name)["id"]


def configured_doors() -> list[Any]:
    """The doors the environment describes — zero, one, or two.

    Built rather than hard-coded because a demo cannot carry secrets. A
    real app's code simply writes the decorator above its function.
    """
    doors: list[object] = []
    oidc = oidc_settings()
    if oidc:
        doors.append(oauth.OIDC(on_denied=LOGIN_PATH, **oidc))
    plain = oauth2_settings()
    if plain:
        doors.append(oauth.OAuth2(on_denied=LOGIN_PATH, **plain))
    return doors


#: The names of the mounted doors, so the login page knows which buttons
#: to show. An empty list is not a failure: the demo runs on password
#: alone.
DOORS = configured_doors()

for porte in DOORS:
    # ``@auth.door(door)`` stacks — two doors can end on the same
    # function, and that is the case here. The decorator MARKS in place
    # and returns the same object: no reassignment, it would suggest a
    # wrapper.
    auth.door(porte)(on_oauth_user)


# ── The rest, which now knows nothing but a ``user_id`` ────────────────────


def current_user() -> dict[str, str] | None:
    """The signed-in person's profile, whichever door they came through.

    ``auth.user_id()`` returns the same string whether the sign-in came
    from the form, an OAuth door or a machine token. That is the whole
    point of the arrangement: beyond this line, the app no longer knows
    how you got in, and does not have to.
    """
    return by_id(auth.user_id())


def sign_out() -> None:
    auth.logout()
    redirect(LOGIN_PATH)


feature = Feature(
    name="access",
    kind="logic",
    provides=[from_api_token, from_trusted_proxy, on_oauth_user,
              current_user, sign_out, configured_doors],
)
