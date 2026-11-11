"""``Bretzel(base_path=…)``: the app writes nothing, the framework prefixes.

What is at stake is the sum of every address the framework writes: one that
is forgotten is a 404 only under a prefix, which no other test would see.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from bretzel import PWA, Bretzel, layout, page, redirect, refreshable, ui
from bretzel.core.base_path import normalize, same_host, strip, with_base, without_base
from bretzel.server.config import ConfigError
from bretzel.server.navigation import _validate
from bretzel.state import AppState, field


class Rev(AppState):
    rev: int = field(default=0, merge="add")


def bumped() -> None:
    Rev().rev += 1


def to_other() -> None:
    redirect("/autre")


def to_sibling() -> None:
    redirect("http://localhost:9999/admin/comptes")


def to_elsewhere() -> None:
    redirect("https://ailleurs.example/")


@refreshable
def zone() -> None:
    ui.text(f"rev {Rev().rev}")


@layout
def coque() -> None:
    with ui.sidebar():
        with ui.sidebar_section():
            ui.sidebar_item("Accueil", icon="house", href="/")
            ui.sidebar_item("Autre", icon="file", href="/autre")
            ui.sidebar_item("Voisine", icon="users", href="http://localhost:9999/admin/comptes")
            ui.sidebar_item("Ailleurs", icon="globe", href="https://ailleurs.example/")
    ui.outlet()


@page("/", layout=coque)
def accueil() -> None:
    ui.link("Vers autre", href="/autre")
    ui.button("Monte", on_click=bumped)
    zone()


@page("/autre", layout=coque)
def autre() -> None:
    ui.text("AUTRE")


def build(base: str) -> Bretzel:
    app = Bretzel(secret_key="k" * 32, mode="dev", base_path=base, pwa=PWA(
        name="Essai", start_url="/autre", icon="/static/logo.png"))
    app.include(__name__)
    return app


@pytest.fixture(scope="module")
def client():
    with TestClient(build("/app"), base_url="http://localhost") as c:
        yield c


LOCAL = re.compile(r'\b(href|src|hx-get|hx-post|action)="(/[^"]*)"')


def test_every_local_address_of_the_page_is_prefixed(client) -> None:
    html = client.get("/app/").text
    found = LOCAL.findall(html)
    assert len(found) > 8
    assert [u for _, u in found if not u.startswith("/app/")] == []


def test_a_request_is_served_with_the_prefix_and_without_it(client) -> None:
    """A proxy may keep the prefix or remove it: same answer."""
    assert "AUTRE" in client.get("/app/autre").text
    assert "AUTRE" in client.get("/autre").text
    assert client.get("/app/_bretzel/runtime.js").status_code == 200


def test_the_runtime_is_told_and_its_endpoints_are_prefixed(client) -> None:
    html = client.get("/app/").text
    assert '<html lang="en" data-bz-base="/app">' in html
    for route in ("action", "sse", "refetch"):
        assert f'/app/_bretzel/{route}' in html
    assert 'resources:["/app/_bretzel/icons"]' in html


def test_the_menu_compares_with_the_path_inside_the_app(client) -> None:
    html = client.get("/app/").text
    assert "$bz._localPath()" in html and "window.location.pathname" not in html.split("<body")[1]


def test_a_sibling_on_this_host_opens_in_place_elsewhere_in_a_new_tab(client) -> None:
    html = client.get("/app/").text
    sibling = re.search(r'<a [^>]*localhost:9999/admin/comptes[^>]*>', html).group(0)
    elsewhere = re.search(r'<a [^>]*ailleurs\.example[^>]*>', html).group(0)
    assert "_blank" not in sibling and "hx-get" not in sibling
    assert 'target="_blank"' in elsewhere


def test_the_manifest_is_prefixed_and_keeps_its_scope() -> None:
    import json
    assert json.loads(PWA(name="x", start_url="/a", icon="/i.png", scope="/").as_json("/app")) == {
        "name": "x", "short_name": "x", "display": "standalone", "start_url": "/app/a",
        "scope": "/", "icons": [{"src": "/app/i.png", "sizes": "any", "type": "image/png"}]}


def test_an_app_at_the_root_is_untouched() -> None:
    with TestClient(build(""), base_url="http://localhost") as c:
        html = c.get("/").text
    assert "data-bz-base" not in html and "$bz._localPath()" not in html
    assert 'href="/autre"' in html


@pytest.mark.parametrize("value, expected", [("", ""), ("/", ""), (None, ""), ("/a/b", "/a/b")])
def test_normalize_accepts(value, expected) -> None:
    assert normalize(value) == expected


@pytest.mark.parametrize("value", ["radar", "/radar/", "//x", "/a?b", "/a#b", "/a b"])
def test_a_malformed_base_path_is_refused_at_startup(value) -> None:
    with pytest.raises(ConfigError, match="base_path"):
        Bretzel(secret_key="k" * 32, mode="dev", base_path=value)


def test_with_base_leaves_what_is_not_a_path_of_this_site() -> None:
    for url in ("https://x.fr/a", "//x.fr/a", "#top", "data:,", "mailto:a@b.c", "relatif"):
        assert with_base(url, "/app") == url
    assert with_base("/a?b=1", "/app") == "/app/a?b=1"


def test_without_base_only_takes_a_whole_segment() -> None:
    assert without_base("/app/x", "/app") == "/x"
    assert without_base("/app", "/app") == "/"
    assert without_base("/application", "/app") == "/application"


def test_strip_only_takes_a_whole_segment() -> None:
    assert strip({"path": "/application"}, "/app") == {"path": "/application"}
    assert strip({"path": "/app/x", "raw_path": b"/app/x"}, "/app") == {
        "path": "/x", "raw_path": b"/x"}


def _request(host: str):
    return SimpleNamespace(url=SimpleNamespace(hostname=host))


@pytest.mark.parametrize("url, expected", [
    ("https://acer.ts.net:8460/admin", True),
    ("http://ACER.ts.net/admin", True),
    ("https://ailleurs.example/", False),
    ("javascript:alert(1)", False),
    ("https://evil.com\\@acer.ts.net/", False),
    ("https://user@acer.ts.net/", False),
    ("https://acer.ts.net.evil.com/", False),
    ("/local", False),
])
def test_same_host(url: str, expected: bool) -> None:
    assert same_host(url, _request("acer.ts.net")) is expected


def test_the_names_of_this_machine_are_one_host() -> None:
    assert same_host("http://127.0.0.1:8460/portail", _request("localhost"))
    assert not same_host("http://127.0.0.1:8460/portail", _request("acer.ts.net"))


def test_redirect_refuses_another_host_and_takes_this_one() -> None:
    request = _request("acer.ts.net")
    _validate("https://acer.ts.net:8460/admin", request)
    _validate("/local", request)
    for bad in ("https://ailleurs.example/", "//ailleurs.example", "javascript:alert(1)"):
        with pytest.raises(ValueError):
            _validate(bad, request)
