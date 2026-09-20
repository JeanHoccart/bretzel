"""``@auth.source`` and ``@auth.door`` — the two halves of identity.

They answer two distinct questions, and it is that split that holds the
whole subject:

- **``@auth.source`` — "who is this request?"** A read, played on EVERY
  request. Bretzel's signed cookie is one of them, always tried first; a
  bearer JWT, an API key or a header set by an SSO proxy are others,
  added behind it.
- **``@auth.door`` — "how does one become known?"** A door, walked
  through ONCE. It always ends in :func:`bretzel.auth.login`, that is to
  say in the cookie: a door does not replace the read, it feeds it.

Both remain **free** decorators — ``from bretzel import auth`` — and not
methods of the app. That is not a style detail: a feature writing
``@app.auth_source`` would have to import the instance, which
``app-structure.md`` § 9 explicitly forbids ("``from myapp.main import
app`` in a feature. Never."). Like ``@page`` and ``@error_page``, these
decorators only **mark**; ``app.include(...)`` picks the mark up at
composition time. Charter anti-rule 4 — "no registration at import time"
— is thus held by construction.

"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

#: The mark of an identity source. Read by ``Bretzel._register_declaration``.
MARK_SOURCE = "_bz_auth_source"

#: A door's mark. It carries the door object itself, not a boolean — the
#: decorated function only makes sense attached to ITS door.
MARK_DOOR = "_bz_auth_door"


def source(fn: Callable[[Any], str | None]) -> Callable[[Any], str | None]:
    """Declare an identity source checked after the signed cookie.

    ::

        from bretzel import auth

        @auth.source
        def from_bearer(request) -> str | None:
            token = request.headers.get("authorization", "")
            return subject_of(token) if token.startswith("Bearer ") else None

    The function returns the identifier, or ``None`` for "I do not know"
    — in which case the next source is tried. It never returns a boolean:
    a guard that logs or authorises by role needs the name, and a boolean
    would have forced it to read again.

    **Synchronous, and that is a contract.** This read runs on every
    request and from a user middleware, where nothing is set up yet; a
    source needing the network (refreshing a JWKS) does it outside the
    request and serves a cache. An ``async def`` is refused here rather
    than being silently awaited — that would be one ``await`` per request
    nobody asked for.
    """
    if inspect.iscoroutinefunction(fn):
        raise TypeError(
            "@auth.source expects a synchronous function — it is called "
            f"on every request, including from a middleware; {fn.__name__} "
            "is a coroutine. Make the network call outside the request and "
            "serve a cache."
        )
    if not callable(fn):
        raise TypeError(f"@auth.source expects a callable; got {type(fn).__name__}")
    setattr(fn, MARK_SOURCE, True)
    return fn


def door(door: Any) -> Callable[[Callable[..., str | None]], Callable[..., str | None]]:
    """Declare a login provider and how its profile is handled.

    ::

        from bretzel import auth, oauth

        @auth.door(oauth.OIDC(name="google", issuer="https://accounts.google.com",
                              client_id=..., client_secret=...))
        def google_user(profile) -> str | None:
            if not profile.email.endswith("@macorp.fr"):
                return None
            return str(users.upsert(email=profile.email).id)

    The decorated function returns **your** identifier — your table's,
    not the provider's — or ``None`` to refuse. It is mandatory, and that
    is a security choice: without it, the default would be "anybody with
    an account at the provider gets in", a default-open that never shows
    in review because the page renders perfectly.

    Stacking several ``@auth.door`` on the same function is legitimate —
    two doors ending at the same user table.
    """
    if not hasattr(door, "mount"):
        raise TypeError(
            "@auth.door expects a door (oauth.OIDC / oauth.OAuth2); got "
            f"{type(door).__name__}."
        )

    def decorate(fn: Callable[..., str | None]) -> Callable[..., str | None]:
        if inspect.iscoroutinefunction(fn):
            raise TypeError(
                "@auth.door expects a synchronous function: it runs in "
                "the callback, after the code exchange, and has nothing to "
                f"await; {fn.__name__} is a coroutine."
            )
        doors: list[Any] = list(getattr(fn, MARK_DOOR, ()))
        doors.append(door)
        setattr(fn, MARK_DOOR, tuple(doors))
        return fn

    return decorate
