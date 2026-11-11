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

import functools
import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from starlette.responses import RedirectResponse, Response
from starlette.routing import compile_path

from bretzel.core.base_path import same_host, with_base, without_base
from bretzel.core.errors import BretzelError

__all__ = [
    "PageRedirectError",
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


#: The header that makes htmx NAVIGATE without reloading the document:
#: a GET of ``path`` swapped into ``target``, then a history entry. It is
#: what a boosted link does, triggered by a response instead of a click.
_HX_LOCATION = "HX-Location"


def _validate(url: str, request: Any = None, *, off_origin: bool = False) -> None:
    """Refuse a URL that would split the header — and, unless the framework
    itself leaves the origin (an OAuth door, :func:`_leave_origin`), one
    that is not a path of this site."""
    if not isinstance(url, str) or not url:
        raise TypeError("redirect() expects a non-empty URL")
    if any(ch in url for ch in _HEADER_UNSAFE):
        raise ValueError(
            "The redirect URL contains a control character (CR / LF / "
            "NUL) — refused: inside a header, it would allow others to "
            "be written."
        )
    if not off_origin and not _is_local_path(url) and not same_host(url, request):
        raise ValueError(
            f"redirect() takes a path of this site (\"/invoices/42\") or a "
            f"full address on this host, not {url!r}. A target often comes from the user (``?next=``): "
            f"\"javascript:…\" would run script in your origin, "
            f"\"//host\" or \"https://…\" would send your users elsewhere."
        )


def _is_local_path(url: str) -> bool:
    r"""Is ``url`` a path of this origin — ``/`` then anything but a second
    ``/`` or a ``\``?

    Each refusal is a way out that a prefix test lets through: ``//host``
    is a URL without a scheme, a browser reads ``/\host`` as ``//host``,
    and it DROPS tabs and newlines before parsing, so ``/<tab>/host``
    becomes ``//host`` — any control character is refused.
    """
    return (
        url.startswith("/")
        and url[1:2] not in ("/", "\\")
        and not any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url)
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
    **nothing sets it to ``True``** in the framework: the field is only
    reserved.
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
    _validate(url, request)
    return _respond(request, url, status_code)


def _leave_origin(request: Any, url: str) -> Response:
    """:func:`redirect_response` to ANOTHER origin — for the framework only
    (an OAuth door sending the browser to its provider). Its URL comes from
    the provider's configuration, never from a request."""
    _validate(url, off_origin=True)
    return _respond(request, url, 302)


def _respond(request: Any, url: str, status_code: int) -> Response:
    url = with_base(url)
    if response_is_read_by_htmx(request):
        # Empty body: htmx reads the header and navigates, it swaps
        # nothing.
        return Response(status_code=200, headers={_HX_REDIRECT: url})
    return RedirectResponse(url, status_code=status_code)


class PageRedirectError(BretzelError):
    """:func:`redirect` called while a page renders for an ordinary
    navigation. The page route answers it with a real redirect
    (``routing/pages.py``); it only surfaces where no page is rendering —
    an API route, a ``@download`` —, with the way out in its message."""

    def __init__(self, url: str) -> None:
        super().__init__(
            f"redirect({url!r}) outside a page render and outside htmx: there "
            f"is no response here for it to turn into a redirect. From a "
            f"middleware or a FastAPI route, return redirect_response(request, "
            f"url)."
        )
        self.url = url


def redirect(url: str) -> None:
    """Navigate the browser to ``url``.

    After a click (an action, a refresh, a boosted partial navigation):
    like a link — when the displayed page and ``url``'s page share a
    layout, only that layout's outlet changes, the sidebar, its scroll and
    the client state stay mounted (``HX-Location``); otherwise the browser
    loads the whole document (``HX-Redirect``).

    While a page renders for an ordinary navigation — a typed address, a
    reload — it stops the render, and the browser gets a real ``307`` to
    ``url``: an address that only leads elsewhere is a page ::

        @page("/")
        def home() -> None:
            redirect("/strategies")

    ``url`` is a path of this site (:func:`_is_local_path`), or a full
    address on this same host — a sibling app, on another port or under
    another ``base_path``. A target often comes from the user: another host
    is refused.
    """
    from bretzel.render.context import current_context

    ctx = current_context()
    _validate(url, ctx.request)
    if not response_is_read_by_htmx(ctx.request):
        raise PageRedirectError(url)
    outlet = _shared_outlet(ctx.app, ctx.request, url)
    if outlet is None:
        ctx.set_header(_HX_REDIRECT, with_base(url))
        return
    ctx.set_header(_HX_LOCATION, json.dumps({
        "path": with_base(url),
        "target": f"#{outlet}",
        "swap": "morph:innerHTML",
    }))


@functools.lru_cache(maxsize=512)
def _route_pattern(path: str) -> re.Pattern[str]:
    """The regex Starlette itself matches ``@page(path)`` with."""
    return compile_path(path)[0]


def _layout_chain_of(app: Any, path: str) -> list[Callable[..., Any]] | None:
    """The layout chain of the page serving ``path``, outermost first.

    ``None`` when no page matches: the caller then has nothing to compare
    and falls back to a full load.
    """
    from bretzel.render.pipeline import (  # casse un cycle : render → server
        _resolve_layout_chain,
    )

    for fn in getattr(app, "_pages", ()):
        meta = getattr(fn, "_bz_page", None)
        if meta is not None and _route_pattern(meta.path).match(path):
            return _resolve_layout_chain(meta.layout)
    return None


def _shared_outlet(app: Any, request: Any, url: str) -> str | None:
    """The outlet both the displayed page and ``url``'s page render into.

    It is the answer to "which part of the screen must change": the
    innermost layout the two pages have in common stays mounted, and the
    target page renders into its outlet — exactly what a sidebar link
    does (``components/navigation/_wiring.py``), and exactly what
    ``server/routing/pages.py`` recognises in ``HX-Target`` to render the
    page without the layouts already in the browser.

    ``None`` — hence a full load — whenever that cannot be known for
    sure: another origin, an unknown displayed page (htmx sends it in
    ``HX-Current-URL``), a path no ``@page`` serves, or two pages that
    share no layout. Guessing wrong would swap a whole document into a
    ``<main>``; reloading is merely slower.
    """
    target = urlsplit(url)
    if target.scheme or target.netloc or not target.path.startswith("/"):
        return None
    headers = getattr(request, "headers", None)
    current = headers.get("HX-Current-URL") if headers is not None else None
    if not current:
        return None
    # A mounted app sees its paths prefixed; the ``@page`` patterns are not.
    root = (getattr(request, "scope", None) or {}).get("root_path", "")

    def local(path: str) -> str:
        if root and path.startswith(root):
            return path[len(root):] or "/"
        return path

    here = _layout_chain_of(app, without_base(local(urlsplit(current).path)))
    there = _layout_chain_of(app, local(target.path))
    if not here or not there:
        return None
    shared = None
    for mine, theirs in zip(here, there, strict=False):
        if mine is not theirs:
            break
        shared = mine
    if shared is None:
        return None
    from bretzel.runtime.protocol import outlet_id_for

    return outlet_id_for(shared.__name__)


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
