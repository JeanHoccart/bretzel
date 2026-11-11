"""``base_path`` — an app that does not live at the root of its site.

``Bretzel(base_path="/radar")``, and nothing else in the app changes: its
``@page("/strategies")`` and its ``ui.link(href="/decisions")`` are still
written from the app's own root. Two places do the work:

- **on the way in** (``Bretzel.__call__``, :func:`strip`): the prefix is taken
  off the request's path, if it is there. So everything behind — routes,
  middlewares, guards, ``request.url.path`` — sees the app's own paths, and
  it makes no difference whether the proxy in front removed the prefix or
  kept it;
- **on the way out** (:func:`with_base`): every address the framework writes
  gets the prefix — the attributes of the HTML (``serialize_attrs``), the
  document's assets, ``redirect()``, the manifest, the runtime's endpoints.

The prefix travels in a ``ContextVar``, set for the duration of the request:
several apps can share a process (the tests do), and an app without a
``base_path`` never enters this path — its HTML is the same to the byte.

An address that is NOT a path of this site is left alone: a full URL
(``https://…``) is how an app points at another one, including a sibling
under the same host.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Final
from urllib.parse import urlsplit

_BASE: ContextVar[str] = ContextVar("bretzel_base_path", default="")

#: The names of this machine, one and the same host: a page opened on
#: ``localhost`` may point at ``127.0.0.1``.
_LOOPBACK: Final[frozenset[str]] = frozenset({"localhost", "127.0.0.1", "::1"})

#: The attributes that hold an address the browser will follow. Wider than
#: ``escape.URL_ATTRS``, which is about what could carry a script: the htmx
#: verbs are addresses too, and ``data`` / ``cite`` are not navigation.
BASED_ATTRS: Final[frozenset[str]] = frozenset({
    "href", "src", "action", "formaction", "poster",
    "hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete", "hx-push-url",
})


def normalize(value: str | None) -> str:
    """``"/radar"``, or ``""`` for an app at the root. Refuses the rest."""
    if value is None or value in ("", "/"):
        return ""
    if (not value.startswith("/") or value.startswith("//") or value.endswith("/")
            or any(ch in value for ch in "?#\\ ")):
        raise ValueError(
            f"base_path={value!r}: expected a path like \"/radar\" — a leading "
            "slash, no trailing slash, no query.")
    return value


def activate(base: str) -> Token[str]:
    return _BASE.set(base)


def deactivate(token: Token[str]) -> None:
    _BASE.reset(token)


def current() -> str:
    """The prefix of the app serving this request, ``""`` if none."""
    return _BASE.get()


def with_base(url: str, base: str | None = None) -> str:
    """``url`` as the browser must ask for it. Only a path of this site
    changes: a full URL, ``//host``, ``#anchor`` or ``data:`` stay as they are."""
    prefix = current() if base is None else base
    if not prefix or not url.startswith("/") or url.startswith("//"):
        return url
    return prefix + url


def without_base(path: str, base: str | None = None) -> str:
    """A path the browser shows, as the app knows it."""
    prefix = current() if base is None else base
    if prefix and (path == prefix or path.startswith(prefix + "/")):
        return path[len(prefix):] or "/"
    return path


def strip(scope: dict[str, Any], base: str) -> dict[str, Any]:
    """The ASGI scope with the prefix off its path, when it is there."""
    path = scope.get("path", "")
    if path != base and not path.startswith(base + "/"):
        return scope
    stripped = dict(scope)
    stripped["path"] = path[len(base):] or "/"
    raw = scope.get("raw_path")
    if raw:
        stripped["raw_path"] = raw[len(base.encode()):] or b"/"
    return stripped


def same_host(url: str, request: Any) -> bool:
    """Is ``url`` a full address on the host this request came to?

    The port does not count: the same machine, the same people — and a
    cookie ignores it too. A backslash or a ``user@`` is refused, because a
    browser and ``urlsplit`` do not read those alike: ``https://evil.com\\@good``
    is ``good`` to one and ``evil.com`` to the other.
    """
    if "\\" in url or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        return False
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or not host or "@" in parts.netloc:
        return False
    here = getattr(getattr(request, "url", None), "hostname", None)
    if not here:
        return False
    host, here = host.lower(), here.lower()
    return host == here or (host in _LOOPBACK and here in _LOOPBACK)
