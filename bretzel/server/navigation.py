"""Sending the browser elsewhere — from a handler or from a middleware.

Why a module, and why this one
------------------------------
``server/`` gives each callable helper its named module: ``auth.py``,
``idempotency.py``. ``redirect`` was the exception and shared
``errors.py`` — whose docstring had had to widen into "a handler's
non-nominal exits" to accommodate it. And a redirect after a successful
sign-up is the **nominal** exit: it is the function's central use case.
The file name said the opposite of what the code does.

The two audiences, and why both are needed
------------------------------------------
A Bretzel app sends the browser elsewhere from **two** places, and they
do not have the same means:

- **a handler** — it has a :class:`RenderContext`, so :func:`redirect` is
  enough for it: it sets the header on the response in progress;
- **a user middleware** — it has none. It is mounted the OUTERMOST
  (``lifecycle.py``: "user middlewares last so they wrap everything
  above"), so on the inbound it runs BEFORE
  ``RenderContextMiddleware``: ``current_context()`` raises. That is
  where the auth guard lives ("not signed in → /login"), that is to say
  the most common redirect case of a real app.

Without this module, that second audience had nothing to call — only
something to copy. And what it would have copied is the subject's
non-obvious trap: **a middleware sees two natures of request.**

On a page GET, a real ``302`` is needed. On an action POST coming from
the bridge, a ``200`` + ``HX-Redirect`` is needed: a 302 would be
followed transparently by ``fetch``, and ``/login``'s HTML would end up
swapped **into the button** that triggered the action. Every user would
rediscover that while debugging.

:func:`redirect_response` is therefore the reusable unit — "send this
browser elsewhere, given the nature of THIS request" — and
:func:`redirect` becomes its thin context-bound wrapper. A single
302-vs-200 decision, written once.
"""

from __future__ import annotations

from typing import Any

from starlette.responses import RedirectResponse, Response

from bretzel.core.errors import BretzelError

__all__ = [
    "redirect",
    "redirect_response",
    "reload",
    "push_url",
    "response_is_read_by_htmx",
]

#: Characters which, in a header value, cut the header and let the
#: following ones be written (response splitting). A redirect URL often
#: comes from user data (``?next=``), so we refuse rather than trust the
#: layer below.
_HEADER_UNSAFE = ("\r", "\n", "\0")

#: The header htmx handles natively (``render/shell.py`` loads htmx in
#: full). So there is NO Bretzel runtime code behind this whole module.
_HX_REDIRECT = "HX-Redirect"

#: The THIRD member of the family — the one that changes the address
#: WITHOUT navigating. ``HX-Redirect`` goes elsewhere, ``HX-Refresh``
#: reloads, ``HX-Push-Url`` merely stacks a history entry on the page one
#: is already looking at.
#:
#: That is what was missing for a view to have an address: the content
#: arrives through the action's swap, the address through this header,
#: and the back button asks the server for the URL again (htmx's cache is
#: at zero, cf. ``render/shell.py``), which reads it back and renders the
#: same view.
_HX_PUSH_URL = "HX-Push-Url"


def _validate(url: str) -> None:
    if not isinstance(url, str) or not url:
        raise TypeError("redirect() expects a non-empty URL")
    if any(ch in url for ch in _HEADER_UNSAFE):
        raise ValueError(
            "The redirect URL contains a control character (CR / LF / "
            "NUL) — refused: inside a header, it would allow others to "
            "be written."
        )


