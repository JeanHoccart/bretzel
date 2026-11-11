"""The session a test client acts in.

An action's signature is bound to the session it was rendered for
(``bretzel.server.handlers.sign_action``). A test that signs by hand signs
for the session its client will send: the cookie it holds, or one set now
when it has none yet — the session middleware adopts it.

The cookie carries the id SIGNED (``bretzel.server.auth.session_cookie``,
2026-11-06): this returns the id, and a cookie set here is signed with
the client's app key, as the server would have.
"""

from __future__ import annotations

import secrets

from starlette.testclient import TestClient

from bretzel.server.auth import COOKIE_SESSION, session_cookie, session_of_cookie


def _key_of(client: TestClient) -> bytes:
    app = client.app
    config = getattr(app, "config", None) or getattr(getattr(app, "bretzel", None), "config", None)
    return getattr(config, "_session_key", b"") or b""


def session_of(client: TestClient) -> str:
    key = _key_of(client)
    held = session_of_cookie(client.cookies.get(COOKIE_SESSION), key)
    if held:
        return held
    session = secrets.token_hex(16)
    client.cookies.set(COOKIE_SESSION, session_cookie(session, key))
    return session
