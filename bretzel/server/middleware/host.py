"""Host check — answer only the names this app is reached by.

A browser sends the name it believes it is talking to in ``Host``. An app
that answers ANY name can be read by a page from another site : the
attacker points its own domain at the victim's machine (DNS rebinding),
and the browser, believing both are the attacker's origin, lets that page
read the answers. Unchecked, an app on a laptop, at ``localhost``, answers
a request addressed to ``evil.example`` with the whole page and its CSRF
token.

The rule is Django's ``ALLOWED_HOSTS`` : in dev mode, with nothing
declared, only the local names are answered (:data:`DEV_HOSTS`) ; in
either mode, ``Bretzel(trusted_hosts=[…])`` names the others. A refused
request gets a 400 that says what to declare.

Why not Starlette's ``TrustedHostMiddleware`` : it reads the host with
``split(":")``, so ``[::1]:8000`` became ``[`` — the IPv6 loopback was
refused — and its answer, « Invalid host header », does not say what to
change.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send

#: The names a dev server answers with nothing declared : the machine
#: itself, under every spelling a browser uses, and ``testserver``, the
#: name Starlette's test client sends (Django's test runner adds it the
#: same way). A ``*.`` entry matches the domain and its subdomains.
DEV_HOSTS: tuple[str, ...] = ("localhost", "*.localhost", "127.0.0.1", "[::1]", "testserver")


def host_name(header: str) -> str:
    """The name in a ``Host`` header, without its port, lowercased —
    ``[::1]:8000`` → ``[::1]``, ``Example.org:443`` → ``example.org``."""
    header = header.strip().lower()
    if header.startswith("["):
        end = header.find("]")
        return header[: end + 1] if end != -1 else header
    return header.split(":", 1)[0]


def is_allowed(name: str, allowed: tuple[str, ...]) -> bool:
    for entry in allowed:
        entry = entry.lower()
        if entry == "*" or entry == name:
            return True
        if entry.startswith("*.") and (name == entry[2:] or name.endswith(entry[1:])):
            return True
    return False


class HostMiddleware:
    """Refuse a request addressed to a name the app does not answer."""

    def __init__(self, app: ASGIApp, *, allowed: tuple[str, ...]) -> None:
        self.app = app
        self.allowed = tuple(allowed)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        raw = dict(scope.get("headers") or ()).get(b"host", b"").decode("latin-1")
        name = host_name(raw)
        if is_allowed(name, self.allowed):
            await self.app(scope, receive, send)
            return
        body = (
            f"Host {name!r} is not one this app answers. Reached by this name on "
            f"purpose? Add it : Bretzel(trusted_hosts=[{name!r}, …]). "
            f"Answered now : {', '.join(self.allowed)}."
        ).encode()
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await send({
            "type": "http.response.start",
            "status": 400,
            "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                        (b"content-length", str(len(body)).encode("ascii"))],
        })
        await send({"type": "http.response.body", "body": body})
