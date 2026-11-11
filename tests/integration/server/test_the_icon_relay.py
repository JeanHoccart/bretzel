"""``/_bretzel/icons`` answers the component's request, and only it.

Three defects of the relay, found on 2026-11-06 and each held here : it
relayed any path and query upstream, wrote one cache file per distinct
query (so the disk grew with what a stranger could invent), and made its
upstream call on the event loop (one slow answer froze the worker). The
path traversal it also allowed is held by the gate
``tests/consistency/test_a_framework_path_never_leaves_its_folder.py``.

Upstream is a fake ``urlopen`` : no test here touches the network.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, ui
from bretzel.render import page, vendor

ICONS = "/_bretzel/icons"


class _Upstream:
    """Answers like the Iconify API for the set ``mdi``; counts its calls."""

    def __init__(self, delay: float = 0.0) -> None:
        self.calls: list[str] = []
        self.delay = delay

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.calls.append(url)
        time.sleep(self.delay)
        names = url.split("icons=", 1)[1].split(",")
        body = {
            "prefix": "mdi",
            "width": 32,
            "height": 32,
            "icons": {n: {"body": f"<path d='{n}'/>"} for n in names if n != "nope"},
        }
        if "nope" in names:
            body["not_found"] = ["nope"]
        return _Response(json.dumps(body).encode())


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = Bretzel(secret_key="k3Jq9w" * 6, mode="prod")

    @page("/")
    def home() -> None:
        ui.text("ok")

    app.include(home)
    with TestClient(app) as test_client:
        yield test_client


def _cache_files() -> list:
    return sorted(p.name for p in vendor.icon_cache_dir().iterdir())


def test_only_the_components_request_goes_upstream(client, monkeypatch) -> None:
    upstream = _Upstream()
    monkeypatch.setattr(urllib.request, "urlopen", upstream)
    for refused in (
        "/mdi.json?icons=home&junk=1",
        "/any/upstream/path?x=1",
        "/collections?prefix=mdi",
        "/mdi.json?icons=Home",
        "/mdi.json?icons=",
        "/mdi.js?icons=home&callback=x",
    ):
        assert client.get(ICONS + refused).status_code == 404, refused
    assert upstream.calls == []
    assert client.get(ICONS + "/mdi.json?icons=home").status_code == 200
    assert upstream.calls == ["https://api.iconify.design/mdi.json?icons=home"]


def test_the_cache_holds_icons_not_requests(client, monkeypatch) -> None:
    upstream = _Upstream()
    monkeypatch.setattr(urllib.request, "urlopen", upstream)
    combos = ["home", "home,star", "star,home", "star", "home,star,bell", "bell,home"]
    for _ in range(5):
        for combo in combos:
            response = client.get(f"{ICONS}/mdi.json?icons={combo}")
            assert response.status_code == 200
            assert set(response.json()["icons"]) == set(combo.split(","))
    assert _cache_files() == ["mdi.json"], "one file per set, not per request"
    assert len(upstream.calls) == 3, upstream.calls  # home ; star ; bell
    glyph = client.get(f"{ICONS}/mdi.json?icons=home").json()["icons"]["home"]
    assert (glyph["width"], glyph["height"]) == (32, 32), glyph


def test_an_unknown_name_is_answered_and_not_kept(client, monkeypatch) -> None:
    upstream = _Upstream()
    monkeypatch.setattr(urllib.request, "urlopen", upstream)
    answer = client.get(f"{ICONS}/mdi.json?icons=home,nope").json()
    assert set(answer["icons"]) == {"home"} and answer["not_found"] == ["nope"]
    kept = json.loads((vendor.icon_cache_dir() / "mdi.json").read_text("utf-8"))
    assert set(kept["icons"]) == {"home"}


def test_a_slow_upstream_does_not_freeze_the_worker(client, monkeypatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _Upstream(delay=2.0))
    waiting = threading.Thread(target=client.get, args=(f"{ICONS}/mdi.json?icons=slow",))
    waiting.start()
    time.sleep(0.3)
    started = time.monotonic()
    assert client.get("/_bretzel/theme.css").status_code == 200
    elapsed = time.monotonic() - started
    waiting.join()
    assert elapsed < 1.0, (
        f"theme.css took {elapsed:.2f} s behind one icon request : the "
        "upstream call runs on the event loop again."
    )