def response_is_read_by_htmx(request: Any) -> bool:
    """``True`` when htmx will handle the headers of the response to ``request``.

    The marker is the ``HX-Request`` header, which htmx sets on every
    request it issues. Compared to ``"true"`` and not to ``None``: that
    is the value htmx sends, and it is already the reading
    ``server/routing/pages.py`` makes.

    The ``getattr`` on ``.headers`` follows ``auth.request_scheme``'s
    convention: the unit tests' low-level stubs pass ``request=object()``,
    so a missing ``headers`` is the only real case to absorb. A request
    with no headers is treated as non-htmx: the safe default is the one
    that speaks.

    ⚠️ ``ctx.is_action`` would look like a better proxy. It is not, for
    two reasons: it would miss partial nav and refresh, and above all
    **nothing sets it to ``True``** in the framework. That reserved field
    is tracked in ``.claude/work/todo.md``.
    """
    headers = getattr(request, "headers", None)
    return headers is not None and headers.get("HX-Request") == "true"


def redirect_response(request: Any, url: str, *, status_code: int = 302) -> Response:
    """A response sending ``request`` to ``url``, whatever its nature.

    **It is the middleware's primitive.** It touches no render context,
    so it is callable where ``redirect()`` is not — typically an auth
    guard ::

        from bretzel.server.navigation import redirect_response

        @app.middleware
        async def require_login(request, call_next):
            if request.url.path not in PUBLIC and not signed_in(request):
                return redirect_response(request, "/login")
            return await call_next(request)

    It settles the only question that matters here, and once and for
    all: **who is going to read this response?**

    - an ordinary navigation → a real ``302``, which the browser
      follows;
    - a request issued by htmx (action, refresh, boosted partial nav) →
      a ``200`` + ``HX-Redirect``. A 302 there would be followed
      **transparently** by ``fetch``, and the target's HTML would end up
      swapped into the element that triggered the request — the button,
      the table row. It is the bug everyone rediscovers while debugging,
      and this function's reason to exist.

    ``status_code`` applies only to the browser branch (303 after a bare
    form POST, 307/308 to preserve the method).
    """
    _validate(url)
    if response_is_read_by_htmx(request):
        # Empty body: htmx reads the header and navigates, it swaps
        # nothing.
        return Response(status_code=200, headers={_HX_REDIRECT: url})
    return RedirectResponse(url, status_code=status_code)


def redirect(url: str) -> None:
    """Navigate the browser to ``url`` after the current request."""
    from bretzel.render.context import current_context

    _validate(url)
    ctx = current_context()
    if not response_is_read_by_htmx(ctx.request):
        raise BretzelError(
            "redirect() only has an effect on a response read by htmx "
            "(an action, a refresh, or a boosted partial navigation) — "
            "the current request is a classic page render, where the "
            "HX-Redirect header would be silently ignored. From a "
            "middleware, call redirect_response(request, url): it has no "
            "render context and can answer a real 302. To refuse the page "
            "rather than redirect, abort(401) + @error_page(401)."
        )
    ctx.set_header(_HX_REDIRECT, url)


def push_url(url: str) -> None:
    """Change the displayed URL without navigating or reloading the page."""
    from bretzel.render.context import current_context

    _validate(url)
    ctx = current_context()
    if not response_is_read_by_htmx(ctx.request):
        raise BretzelError(
            "push_url() only has an effect on a response read by htmx — "
            "the current request is a classic page render, where the "
            "header would be silently ignored. On a page render, the "
            "address is ALREADY the one the browser displays: there is "
            "nothing to push."
        )
    ctx.set_header(_HX_PUSH_URL, url)


#: The header htmx reloads the displayed page with. THIRD member of
#: ``_HX_REDIRECT``'s family: the three ways of acting on the address bar
#: from a response — go elsewhere, reload, or rename without moving — and
#: this module owns them all, as its header claims.
_HX_REFRESH = "HX-Refresh"


def reload() -> None:
    """Reload the page displayed by the browser after the current request."""
    from bretzel.render.context import current_context

    ctx = current_context()
    if not response_is_read_by_htmx(ctx.request):
        raise BretzelError(
            "reload() only has an effect on a response read by htmx "
            "(an action, a refresh, or a boosted partial navigation) — "
            "the current request is a classic page render, where the "
            "HX-Refresh header would be silently ignored."
        )
    ctx.set_header(_HX_REFRESH, "true")
