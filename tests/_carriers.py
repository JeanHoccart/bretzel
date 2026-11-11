"""What a test reads off a rendered page to act like the browser.

The action carriers (``hx-post`` and the form token around them), the
``_args`` blob, and a zone's fingerprint — read once here, so a change of
the wire format reddens every bench at once instead of leaving one copy
green on a stale reading.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from starlette.testclient import TestClient

from bretzel.runtime import HEADER_BZ_SIG, HEADER_BZ_TS
from bretzel.runtime.protocol import DATA_ZONE_HASH
from bretzel.server.handlers import FIELDS_TOKEN, action_path


class Carriers(HTMLParser):
    """Each action carrier, with the token of the form around it (or that
    it is) — what htmx joins to its request."""

    def __init__(self) -> None:
        super().__init__()
        self.found: list[dict[str, Any]] = []
        self._forms: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "form":
            self._forms.append({})
        if a.get("name") == FIELDS_TOKEN and self._forms:
            self._forms[-1]["token"] = a["value"]
        if "hx-post" in a:
            self.found.append({"tag": tag, **a, "form": self._forms[-1] if self._forms else {}})

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._forms:
            self._forms.pop()


def carriers_of(html: str, handler: object) -> list[dict[str, Any]]:
    parser = Carriers()
    parser.feed(html)
    return [c for c in parser.found if c["hx-post"] == action_path(handler)]


_ARGS = re.compile(r'"_args":\s*"([^"]*)"')


def blob_of(hx_vals: object) -> str:
    found = _ARGS.search(str(hx_vals or ""))
    return found.group(1) if found else ""


def post(client: TestClient, carrier: dict[str, Any], *,
         headers: dict[str, str] | None = None, **data: str):
    """The request htmx would send: the carrier's blob, its form's token,
    and the fields — plus whatever a client adds."""
    token = carrier["form"].get("token")
    return client.post(
        carrier["hx-post"],
        headers={HEADER_BZ_SIG: carrier["data-bz-sig"],
                 HEADER_BZ_TS: carrier.get("data-bz-ts", ""), **(headers or {})},
        data={"_args": blob_of(carrier.get("hx-vals")),
              **({FIELDS_TOKEN: token} if token else {}), **data},
    )


def zone_stamp(html: str, zone_id: str) -> str:
    """The fingerprint the page stamped on zone ``zone_id``."""
    found = re.search(rf'bz-id="{zone_id}"[^>]*?{DATA_ZONE_HASH}="([0-9a-f]+)"', html) or \
        re.search(rf'{DATA_ZONE_HASH}="([0-9a-f]+)"[^>]*?bz-id="{zone_id}"', html)
    assert found, f"{zone_id} carries no fingerprint"
    return found.group(1)
