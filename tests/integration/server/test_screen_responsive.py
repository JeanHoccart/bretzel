"""End-to-end test for the Screen responsive layout (server-authoritative).

The whole feature is : a ``@layout`` (or page) branches on ``Screen().is_mobile``
— a plain Python ``if`` — and the server renders the matching tree from the
``bz_screen`` cookie. No ``@refreshable``, no live resize machinery (a device
doesn't change mid-session) : whenever the cookie doesn't match the real
viewport, the boot script spends one pre-paint reload and the next render is
correct — on every load, not once per tab (cf.
``tests/consistency/test_screen_sync_guard_is_consumed.py``).

Zones live at MODULE level so the app is stable across tests.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from bretzel import Bretzel, Screen, layout, page, ui

_SECRET = "x" * 32

_app = Bretzel(secret_key=_SECRET, mode="dev", mobile_breakpoint=700)


@layout
def shell() -> None:
    # A structural swap : sidebar on the left (desktop) vs a top bar (mobile) —
    # two different trees, exactly the case CSS can't exchange cleanly. No
    # @refreshable : the layout just reads Screen() at render time.
    if Screen().is_mobile:
        with ui.vstack(gap="none"):
            ui.text("TOPBAR")
            ui.outlet()
    else:
        with ui.hstack(gap="none"):
            ui.text("SIDEBAR")
            ui.outlet()


@page("/", layout=shell, title="Home")
def home() -> None:
    ui.text("PAGE-CONTENT")


_app.include(home)


class TestServerBranch:
    def test_desktop_cookie_renders_sidebar(self) -> None:
        with TestClient(_app) as client:
            html = client.get("/", cookies={"bz_screen": "0,0"}).text
        assert "SIDEBAR" in html
        assert "TOPBAR" not in html
        assert "PAGE-CONTENT" in html  # outlet filled

    def test_mobile_cookie_renders_topbar(self) -> None:
        with TestClient(_app) as client:
            html = client.get("/", cookies={"bz_screen": "1,0"}).text
        assert "TOPBAR" in html
        assert "SIDEBAR" not in html
        assert "PAGE-CONTENT" in html  # outlet filled

    def test_no_cookie_falls_back_to_desktop(self) -> None:
        # Brand-new visitor : no cookie yet → desktop fallback. The boot script
        # writes the cookie + spends one pre-paint reload if the real viewport
        # is mobile.
        with TestClient(_app) as client:
            html = client.get("/").text
        assert "SIDEBAR" in html


class TestNoLiveMachinery:
    def test_no_screen_refetch_url_in_page(self) -> None:
        # The zone-refetch mechanism was dropped : a Screen-branching layout
        # must NOT emit any per-zone refetch marker.
        with TestClient(_app) as client:
            html = client.get("/", cookies={"bz_screen": "1,0"}).text
        assert "data-bz-screen-url" not in html
        assert "/_bretzel/rescreen" not in html

    def test_boot_script_writes_cookie(self) -> None:
        with TestClient(_app) as client:
            html = client.get("/").text
        assert "bz_screen=" in html
        assert "(max-width: 700px)" in html  # configured breakpoint
