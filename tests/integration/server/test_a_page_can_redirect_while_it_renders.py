"""``redirect()`` while a page renders answers a real redirect.

An address that only leads elsewhere — an app's root opening on its main
list, an old address kept — is a page that redirects. ``redirect()``
used to raise there (it only spoke to htmx), and Radar answered « / »
with a hand-written FastAPI route (2026-11-07).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, redirect, ui
from bretzel.server.navigation import PageRedirectError

app = Bretzel(secret_key="x" * 32, mode="dev")


@page("/")
def home() -> None:
    redirect("/strategies")
    ui.text("never rendered")


@page("/strategies")
def strategies() -> None:
    ui.text("the strategies", id="strategies")


app.include(home, strategies)


@app.fastapi.get("/api/elsewhere")
def api_route() -> dict:
    redirect("/strategies")
    return {}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_a_typed_address_gets_a_real_redirect(client) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/strategies"
    assert "never rendered" not in response.text


def test_the_browser_lands_on_the_target(client) -> None:
    assert "the strategies" in client.get("/").text


def test_a_boosted_navigation_still_goes_through_htmx(client) -> None:
    response = client.get("/", headers={"HX-Request": "true"}, follow_redirects=False)
    assert response.status_code == 200
    assert {"hx-redirect", "hx-location"} & {k.lower() for k in response.headers}


def test_outside_a_page_it_is_an_error() -> None:
    """No page renders there, so no response to turn into a redirect: an
    error that names ``redirect_response``, the way out."""
    assert "redirect_response" in str(PageRedirectError("/x"))
    with TestClient(app, raise_server_exceptions=False) as c:
        assert c.get("/api/elsewhere", follow_redirects=False).status_code == 500
