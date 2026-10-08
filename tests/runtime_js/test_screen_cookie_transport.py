"""The screen cookie follows the page's HTTP or HTTPS transport."""

from __future__ import annotations

import pytest

from bretzel.render.shell import _screen_sync_script
from tests.audit.harness import browser_context

pytestmark = pytest.mark.browser


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_screen_cookie_follows_transport(scheme: str) -> None:
    script = _screen_sync_script(768)
    html = f"<script>{script}window.$bzScreenSync();</script>"
    url = f"{scheme}://screen.test/"
    with browser_context() as context:
        context.route(url, lambda route: route.fulfill(content_type="text/html", body=html))
        page = context.new_page()
        page.goto(url)
        cookie = next(cookie for cookie in context.cookies() if cookie["name"] == "bz_screen")
        assert cookie["value"] == "0,0"
        assert cookie["secure"] is (scheme == "https")
        assert cookie["path"] == "/"
        assert cookie["sameSite"] == "Lax"
        assert cookie["httpOnly"] is False
