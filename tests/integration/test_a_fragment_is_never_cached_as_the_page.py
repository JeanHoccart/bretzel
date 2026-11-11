"""Un fragment de navigation n'est jamais rangé sous l'URL de la page.

Vu par Jean le 2026-10-26 sur ui.bretzel-py.dev/accordion : une page
sans CSS, avec ``{"patches":{"Checkout.default":…}}`` en texte tout en
haut. C'était le fragment d'une navigation boostée — même URL que la
page, réponse différente selon ``HX-Request`` / ``HX-Target``, et aucun
``Vary`` : Chrome l'a gardé en cache et l'a ré-affiché tel quel sur un
retour arrière.

Le contrat : toute page dit qu'elle varie selon ces deux en-têtes, et
un fragment interdit qu'on le stocke.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

_PAGE = "/markdown"
_OUTLET = "outlet_shell"


@pytest.fixture(scope="module")
def client():
    from examples.playground.main import app

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def varies_on(response) -> set[str]:
    return {
        token.strip().lower()
        for value in response.headers.get_list("vary")
        for token in value.split(",")
    }


def test_the_fragment_really_is_a_fragment(client) -> None:
    """Garde-fou : si la navigation cessait d'être partielle, les deux
    tests suivants ne prouveraient plus rien."""
    partial = client.get(_PAGE, headers={"HX-Request": "true", "HX-Target": _OUTLET})
    assert partial.status_code == 200
    assert "<head" not in partial.text


def test_a_page_varies_on_the_headers_that_choose_its_shape(client) -> None:
    for headers in ({}, {"HX-Request": "true", "HX-Target": _OUTLET}):
        response = client.get(_PAGE, headers=headers)
        assert {"hx-request", "hx-target"} <= varies_on(response), response.headers


def test_a_fragment_is_never_stored(client) -> None:
    partial = client.get(_PAGE, headers={"HX-Request": "true", "HX-Target": _OUTLET})
    assert partial.headers.get("cache-control") == "no-store"
