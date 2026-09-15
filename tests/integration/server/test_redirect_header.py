"""``redirect()`` — l'en-tête arrive vraiment sur la réponse d'action.

La fonction fait UNE chose : poser ``HX-Redirect`` sur la réponse, en
comptant sur deux faits qu'elle ne contrôle pas — que ``ctx`` recopie
ses ``response_headers`` vers la réponse d'action, et qu'htmx traite cet
en-tête nativement. Le premier se teste ici ; le second demande un vrai
navigateur : ``tests/runtime_js/test_redirect_actually_navigates.py``.

Ce que ce fichier verrouille, dans l'ordre où ça casserait :

1. l'en-tête traverse le round-trip d'action jusqu'à la réponse HTTP ;
2. le handler continue après l'appel (pas de sortie non-locale) ;
3. un rendu de page classique REFUSE l'appel au lieu de l'avaler — le
   demi-branchement silencieux est précisément la classe de défaut qui a
   coûté six mois au kind ``"redirect"`` du bridge ;
4. une URL porteuse d'un CR/LF est refusée (response splitting).

App + handlers au niveau MODULE : la route d'action résout ses handlers
via ``sys.modules`` et rejette les ``<locals>``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bretzel import Bretzel, page, redirect, ui
from bretzel.core.errors import BretzelError
from bretzel.server.handlers import encode_action_id, sign_action

_SECRET = "r" * 32

_app = Bretzel(secret_key=_SECRET, mode="dev")

#: Ce que le handler a exécuté, dans l'ordre. Prouve que ``redirect()``
#: n'interrompt pas — la ligne d'après doit y figurer.
_trace: list[str] = []


def save_and_go() -> None:
    _trace.append("before")
    redirect("/factures/42")
    _trace.append("after")


@page("/form")
def form_page() -> None:
    ui.button("Enregistrer", on_click=save_and_go)


_app.include(form_page)


def go_to_crlf() -> None:
    redirect("/ok\r\nX-Injected: 1")


@page("/crlf")
def crlf_page() -> None:
    ui.button("Injecter", on_click=go_to_crlf)


_app.include(crlf_page)


@page("/plain")
def plain_page() -> None:
    """Une page qui appelle ``redirect()`` pendant son rendu — le cas où
    l'en-tête serait invisible, donc celui qui doit lever."""
    redirect("/ailleurs")


_app.include(plain_page)


@pytest.fixture(autouse=True)
def _clear_trace():
    _trace.clear()
    yield


@pytest.fixture
def client():
    """Un seul client pour tout le fichier.

    ``raise_server_exceptions=False`` partout : les deux tests qui ne
    lèvent pas se comportent à l'identique avec ou sans, et les trois qui
    lèvent ont besoin de lire le statut plutôt que de propager.
    """
    with TestClient(_app, raise_server_exceptions=False) as c:
        yield c


def _post(client: TestClient, action) -> object:
    action_id = encode_action_id(action)
    sig = sign_action(_app.config._action_key, action_id, "")
    return client.post(
        f"/_bretzel/action/{action_id}",
        # htmx pose ``HX-Request`` sur toute requête qu'il émet ; la
        # garde de ``redirect()`` s'appuie dessus, donc le test doit
        # reproduire le vrai câblage plutôt que de le contourner.
        headers={"X-Bz-Sig": sig, "HX-Request": "true"},
        data={"_args": ""},
    )


class TestActionResponse:
    def test_header_reaches_the_http_response(self, client) -> None:
        client.get("/form")
        response = _post(client, save_and_go)

        assert response.headers.get("HX-Redirect") == "/factures/42"

    def test_handler_keeps_running_after_the_call(self, client) -> None:
        """Pas de sortie non-locale — c'est ce qui distingue ``redirect()``
        d'``abort()``, et ce qu'un humain lit de haut en bas."""
        client.get("/form")
        _post(client, save_and_go)

        assert _trace == ["before", "after"]


class TestGuards:
    def test_plain_page_render_refuses_instead_of_swallowing(self, client) -> None:
        """Sur un GET de page nu, htmx n'est pas dans la boucle : l'en-tête
        ne serait lu par personne. On lève plutôt que de ne rien faire."""
        assert client.get("/plain").status_code == 500

    def test_boosted_partial_nav_is_accepted(self, client) -> None:
        """La même page, demandée par htmx, passe : la réponse d'une nav
        partielle EST lue par htmx. La garde vise le rendu nu, pas la page."""
        response = client.get("/plain", headers={"HX-Request": "true"})

        assert response.status_code == 200
        assert response.headers.get("HX-Redirect") == "/ailleurs"

    def test_crlf_in_url_is_refused(self, client) -> None:
        """Response splitting : une URL de redirection vient souvent d'une
        donnée utilisateur (``?next=``)."""
        client.get("/crlf")
        response = _post(client, go_to_crlf)

        assert response.status_code == 500
        assert "X-Injected" not in response.headers


class TestCallableOutsideARequest:
    def test_no_context_raises_rather_than_no_op(self) -> None:
        with pytest.raises((RuntimeError, BretzelError)):
            redirect("/nulle-part")
