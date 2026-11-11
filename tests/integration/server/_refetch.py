"""The refetch URL a page would have given this client.

Since 2026-10-27 the refetch route serves a zone only to the session it
was rendered for: the URL carries ``?sig=`` signed for that session
(``bretzel.server.handlers.sign_refetch``). A test that builds the URL by
hand signs it the same way, from the client's session cookie.
"""

from __future__ import annotations

from typing import Any

from starlette.testclient import TestClient

from bretzel.runtime import ROUTE_REFETCH
from bretzel.runtime.protocol import REFETCH_SIG_PARAM
from bretzel.server.handlers import sign_refetch
from tests._session import session_of


def refetch_url(app: Any, client: TestClient, zone: str) -> str:
    sig = sign_refetch(app.config._action_key, zone, session_of(client))
    return f"{ROUTE_REFETCH}/{zone}?{REFETCH_SIG_PARAM}={sig}"
