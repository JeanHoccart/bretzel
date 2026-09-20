"""Auth — the four ways in, a single identity out.

Run: ``py -m examples.auth.main`` (port 8012).

What this app puts under constraint, and that no other exercised:

1. **the form** — the app verifies, ``auth.login(user_id)`` transports;
2. **an OAuth / OIDC door** — ``@auth.door``, configured by the
   environment, ending on the same ``auth.login``;
3. **a machine token** — ``@auth.source``, with no cookie and no session,
   re-checked at every request;
4. **an SSO proxy header** — ``@auth.source`` too, off by default.

All four end at the same ``auth.user_id()``, hence the same
``UserState``. The last two have no screen: they answer on ``/me``, in
plain text ::

    curl.exe -s -H "Authorization: Bearer demo-token" http://127.0.0.1:8012/me

Turn everything on in one command: ``py -m examples.auth.demo``.

⚠️ ``secret_key`` is in clear here because this is a local demo. A real
app reads it from its environment — it is what derives the key that signs
the identity cookie.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from bretzel import Bretzel
from bretzel.runtime import is_public_asset_path
from bretzel.server import action_path, auth, redirect_response

from examples.auth.core.domain import LOGIN_PATH, PROXY_HEADER, by_id
from examples.auth.features import access, home, login

app = Bretzel(
    title="Bretzel · Auth",
    secret_key="dev-auth-secret-change-me",
    mode="dev",
)

@app.middleware
async def require_login(request, call_next):
    """The guard. Written first, so the outermost.

    ``auth.user_id(request)`` — with the request — because at this level
    neither the render context nor ``request.state`` exists yet. It is
    what plays the full chain: the signed cookie, then the app's
    ``@auth.source``. Without that, a token call would be sent back to
    the login page.

    ``redirect_response`` and not ``redirect``: the first decides between
    a real 302 (navigation) and an ``HX-Redirect`` (bridge action); the
    second raises outside a render context.

    ⚠️ **``is_public_asset_path`` and not merely membership of
    ``PUBLIC``.** ``app.public_paths`` holds a route PATTERN —
    ``/_bretzel/vendor/{filename}`` — which equals no real path, so
    equality alone refuses the three third-party scripts. The guard then
    redirects them to the login page, and the browser receives HTML where
    it expects JavaScript: ``Unexpected token '<'`` on a loop, htmx never
    loaded, no POST at all any more. The app looks dead without a single
    server error being emitted.

    It shows **only if ``.bretzel/vendor/`` exists**: with no vendored
    cache, the ``<script>`` tags point at the CDNs and this route is
    never requested. So the symptom appears the day somebody runs the
    vendoring, not the day the guard is written.
    """
    if (request.url.path in PUBLIC
            or is_public_asset_path(request.url.path)
            or auth.user_id(request)):
        return await call_next(request)
    return redirect_response(request, LOGIN_PATH)


@app.fastapi.get("/me")
async def who_am_i(request: Request) -> PlainTextResponse:
    """"Who am I?", in TEXT — the answer for the two screen-less ways.

    A machine token and a proxy header open no page: they are tried at
    the terminal, and a real page's HTML is unreadable there. This route
    returns three lines, so the ``curl`` command finally shows something.

    It is BEHIND the guard, on purpose: with no identity you get the
    redirect to ``/login``, which proves the guard is what read the token
    — and not that the route would be open.

    ⚠️ A raw route on ``app.fastapi`` (public escape hatch): the framework
    has no decorator for a routable that does not return HTML. It is
    noted in ``.claude/work/todo.md`` (@download), and it is beyond this
    demo.

    ``request.state.user_id`` is what ``AuthMiddleware`` resolved — the
    same value ``auth.user_id()`` would see at render time.
    """
    user_id = getattr(request.state, "user_id", None)
    user = by_id(user_id)
    door = "session cookie (browser)"
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        door = "machine token (Authorization: Bearer)"
    elif request.headers.get(PROXY_HEADER):
        door = f"proxy header ({PROXY_HEADER})"
    address = user["email"] if user else "—"
    return PlainTextResponse(
        "\n".join(
            [
                f"user_id      : {user_id}",
                f"address      : {address}",
                f"recognised by: {door}",
                "",
            ]
        )
    )


app.include(access, login, home)

#: What the guard lets through. ``app.public_paths`` carries the runtime's
#: assets AND the two routes of every mounted door — so the app has
#: nothing of the framework's to enumerate, and a door added tomorrow
#: obliges nothing.
#:
#: Computed AFTER ``include``: that is what makes the doors known. The
#: middleware reads this name at call time, not at decoration time, so the
#: writing order above has no effect.
PUBLIC = {
    LOGIN_PATH,
    # ⚠️ The login form POSTs an action, and a closed-by-default guard
    # blocks it like the rest. The symptom looks like nothing: htmx
    # follows the redirect transparently, /login's HTML comes back, and
    # the button seems dead — no error anywhere.
    action_path(login.sign_in),
    *app.public_paths,
}


if __name__ == "__main__":
    app.run(port=8012, reload=True)
