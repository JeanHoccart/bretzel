"""Un lien vers une page d'une autre coque charge la page entière.

La coque booste ses liens internes : htmx demande la page avec
``HX-Target: outlet_<coque>`` et glisse la réponse dans cet outlet. Tant
que la page visée vit dans cette coque, le serveur ne rend que ce qui est
dedans. Mais si elle n'en a pas — une page sans layout, comme un « grand
écran » de projection, ou une page d'une autre coque — le serveur
rendait le document ENTIER, et htmx le glissait dans l'outlet : la page
plein écran s'affichait sous la barre latérale qu'elle voulait quitter
(Jean, 2026-10-27, sur une capture).

Le contrat : quand l'outlet visé n'est pas dans la chaîne de la page, la
réponse est un ``HX-Redirect`` vers la même adresse — le navigateur la
charge en entier, sans en-têtes htmx, et la coque d'avant disparaît.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from bretzel import Bretzel, layout, page, ui
from bretzel.runtime.protocol import outlet_id_for

_app = Bretzel(secret_key="x" * 32, mode="dev")


@layout
def coque() -> None:
    ui.text("barre latérale")
    ui.outlet()


@layout
def autre() -> None:
    ui.outlet()


@page("/", layout=coque)
def accueil() -> None:
    ui.link("plein écran", href="/plein")


@page("/plein")
def plein() -> None:
    ui.text("toute la salle")


@page("/ailleurs", layout=autre)
def ailleurs() -> None:
    ui.text("une autre coque")


_app.include(accueil, plein, ailleurs)

_BOOSTED = {"HX-Request": "true", "HX-Target": outlet_id_for(coque.__name__)}


@pytest.fixture(scope="module")
def client():
    with TestClient(_app, raise_server_exceptions=True) as c:
        yield c


def test_a_link_inside_the_same_shell_stays_a_fragment(client) -> None:
    """Garde-fou : la navigation partielle ordinaire ne change pas."""
    response = client.get("/", headers=_BOOSTED)
    assert response.status_code == 200
    assert "HX-Redirect" not in response.headers
    assert "<head" not in response.text


@pytest.mark.parametrize("path", ["/plein", "/ailleurs"])
def test_a_page_outside_the_shell_is_loaded_whole(client, path: str) -> None:
    response = client.get(path, headers=_BOOSTED)
    assert response.headers.get("HX-Redirect") == path
    assert "toute la salle" not in response.text and "une autre coque" not in response.text


@pytest.mark.parametrize("path", ["/plein", "/ailleurs"])
def test_the_same_page_loaded_by_the_browser_is_whole(client, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert "<head" in response.text and "HX-Redirect" not in response.headers


def test_an_htmx_request_aimed_elsewhere_is_left_alone(client) -> None:
    """Seule une cible d'outlet déclenche le rechargement : un ``hx-get``
    d'app vers une page, visant autre chose, reçoit la page comme avant."""
    response = client.get("/plein", headers={"HX-Request": "true", "HX-Target": "detail"})
    assert "HX-Redirect" not in response.headers
    assert "toute la salle" in response.text
